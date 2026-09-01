import json
from pydantic import BaseModel, Field
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.graph import END
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableConfig
from app.utils.files import File, get_custom_file_tools
from app.models.models import ProjectState
from app.models.llm_factory import get_coder_llm
from app.utils.summarization import aplicar_resumen_middleware
from app.utils.prompt_utils import escapar_llaves, construir_prompt_template_cacheado
from app.utils.test_regenerator import evaluar_regeneracion_tests
from app.utils.skills_loader import cargar_skills_para_prompt
from functools import lru_cache
from app.utils.args_utils import _get_args

fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

# Conjunto de herramientas que realizan una escritura física en disco.
herramientas_modificacion = {"write_file", "edit_file", "copy_file", "move_file", "file_delete"}

# --- Umbrales anti-bucle del Codificador ---
# Tope máximo de iteraciones completas del Codificador. Se bajó de 15 a 10
# para converger antes con modelos de tool-calling poco fiables.
UMBRAL_MAX_ITERACIONES = 10
# Iteración desde la cual se fuerza tool_choice hacia una herramienta de
# escritura (write_file) para evitar que el modelo responda solo con texto.
UMBRAL_FORZAR_ESCRITURA = 3
# Iteración desde la cual, si el modelo responde texto plano sin tool_calls,
# se deriva una llamada write_file desde el contenido generado (evita agotar
# el presupuesto en reintentos sin escribir nada en disco).
UMBRAL_DERIVAR_ESCRITURA = 4

# Cadenas de confirmación de éxito que devuelven las herramientas de escritura en disco.
_confirmaciones_exito = (
    "escrito exitosamente",
    "editado exitosamente",
    "eliminado exitosamente",
    "Copiado de",
    "Movido de",
)


def _hubo_escritura_exitosa(msgs, respuesta) -> bool:
    """
    Determina si se ha realizado (o al menos invocado) una escritura física en disco.

    Retorna True si:
      (a) algún AIMessage en `msgs` o en `respuesta.tool_calls` invoca una herramienta
          del conjunto `herramientas_modificacion` Y esa invocación NO tiene un
          ToolMessage de error asociado (p.ej. 'Error al escribir el archivo'); O
      (b) algún ToolMessage en `msgs` contiene una cadena de confirmación de éxito
          en disco (p.ej. 'escrito exitosamente', 'editado exitosamente', 'Copiado de').

    El criterio (a) se refuerza con la resta de tool_call_ids con error: si el LLM
    invocó write_file/edit_file pero la herramienta devolvió un error (argumentos
    inválidos, ruta inexistente, etc.), esa invocación NO cuenta como escritura
    exitosa y el nodo no debe avanzar a revisión.
    """
    # Recopilar tool_call_ids de herramientas de modificación invocadas.
    ids_modificacion = set()
    for m in msgs:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                if tc.get("name") in herramientas_modificacion:
                    ids_modificacion.add(tc.get("id"))
    if respuesta.tool_calls:
        for tc in respuesta.tool_calls:
            if tc.get("name") in herramientas_modificacion:
                ids_modificacion.add(tc.get("id"))

    # Recopilar tool_call_ids de ToolMessages con error (las herramientas de
    # escritura devuelven mensajes que empiezan por 'Error').
    ids_error = set()
    for m in msgs:
        if isinstance(m, ToolMessage):
            content = str(m.content or "")
            if content.lower().startswith("error"):
                ids_error.add(m.tool_call_id)

    # (a) Herramienta de modificación invocada sin error asociado.
    if ids_modificacion - ids_error:
        return True

    # (b) Confirmación de éxito en disco en ToolMessages del historial.
    for m in msgs:
        if isinstance(m, ToolMessage):
            content = str(m.content or "")
            if any(kw in content for kw in _confirmaciones_exito):
                return True

    return False


@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    """
    Lista (con caché) las herramientas de manejo de archivos del directorio dado.

    Args:
        directorio: Ruta del directorio del proyecto (str).

    Returns:
        list: Herramientas de archivo configuradas para el directorio.
    """
    return get_custom_file_tools(directorio)

def agente_codificador(state: ProjectState) -> Command:
    """
    Ejecuta el agente codificador: lee el plan de acción, escribe los archivos en el disco duro y corrige errores si el Revisor (QA) los encuentra.

    Args:
        state: Estado global del proyecto (ProjectState).

    Returns:
        Command: Comando de LangGraph con la actualización de estado y el nodo destino.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > UMBRAL_MAX_ITERACIONES:
        # Registrar el aborto en errores_terminal: sin esto, el reporte final
        # del MCP mostraría "Sin errores" pese a que el flujo abortó por bucle.
        return Command(
            update={
                "errores_terminal": f"Abortado: el Agente Codificador excedió el límite máximo de {UMBRAL_MAX_ITERACIONES} iteraciones sin completar el plan (posible bucle). Revisar el plan y los errores previos.",
                "messages": [HumanMessage(content=f"Error: Se ha excedido el límite máximo de iteraciones ({UMBRAL_MAX_ITERACIONES}) en el Agente Codificador. El proceso se detiene para evitar un bucle infinito.")]
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_codigo = _get_tools(directorio)
    
    llm = get_coder_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    if loop_counter >= UMBRAL_FORZAR_ESCRITURA:
        # Anti-bucle: en iteraciones tardías se fuerza tool_choice hacia una
        # herramienta de escritura (write_file) para que el modelo no responda
        # solo con texto plano. Si el proveedor no soporta tool_choice, se
        # degrada sin error al binding normal.
        try:
            llm_con_herramientas = llm.bind_tools(
                herramientas_codigo + [CodigoCompletado],
                tool_choice="write_file",
            )
        except Exception:
            pass
    
    errores = state.get("errores_terminal", "")
    revision_count = state.get("revision_count", 0)
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    # Inyectar el índice del proyecto si está disponible en el estado (optimización de tokens)
    project_index = state.get("project_index")
    if project_index and isinstance(project_index, dict):
        from app.utils.project_index import extraer_archivos_relevantes, formatear_indice_para_prompt
        plan_estado = state.get("plan_de_accion")
        texto_fuentes = "\n".join(filter(None, [
            json.dumps(plan_estado, ensure_ascii=False, default=str) if plan_estado else "",
            str(state.get("analisis_final") or ""),
        ]))
        archivos_relevantes = extraer_archivos_relevantes(texto_fuentes, project_index)
        indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index, archivos_relevantes=archivos_relevantes))
        prompt_sistema += (
            "\n\n=== ÍNDICE DEL PROYECTO (proporcionado, usa read_file_summary para detalles) ===\n"
            f"{indice_texto}"
        )

    seccion_skills = cargar_skills_para_prompt(directorio, agente="codificador")
    if seccion_skills:
        prompt_sistema += "\n\n" + seccion_skills

    if errores:
        prompt_sistema += (
            f"\n\n ATENCIÓN: Tu código anterior falló las pruebas (Intento de revisión #{revision_count}). "
            f"Corrige los siguientes errores:\n{escapar_llaves(errores)}"
        )
        
    # Caché de template: si el prompt de sistema es idéntico al de la iteración
    # anterior, se reutiliza la instancia compilada (ahorro de trabajo redundante).
    prompt_template = construir_prompt_template_cacheado(prompt_sistema)
    
    plan = state.get("plan_de_accion", "Sin plan.")
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa programando según el plan.")]

    prompt = prompt_template.invoke({
        "messages": mensajes_contexto,
        "directorio": directorio,
        "plan": plan
    })
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        # Verificar si se ha realizado una escritura física en disco (herramienta de
        # modificación invocada o confirmación de éxito en un ToolMessage del historial).
        has_written_files = _hubo_escritura_exitosa(msgs, respuesta)

        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                if not has_written_files:
                    msg_error = "Error: No has modificado ni creado ningún archivo usando las herramientas de escritura (write_file, edit_file, copy_file, move_file, file_delete). Debes escribir el código correspondiente antes de llamar a 'CodigoCompletado'."
                    return Command(
                        update={
                            "messages": [respuesta, HumanMessage(content=msg_error)],
                            "loop_counter": loop_counter
                        },
                        goto="agente_codificador"
                    )

                resumen = _get_args(tool_call).get("resumen_cambios", "Código completado.") # pyright: ignore[reportArgumentType]
                
                tool_messages = []
                for tc in respuesta.tool_calls:
                    if tc["name"] == "CodigoCompletado":
                        content = f"Código guardado y listo para revisión: {resumen}"
                    else:
                        content = "Operación de archivo confirmada"
                    
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=tc["id"],
                            content=content,
                        )
                    )
                
                # --- Hook de regeneración de pruebas (anti-bucle) ---
                # Tras un cambio COMPLETADO en disco, evalúa si deben exigirse
                # pruebas actualizadas. Los archivos bajo tests/ y los contenidos
                # sin cambios reales (hash SHA-256) nunca re-disparan el mecanismo;
                # el cooldown y el tope de iteraciones impiden bucles infinitos.
                evaluacion = evaluar_regeneracion_tests(directorio, msgs, respuesta, state)
                if evaluacion["disparar"]:
                    archivos = ", ".join(evaluacion["archivos_modificados"])
                    msg_regeneracion = (
                        "Acción requerida: actualiza o crea las pruebas unitarias (pytest) para los "
                        f"siguientes archivos modificados: {archivos}. Escribe los tests en el directorio "
                        "'tests/' y verifica que pasan con pytest antes de llamar a CodigoCompletado de nuevo."
                    )
                    return Command(
                        update={
                            "codigo_escrito": resumen,
                            "errores_terminal": "",
                            "messages": [respuesta] + tool_messages + [HumanMessage(content=msg_regeneracion)],
                            "loop_counter": loop_counter,
                            "test_regeneration_count": int(state.get("test_regeneration_count") or 0) + 1,
                            "test_regeneration_hashes": evaluacion["hashes_actualizados"],
                            "test_regeneration_last_ts": evaluacion["last_ts"],
                        },
                        goto="agente_codificador"
                    )

                return Command(
                    update={
                        "codigo_escrito": resumen,
                        "errores_terminal": "",
                        "messages": [respuesta] + tool_messages,
                        "loop_counter": 0
                    },
                    goto="agente_revisor"
                )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_codificador"
        )
    else:
        # Respuesta de texto sin tool_calls. En iteraciones tempranas se reintenta
        # (nunca avanzar a revisión sin haber escrito archivos en disco). En
        # iteraciones tardías (UMBRAL_DERIVAR_ESCRITURA) se deriva una llamada
        # write_file desde el contenido generado para no agotar el presupuesto
        # en reintentos sin escribir nada en disco.
        contenido_texto = str(respuesta.content or "").strip()
        if loop_counter >= UMBRAL_DERIVAR_ESCRITURA and contenido_texto:
            # El texto del LLM es el mejor material disponible: se usa como
            # contenido del archivo principal del plan. Se deriva write_file
            # para que la escritura se ejecute físicamente en disco.
            plan_estado = state.get("plan_de_accion") or {}
            pasos = plan_estado.get("pasos") if isinstance(plan_estado, dict) else None
            archivo_objetivo = "main.py"
            if isinstance(pasos, list) and pasos:
                archivo_objetivo = pasos[0].get("archivo", "main.py") if isinstance(pasos[0], dict) else "main.py"
            tool_call_derivado = {
                "name": "write_file",
                "args": {"file_path": archivo_objetivo, "text": contenido_texto},
                "id": f"call_derivado_{loop_counter}",
            }
            return Command(
                update={
                    "messages": [respuesta, AIMessage(content="", tool_calls=[tool_call_derivado])],
                    "loop_counter": loop_counter
                },
                goto="nodo_herramientas_codificador"
            )

        msg = (
            "No has llamado a ninguna herramienta. DEBES llamar a una herramienta de escritura "
            "de archivos (write_file, edit_file, etc.) para implementar el plan, o llamar a "
            "CodigoCompletado si ya escribiste todos los archivos en disco."
        )
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=msg)],
                "loop_counter": loop_counter
            },
            goto="agente_codificador"
        )

def nodo_herramientas_codificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de manejo de archivos mediante ToolNode de LangGraph.

    Tras la ejecución de las herramientas (que pueden escribir archivos en disco), refresca automáticamente el índice del proyecto si está habilitado (PROJECT_INDEX_ENABLED=true), actualizando la clave 'project_index' del estado para que los agentes posteriores trabajen con un índice coherente.

    Args:
        state: Estado global del proyecto (ProjectState).
        config: Configuración de ejecución de LangGraph (RunnableConfig).

    Returns:
        dict: Resultado de la ejecución de las herramientas, con 'project_index' actualizado si el refresco fue exitoso.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    resultado = nodo.invoke(state, config=config)

    try:
        import os
        from app.settings.settings import Settings
        from app.utils.project_index import actualizar_indice_incremental

        if Settings().PROJECT_INDEX_ENABLED and os.path.isdir(directorio):
            indice_actualizado = actualizar_indice_incremental(directorio, state.get("project_index"))
            if isinstance(resultado, dict):
                return {**resultado, "project_index": indice_actualizado}
    except Exception:
        # Si el refresco del índice falla, devolvemos el resultado original sin
        # interrumpir el flujo normal de ejecución de las herramientas.
        pass

    return resultado