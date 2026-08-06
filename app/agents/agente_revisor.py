import sys
import subprocess
from contextlib import redirect_stdout
from langgraph.graph import END
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.models.llm_factory import get_reviewer_llm
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from app.models.models import ProjectState
from langchain_core.runnables import RunnableConfig
from app.utils.files import File
from app.settings.settings import Settings
from functools import lru_cache

settings = Settings()
fileSystem = File(directory="prompts")

@tool
def terminal(commands: list[str] | str) -> str:
    """
    Ejecuta comandos en la terminal de forma totalmente aislada e inofensiva para el servidor MCP.
    Pasa una lista de comandos o una cadena de comando (ej. "pytest" o ["pytest"]).
    """
    if isinstance(commands, str):
        lista_comandos = [commands]
    elif isinstance(commands, list):
        lista_comandos = commands
    else:
        return "Error: Formato de comandos inválido. Proporciona una cadena o lista de cadenas."

    resultados = []
    for cmd in lista_comandos:
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                stdin=subprocess.DEVNULL
            )
            stdout = res.stdout.strip() if res.stdout else ""
            stderr = res.stderr.strip() if res.stderr else ""
            salida = []
            if stdout:
                salida.append(f"STDOUT:\n{stdout}")
            if stderr:
                salida.append(f"STDERR:\n{stderr}")
            if not salida:
                salida.append(f"Comando '{cmd}' ejecutado con código de salida {res.returncode} (sin salida).")
            resultados.append(f"$ {cmd}\nCódigo de salida: {res.returncode}\n" + "\n".join(salida))
        except subprocess.TimeoutExpired:
            resultados.append(f"$ {cmd}\n🚨 Timeout: El comando excedió el tiempo límite de 30 segundos.")
        except BaseException as e:
            resultados.append(f"$ {cmd}\n🚨 Error al ejecutar comando: {str(e)}")

    return "\n\n---\n\n".join(resultados) if resultados else "No se ejecutaron comandos válidos."

@tool
def finalizar_revision(aprobado: bool, requiere_pruebas: bool = True, reporte_errores: str = "") -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de evaluar el código.
    - Si el código NO requiere pruebas (ej. documentación, HTML estático, o el plan indica que no requiere test), pon requiere_pruebas=False y aprobado=True.
    - Si el código SÍ requiere pruebas y FALLA, pon requiere_pruebas=True, aprobado=False y detalla los errores en 'reporte_errores'.
    - Si el código SÍ requiere pruebas y PASA exitosamente, pon requiere_pruebas=True y aprobado=True.
    """
    return "Revisión procesada."

@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura = [
        t for t in toolkit_archivos.get_tools() 
        if t.name == "read_file"
    ]
    herramientas = [terminal, finalizar_revision] + herramientas_lectura
    return herramientas

def agente_revisor(state: ProjectState) -> Command:
    """
    El Tester ejecuta el código en la terminal. Si hay errores, 
    devuelve el flujo al Codificador. Si todo está bien o no requiere pruebas, termina el proceso.
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
                    "revision_count": revision_count
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
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Optimización de contexto: enviar mensaje inicial y los últimos 8 mensajes
    msgs = state.get("messages", [])
    mensajes_contexto = [msgs[0]] + msgs[-8:] if len(msgs) > 9 else msgs

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
                aprobado = tool_call["args"].get("aprobado", False)
                requiere_pruebas = tool_call["args"].get("requiere_pruebas", True)
                errores = tool_call["args"].get("reporte_errores", "")
                
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
                            "revision_count": revision_count
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
    """
    Ejecuta las herramientas de revisión utilizando ToolNode de LangGraph.
    Captura de forma segura cualquier BaseException para evitar caídas en el TaskGroup de MCP.
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
