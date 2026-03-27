import os
from langchain_community.utilities import SearxSearchWrapper
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

# ==========================================
# 2. LA ESTRUCTURA DEL PLAN (Pydantic)
# ==========================================
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
    
    # 1. Obtenemos la ruta dinámica desde el estado (Agnóstico al editor)
    directorio = state.get("directorio_proyecto", "./")
    
    # 2. Configuramos las herramientas de lectura (restringidas al directorio)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    # 3. Configuramos la búsqueda gratuita con SearxNG
    searx = SearxSearchWrapper(searx_host="http://127.0.0.1:8888", k=2)
    tool_busqueda = Tool(
        name="busqueda_web_searx",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    
    # Unimos las herramientas de investigación
    herramientas_investigacion = herramientas_lectura + [tool_busqueda]
    
    # 4. Configuramos el LLM
    llm = get_llm(temperature=0.0)
    
    # EL TRUCO DE LANGGRAPH: Le pasamos las herramientas de investigación 
    # Y TAMBIÉN el modelo Pydantic (PlanDeAccion) como si fuera una herramienta más.
    llm_con_herramientas = llm.bind_tools(herramientas_investigacion + [PlanDeAccion])
    
    # 5. Construimos el Prompt
    prompt_sistema = fileSystem.get_file_content(file_name="planificador_prompt.md")
    
    # Preparamos los mensajes (Historial + Prompt)
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # Si es el primer turno (no hay mensajes previos), inyectamos la instrucción del usuario
    if not state["messages"]:
        mensajes.append(HumanMessage(content=state["instruccion_usuario"]))
        
    # 6. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    # ==========================================
    # 7. ENRUTAMIENTO DINÁMICO (Command)
    # ==========================================
    # Verificamos si el LLM decidió entregar el plan final
    if respuesta.tool_calls and respuesta.tool_calls[0]["name"] == "PlanDeAccion":
        # Extraemos los argumentos que generó el LLM (que coinciden con nuestro Pydantic)
        plan_generado = respuesta.tool_calls[0]["args"]
        
        return Command(
            update={"plan_de_accion": plan_generado}, # Guardamos el plan en el Estado
            goto="agente_codificador"                 # ¡Terminó! Pasamos el turno al Codificador
        )
    
    # Si no entregó el plan, significa que decidió usar read_file, list_directory o searx
    else:
        return Command(
            update={"messages": [respuesta]},         # Guardamos la intención de usar la herramienta
            goto="nodo_herramientas_planificador"     # Lo enviamos al nodo que ejecuta las herramientas
        )

def nodo_herramientas_planificador(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    # 1. Inicializamos las herramientas dinámicamente para esta ruta
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "list_directory"]}
    
    searx = SearxSearchWrapper(searx_host="http://127.0.0.1:8888")
    herramientas["busqueda_web_searx"] = Tool(name="busqueda_web_searx", func=searx.run, description="")
    
    # 2. Obtenemos las herramientas que el LLM pidió usar
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        # 3. Ejecutamos la herramienta y guardamos el resultado
        if nombre in herramientas:
            resultado = herramientas[nombre].invoke(args)
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={"messages": respuestas_tools},
        goto="agente_planificador" # Regresamos el control al Planificador para que lea el resultado
    )