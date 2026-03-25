import os
from typing import List, Dict, Any, Callable, Optional
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import BaseTool
from app.models.models import ProjectState
from app.settings.settings import Settings, get_llm
from app.utils.files import File

settings = Settings()
prompt_manager = File(directory="prompts")

def get_base_tools(directorio: str, tool_names: List[str]) -> List[BaseTool]:
    """
    Obtiene herramientas de gestión de archivos filtradas por nombre.
    """
    abs_path = os.path.abspath(directorio)
    toolkit = FileManagementToolkit(root_dir=abs_path)
    return [t for t in toolkit.get_tools() if t.name in tool_names]

def prepare_messages(state: ProjectState, prompt_name: str, format_kwargs: Dict[str, Any]) -> List[Any]:
    """
    Carga un prompt, lo formatea y construye la lista de mensajes.
    """
    prompt_raw = prompt_manager.get_file_content(file_name=prompt_name)
    prompt_sistema = prompt_raw.format(**format_kwargs)
    
    mensajes = [SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # Inyectar instrucción de usuario si no hay mensajes previos
    if not state["messages"] and state.get("instruccion_usuario"):
        mensajes.append(HumanMessage(content=state["instruccion_usuario"]))
        
    return mensajes

def handle_tool_calls(ultimo_mensaje: Any, herramientas_map: Dict[str, BaseTool]) -> List[ToolMessage]:
    """
    Ejecuta las llamadas a herramientas solicitadas por un mensaje de IA.
    """
    respuestas_tools = []
    if not hasattr(ultimo_mensaje, "tool_calls") or not ultimo_mensaje.tool_calls:
        return respuestas_tools

    for tool_call in ultimo_mensaje.tool_calls:
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas_map:
            try:
                # Manejo especial para ShellTool si es necesario
                if nombre == "terminal":
                    comando = args.get("commands") or args.get("query") or args
                    resultado = herramientas_map[nombre].invoke(comando)
                else:
                    resultado = herramientas_map[nombre].invoke(args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
            
            respuestas_tools.append(ToolMessage(
                content=str(resultado), 
                tool_call_id=tool_call["id"], 
                name=nombre
            ))
        else:
            respuestas_tools.append(ToolMessage(
                content=f"Error: La herramienta '{nombre}' no está disponible para este agente.",
                tool_call_id=tool_call["id"],
                name=nombre
            ))
            
    return respuestas_tools

def create_tool_node(get_tools_func: Callable[[str], List[BaseTool]], goto_agent: str) -> Callable[[ProjectState], Command]:
    """
    Crea un nodo de herramientas genérico que inyecta el directorio dinámicamente.
    """
    def tool_node(state: ProjectState) -> Command:
        directorio = state.get("directorio_proyecto", "./")
        herramientas_map = {t.name: t for t in get_tools_func(directorio)}
        respuestas_tools = handle_tool_calls(state["messages"][-1], herramientas_map)
        return Command(update={"messages": respuestas_tools}, goto=goto_agent)
    
    return tool_node
