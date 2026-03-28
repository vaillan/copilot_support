import os
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.agent_toolkits import FileManagementToolkit
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.types import Command
from langchain_core.tools import Tool
from langgraph.prebuilt import ToolNode
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

def _get_tools(directorio: str):
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura = [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    searx = DuckDuckGoSearchAPIWrapper()
    tool_busqueda = Tool(
        name="busqueda_web_duckduckgo",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    return herramientas_lectura + [tool_busqueda]

def agente_planificador(state: ProjectState) -> Command:
    """
    Analiza el requerimiento, investiga el proyecto/internet y genera un plan.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas_investigacion = _get_tools(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_investigacion + [PlanDeAccion])
    
    prompt_sistema = fileSystem.get_file_content(file_name="planificador_prompt.md")
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    cadena = prompt_template | llm_con_herramientas
    respuesta = cadena.invoke({"messages": state["messages"], "directorio": directorio})
    
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

def nodo_herramientas_planificador(state: ProjectState):
    """
    Ejecuta las herramientas de investigación utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state)
