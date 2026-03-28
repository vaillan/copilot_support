import os
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.agent_toolkits import FileManagementToolkit
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain_core.tools import Tool
from app.settings.settings import Settings
from app.models.llm_factory import get_llm
from app.models.models import ProjectState
from app.utils.files import File

settings = Settings()
fileSystem = File(directory="prompts")

class Paso(BaseModel):
    archivo: str = Field(description="Ruta relativa del archivo a modificar o crear")
    tarea: str = Field(description="Descripción técnica de lo que el codificador debe programar")
    requiere_test: bool = Field(description="True si este paso necesita una prueba unitaria")

class PlanDeAccion(BaseModel):
    explicacion_arquitectura: str = Field(description="Breve explicación del enfoque técnico")
    pasos: List[Paso]


def agente_planificador(state: ProjectState) -> Command:
    """
    Analiza el requerimiento, investiga el proyecto/internet y genera un plan.
    """
    
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    searx = DuckDuckGoSearchAPIWrapper()
    tool_busqueda = Tool(
        name="busqueda_web_duckduckgo",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    
    herramientas_investigacion = herramientas_lectura + [tool_busqueda]
    
    llm = get_llm(temperature=0.0)
    
    llm_con_herramientas = llm.bind_tools(herramientas_investigacion + [PlanDeAccion])
    
    prompt_sistema = fileSystem.get_file_content(file_name="planificador_prompt.md")
    
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
        
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls and respuesta.tool_calls[0]["name"] == "PlanDeAccion": # type: ignore
        plan_generado = respuesta.tool_calls[0]["args"] # type: ignore
        
        return Command(
            update={"plan_de_accion": plan_generado},
            goto="agente_codificador"
        )
    
    else:
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_planificador"
        )

def nodo_herramientas_planificador(state: ProjectState) -> Command:
    """
    Ejecuta las herramientas de investigación (lectura de archivos, listado de directorios y búsqueda web) 
    solicitadas por el planificador.
    
    Procesa las llamadas a herramientas en el último mensaje del estado, las ejecuta 
    y devuelve los resultados al agente planificador para que continúe con el análisis.
    
    Args:
        state (ProjectState): El estado actual del proyecto.
        
    Returns:
        Command: Un comando de LangGraph que actualiza los mensajes y redirige al agente planificador.
    """
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "list_directory"]}
    
    searx = DuckDuckGoSearchAPIWrapper()
    herramientas["busqueda_web_duckduckgo"] = Tool(name="busqueda_web_duckduckgo", func=searx.run, description="Búsqueda web con DuckDuckGo")
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas:
            resultado = herramientas[nombre].invoke(args)
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={"messages": respuestas_tools},
        goto="agente_planificador"
    )