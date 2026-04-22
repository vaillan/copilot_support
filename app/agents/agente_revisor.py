from langgraph.graph import END
from langchain_core.messages import ToolMessage, HumanMessage
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.models.llm_factory import get_llm
from langchain_community.tools import ShellTool
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
    terminal = ShellTool()
    herramientas = [terminal, finalizar_revision] + herramientas_lectura
    return herramientas

def agente_revisor(state: ProjectState) -> Command:
    """
    El Tester ejecuta el código en la terminal. Si hay errores, 
    devuelve el flujo al Codificador. Si todo está bien o no requiere pruebas, termina el proceso.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > 15:
        return Command(
            update={
                "messages":[HumanMessage(content="Error: Se ha excedido el límite máximo de iteraciones (15) en el Agente Revisor. El proceso se detiene para evitar un bucle infinito.")]
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_qa = _get_tools(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_qa)
    
    prompt_sistema = fileSystem.get_file_content(file_name="revisor_prompt.md")
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Pasamos el plan de acción para que el QA sepa si el planificador exigió pruebas
    prompt = prompt_template.invoke({
        "messages": state["messages"], 
        "directorio": directorio, 
        "codigo_escrito": state.get("codigo_escrito", "Sin reporte."),
        "plan": state.get("plan_de_accion", "Sin plan.")
    })
    
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                requiere_pruebas = tool_call["args"].get("requiere_pruebas", True)
                errores = tool_call["args"].get("reporte_errores", "")
                
                tool_messages =[
                    ToolMessage(
                        tool_call_id=tc["id"],
                        content="Revisión finalizada con éxito." if tc["name"] == "finalizar_revision" else "Operación completada",
                    )
                    for tc in respuesta.tool_calls
                ]
                
                # NUEVA LÓGICA: Si no requiere pruebas, terminamos el bucle directamente
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
                                "messages": [respuesta] + tool_messages +[HumanMessage(content="Se ha alcanzado el límite máximo de 3 revisiones. El proceso se detiene.")],
                                "loop_counter": loop_counter,
                                "revision_count": revision_count
                            },
                            goto=END
                        )
                    
                    return Command(
                        update={
                            "errores_terminal": errores,
                            "messages":[respuesta] + tool_messages,
                            "loop_counter": 0,
                            "revision_count": revision_count
                        },
                        goto="agente_codificador"
                    )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_revisor"
        )
    else:
        return Command(
            update={
                "messages":[respuesta, HumanMessage(content="Debes llamar a una herramienta para probar el código o llamar a finalizar_revision si ya terminaste o si el código no requiere pruebas.")],
                "loop_counter": loop_counter
            },
            goto="agente_revisor"
        )

def nodo_herramientas_revisor(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de revisión utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    herramientas_ejecutables = [t for t in herramientas if t.name != "finalizar_revision"]
    nodo = ToolNode(herramientas_ejecutables)
    return nodo.invoke(state, config=config)
