import os
from typing import List
from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.tools import Tool
from langchain_community.utilities import SearxSearchWrapper
from app.models.models import ProjectState
from app.settings.settings import Settings, get_llm
from app.utils.agent_factory import get_base_tools, prepare_messages, handle_tool_calls, create_tool_node

settings = Settings()

class Paso(BaseModel):
    archivo: str = Field(description="Ruta relativa del archivo a modificar o crear")
    tarea: str = Field(description="Descripción técnica de lo que el codificador debe programar")
    requiere_test: bool = Field(description="True si este paso necesita una prueba unitaria")

class PlanDeAccion(BaseModel):
    explicacion_arquitectura: str = Field(description="Breve explicación del enfoque técnico")
    pasos: List[Paso]

def get_investigacion_tools(directorio: str):
    """Configura las herramientas de investigación para el planificador."""
    herramientas_lectura = get_base_tools(directorio, ["read_file", "list_directory"])
    
    searx = SearxSearchWrapper(searx_host=settings.SEARXNG_HOST, k=2) # type: ignore
    tool_busqueda = Tool(
        name="busqueda_web_searx",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    return herramientas_lectura + [tool_busqueda]

def agente_planificador(state: ProjectState) -> Command:
    """Analiza el requerimiento, investiga el proyecto/internet y genera un plan."""
    directorio = state.get("directorio_proyecto", "./")
    herramientas = get_investigacion_tools(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas + [PlanDeAccion])
    
    mensajes = prepare_messages(
        state=state, 
        prompt_name="planificador_prompt.md", 
        format_kwargs={"directorio": os.path.abspath(directorio)}
    )
    
    print(f"[DEBUG Planificador] Invocando agente con {len(mensajes)} mensajes...")
    respuesta = llm_con_herramientas.invoke(mensajes)

    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "PlanDeAccion":
                plan_generado = tool_call["args"]
                print(f"[DEBUG Planificador] Plan generado con {len(plan_generado.get('pasos', []))} pasos.")
                return Command(
                    update={"plan_de_accion": plan_generado, "messages": [respuesta]}, 
                    goto="agente_codificador"                 
                )
        
        return Command(update={"messages": [respuesta]}, goto="nodo_herramientas_planificador")
    
    return Command(update={"messages": [respuesta]}, goto="agente_planificador")

nodo_herramientas_planificador = create_tool_node(get_investigacion_tools, "agente_planificador")
