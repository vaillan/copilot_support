import json
from langgraph.graph import END
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.models.llm_factory import get_reviewer_llm
from app.utils.summarization import aplicar_resumen_middleware

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from app.models.models import ProjectState
from langchain_core.runnables import RunnableConfig
from app.utils.files import File, get_custom_file_tools
from app.utils.prompt_utils import escapar_llaves
from app.utils.skills_loader import cargar_skills_para_prompt
from app.utils.terminal_tool import configurar_directorio, terminal
from functools import lru_cache
from app.utils.args_utils import _get_args

fileSystem = File(directory="prompts")


@tool
def finalizar_revision(aprobado: bool, requiere_pruebas: bool = True, reporte_errores: str = "") -> str:
    """Finaliza la revisión del código indicando el resultado de la evaluación.

    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de evaluar el código.

    Args:
        aprobado (bool): Indica si el código fue aprobado.
        requiere_pruebas (bool): Indica si el código requiere pruebas; por defecto True.
        reporte_errores (str): Detalle de los errores encontrados, si los hay;
            por defecto cadena vacía.

    Reglas de uso:
        - Si el código NO requiere pruebas (ej. documentación, HTML estático, o el plan indica que no requiere test), pon requiere_pruebas=False y aprobado=True.
        - Si el código SÍ requiere pruebas y FALLA, pon requiere_pruebas=True, aprobado=False y detalla los errores en 'reporte_errores'.
        - Si el código SÍ requiere pruebas y PASA exitosamente, pon requiere_pruebas=True y aprobado=True.

    Returns:
        str: Mensaje de confirmación de que la revisión fue procesada.
    """
    return "Revisión procesada."

@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    """Construye y cachea la lista de herramientas de revisión para un directorio.

    Actualiza el directorio del proyecto actual (compartido con la tool
    `terminal` de app/utils/terminal_tool.py) y combina las herramientas de
    terminal y finalización con las de lectura de archivos (read_file,
    read_file_summary).

    Args:
        directorio (str): Ruta del directorio del proyecto.

    Returns:
        list[BaseTool]: Lista de herramientas (terminal, finalizar_revision y las de lectura).
    """
    configurar_directorio(directorio)
    todas = get_custom_file_tools(directorio)
    herramientas_lectura = [
        t for t in todas
        if t.name in ["read_file", "read_file_summary"]
    ]
    herramientas = [terminal, finalizar_revision] + herramientas_lectura
    return herramientas

def agente_revisor(state: ProjectState) -> Command:
    """Ejecuta la revisión del código probándolo en la terminal y decide el flujo.

    Args:
        state (ProjectState): Estado global del proyecto con mensajes, plan de
            acción, directorio y contadores de iteración/revisión.

    Returns:
        Command: Comando de LangGraph que actualiza el estado y dirige el flujo
            a END, "agente_codificador", "nodo_herramientas_revisor" o
            "agente_revisor" según el resultado de la revisión.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    
    # 0. Verificación rápida del plan: Si ningún paso del plan requiere test, aprobamos automáticamente.
    plan = state.get("plan_de_accion")
    if isinstance(plan, dict) and "pasos" in plan:
        pasos = plan.get("pasos", [])
        if pasos and all(isinstance(p, dict) and not p.get("requiere_test", True) for p in pasos):
            return Command(
                update={
                    "errores_terminal": "No se requirieron pruebas para este plan. Aprobado automáticamente.",
                    "messages": [HumanMessage(content="Revisión omitida: ningún paso del plan requiere pruebas. Código aprobado automáticamente.")],
                    "loop_counter": 0
                },
                goto=END
            )

    # Prevenir bucles infinitos en el agente revisor
    if loop_counter > 5:
        messages = state.get("messages", [])
        errores_detectados = ""
        for m in reversed(messages):
            if isinstance(m, ToolMessage) and m.content:
                content_str = str(m.content)
                if "error" in content_str.lower() or "fail" in content_str.lower() or "exception" in content_str.lower():
                    errores_detectados = content_str
                    break

        if errores_detectados:
            revision_count = state.get("revision_count", 0) + 1
            if revision_count >= 3:
                return Command(
                    update={
                        "errores_terminal": f"Límite de iteraciones y revisiones alcanzado. Últimos errores: {errores_detectados}",
                        "messages": [HumanMessage(content="Límite máximo de iteraciones de pruebas alcanzado con errores. Proceso detenido.")],
                        "loop_counter": loop_counter,
                        "revision_count": revision_count
                    },
                    goto=END
                )
            return Command(
                update={
                    "errores_terminal": f"Errores detectados tras múltiples intentos de prueba: {errores_detectados}",
                    "messages": [HumanMessage(content=f"Pruebas no concluidas adecuadamente. Errores detectados: {errores_detectados}")],
                    "loop_counter": 0,
                    "revision_count": revision_count,
                    "pausa_motivo": "retrabajo_qa"
                },
                goto="agente_codificador"
            )
        else:
            return Command(
                update={
                    "errores_terminal": "Ninguno. Verificación completada tras múltiples iteraciones sin errores.",
                    "messages": [HumanMessage(content="Finalización automática del Revisor por límite de iteraciones sin detección de errores.")],
                    "loop_counter": loop_counter
                },
                goto=END
            )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_qa = _get_tools(directorio)
    
    llm = get_reviewer_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_qa)
    
    prompt_sistema = fileSystem.get_file_content(file_name="revisor_prompt.md")
    
    # Inyectar el índice del proyecto cargándolo desde la caché en disco
    # (optimización de tokens sin persistir el índice en los checkpoints).
    from app.utils.project_index import (
        extraer_archivos_relevantes,
        formatear_indice_para_prompt,
        obtener_indice_para_agentes,
    )
    project_index = obtener_indice_para_agentes(directorio, state.get("project_index"))
    if project_index and isinstance(project_index, dict):
        plan_estado = state.get("plan_de_accion")
        texto_fuentes = "\n".join(filter(None, [
            json.dumps(plan_estado, ensure_ascii=False, default=str) if plan_estado else "",
            str(state.get("analisis_final") or ""),
        ]))
        archivos_relevantes = extraer_archivos_relevantes(texto_fuentes, project_index)
        indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index, archivos_relevantes=archivos_relevantes))
        prompt_sistema += (
            "\n\n=== ÍNDICE DEL PROYECTO (proporcionado, usa read_file_summary para inspección) ===\n"
            f"{indice_texto}"
        )

    seccion_skills = cargar_skills_para_prompt(directorio, agente="revisor")
    if seccion_skills:
        prompt_sistema += "\n\n" + seccion_skills

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa evaluando el código.")]

    # Pasamos el plan de acción para que el QA sepa si el planificador exigió pruebas
    prompt = prompt_template.invoke({
        "messages": mensajes_contexto,
        "directorio": directorio,
        "codigo_escrito": state.get("codigo_escrito", "Sin reporte."),
        "plan": state.get("plan_de_accion", "Sin plan.")
    })
    
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        # Extraer comandos de terminal ejecutados previamente en el historial
        comandos_previos = []
        for m in msgs:
            if isinstance(m, AIMessage) and m.tool_calls:
                for tc in m.tool_calls:
                    if tc.get("name") == "terminal":
                        comandos_previos.append(str(tc.get("args")))

        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "finalizar_revision":
                args_revision = _get_args(tool_call)
                aprobado = args_revision.get("aprobado", False)
                requiere_pruebas = args_revision.get("requiere_pruebas", True)
                errores = args_revision.get("reporte_errores", "")
                
                tool_messages = [
                    ToolMessage(
                        tool_call_id=tc["id"],
                        content="Revisión finalizada con éxito." if tc["name"] == "finalizar_revision" else "Operación completada",
                    )
                    for tc in respuesta.tool_calls
                ]
                
                # Si no requiere pruebas, terminamos el bucle directamente
                if not requiere_pruebas:
                    return Command(
                        update={
                            "errores_terminal": "No se requirieron pruebas para este código. Aprobado automáticamente.",
                            "messages": [respuesta] + tool_messages,
                            "loop_counter": loop_counter
                        },
                        goto=END
                    )
                
                # Si requiere pruebas y fue aprobado
                elif aprobado:
                    return Command(
                        update={
                            "errores_terminal": "Ninguno. Código probado y aprobado.",
                            "messages": [respuesta] + tool_messages,
                            "loop_counter": loop_counter
                        },
                        goto=END
                    )
                
                # Si requiere pruebas y falló (aprobado=False)
                else:
                    revision_count = state.get("revision_count", 0) + 1
                    if revision_count >= 3:
                        return Command(
                            update={
                                "errores_terminal": f"Límite de revisiones alcanzado. Últimos errores: {errores}",
                                "messages": [respuesta] + tool_messages + [HumanMessage(content="Se ha alcanzado el límite máximo de 3 revisiones. El proceso se detiene.")],
                                "loop_counter": loop_counter,
                                "revision_count": revision_count
                            },
                            goto=END
                        )
                    
                    return Command(
                        update={
                            "errores_terminal": errores,
                            "messages": [respuesta] + tool_messages,
                            "loop_counter": 0,
                            "revision_count": revision_count,
                            "pausa_motivo": "retrabajo_qa"
                        },
                        goto="agente_codificador"
                    )

            elif tool_call["name"] == "terminal":
                args_str = str(tool_call.get("args"))
                if args_str in comandos_previos:
                    # Detección de comando duplicado: evitar ejecutar el mismo comando repetidamente
                    return Command(
                        update={
                            "errores_terminal": "Ninguno. Verificación finalizada por detección de comandos redundantes en terminal.",
                            "messages": [
                                respuesta,
                                HumanMessage(content="El comando de terminal ya fue ejecutado previamente. Se concluye la revisión para evitar un bucle de ejecución.")
                            ],
                            "loop_counter": loop_counter
                        },
                        goto=END
                    )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_revisor"
        )
    else:
        # Si la respuesta en texto sugiere aprobación o no requiere pruebas
        contenido_texto = str(respuesta.content).lower()
        palabras_aprobacion = ["aprobado", "correcto", "sin errores", "exitoso", "no requiere", "paso las pruebas", "pasó las pruebas"]
        if any(p in contenido_texto for p in palabras_aprobacion):
            return Command(
                update={
                    "errores_terminal": "Ninguno. Código aprobado en revisión.",
                    "messages": [respuesta],
                    "loop_counter": loop_counter
                },
                goto=END
            )

        if loop_counter >= 2:
            # Si el modelo sigue respondiendo con texto sin llamar a herramientas tras 2 intentos
            return Command(
                update={
                    "errores_terminal": "No se ejecutaron pruebas de terminal pero la revisión se concluyó sin errores reportados.",
                    "messages": [respuesta, HumanMessage(content="Finalizando revisión tras respuestas continuas en texto.")],
                    "loop_counter": loop_counter
                },
                goto=END
            )

        return Command(
            update={
                "messages": [respuesta, HumanMessage(content="Debes llamar a una herramienta para probar el código o llamar a finalizar_revision si ya terminaste o si el código no requiere pruebas.")],
                "loop_counter": loop_counter
            },
            goto="agente_revisor"
        )

def nodo_herramientas_revisor(state: ProjectState, config: RunnableConfig):
    """Ejecuta las herramientas de revisión mediante ToolNode de LangGraph.

    Args:
        state (ProjectState): Estado global del proyecto.
        config (RunnableConfig): Configuración de ejecución de LangGraph.

    Returns:
        dict: Resultado de la invocación del ToolNode o, ante una excepción,
            un dict con un mensaje de error en "messages".
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    herramientas_ejecutables = [t for t in herramientas if t.name != "finalizar_revision"]
    nodo = ToolNode(herramientas_ejecutables)
    try:
        return nodo.invoke(state, config=config)
    except BaseException as e:
        return {
            "messages": [HumanMessage(content=f"Error al ejecutar herramienta de revisión: {str(e)}")]
        }
