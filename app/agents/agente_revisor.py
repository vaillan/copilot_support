from langgraph.types import Command
from langchain_core.messages import AIMessage, ToolMessage
from langchain_community.tools import ShellTool
from langchain_core.tools import tool
from app.models.models import ProjectState
from app.settings.settings import get_llm
from app.utils.agent_factory import get_base_tools, prepare_messages, create_tool_node

@tool
def finalizar_revision(aprobado: bool, reporte_errores: str = "") -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de probar el código.
    - Si el código falla o tiene errores de sintaxis, pon aprobado=False y detalla los errores en 'reporte_errores'.
    - Si el código pasa todas las pruebas y es perfecto, pon aprobado=True.
    """
    return "Revisión procesada."

def get_herramientas_revisor(directorio: str):
    """Configura las herramientas para el revisor."""
    terminal = ShellTool()
    terminal.name = "terminal"
    
    herramientas_lectura = get_base_tools(directorio, ["read_file", "list_directory"])
    return [terminal, finalizar_revision] + herramientas_lectura

def agente_revisor(state: ProjectState) -> Command:
    """Ejecuta el código en la terminal y valida el resultado."""
    directorio = state.get("directorio_proyecto", "./")
    herramientas = get_herramientas_revisor(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas)
    
    mensajes = prepare_messages(
        state=state,
        prompt_name="revisor_prompt.md",
        format_kwargs={
            "directorio": directorio,
            "codigo_escrito": state.get("codigo_escrito", "Sin reporte.")
        }
    )
    
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                errores = tool_call["args"].get("reporte_errores", "")
                
                proximo = "agente_documentador" if aprobado else "agente_codificador"
                reporte = "Ninguno. Código aprobado." if aprobado else errores
                
                return Command(
                    update={
                        "errores_terminal": reporte,
                        "messages": [respuesta, ToolMessage(content=f"Revisión finalizada. Aprobado: {aprobado}", tool_call_id=tool_call["id"])]
                    },
                    goto=proximo
                )
        
        return Command(update={"messages": [respuesta]}, goto="nodo_herramientas_revisor")
        
    mensaje_seguimiento = "Entiendo tu análisis. Por favor, procede a verificar el código usando las herramientas disponibles o finaliza la revisión."
    return Command(
        update={"messages": [respuesta, AIMessage(content=mensaje_seguimiento)]},
        goto="agente_revisor"
    )

nodo_herramientas_revisor = create_tool_node(get_herramientas_revisor, "agente_revisor")
