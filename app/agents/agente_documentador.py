import os
from langgraph.graph import END
from langgraph.types import Command
from langchain_core.tools import tool
from app.models.models import ProjectState
from app.settings.settings import get_llm
from app.utils.agent_factory import get_base_tools, prepare_messages, create_tool_node

@tool
def finalizar_documentacion(resumen: str) -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de documentar el código.
    Describe brevemente qué archivos de documentación se crearon o modificaron.
    """
    return f"Documentación finalizada: {resumen}"

def get_herramientas_documentador(directorio: str):
    """Configura las herramientas para el documentador."""
    herramientas_archivos = get_base_tools(directorio, ["read_file", "write_file", "list_directory"])
    return herramientas_archivos + [finalizar_documentacion]

def agente_documentador(state: ProjectState) -> Command:
    """Analiza el código final y genera la documentación necesaria."""
    directorio = state.get("directorio_proyecto", "./")
    herramientas = get_herramientas_documentador(directorio)
    
    llm = get_llm(temperature=0.2)
    llm_con_herramientas = llm.bind_tools(herramientas)
    
    mensajes = prepare_messages(
        state=state,
        prompt_name="documentador_prompt.md",
        format_kwargs={"directorio": os.path.abspath(directorio)}
    )
    
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        # Si el único tool call es finalizar_documentacion, terminamos
        if len(respuesta.tool_calls) == 1 and respuesta.tool_calls[0]["name"] == "finalizar_documentacion":
            return Command(update={"messages": [respuesta]}, goto=END)
        
        return Command(update={"messages": [respuesta]}, goto="nodo_herramientas_documentador")
        
    return Command(update={"messages": [respuesta]}, goto="agente_documentador")

nodo_herramientas_documentador = create_tool_node(get_herramientas_documentador, "agente_documentador")
