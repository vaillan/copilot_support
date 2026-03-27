from langchain_community.utilities import SearxSearchWrapper
from langchain_community.agent_toolkits import FileManagementToolkit
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain_core.tools import Tool
from app.models.models import ProjectState
from app.settings.settings import Settings
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
    
    # 1. Obtenemos la ruta dinámica desde el estado (Agnóstico al editor)
    directorio = state.get("directorio_proyecto", "./")
    
    # 2. Configuramos las herramientas de lectura (restringidas al directorio)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    # 3. Configuramos la búsqueda gratuita con SearxNG
    searx = SearxSearchWrapper(searx_host=settings.SEARXNG_HOST, k=2) # type: ignore
    tool_busqueda = Tool(
        name="busqueda_web_searx",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    
    # Unimos las herramientas de investigación
    herramientas_investigacion = herramientas_lectura + [tool_busqueda]
    
    # 4. Configuramos el LLM
    from app.settings.settings import get_llm
    llm = get_llm(temperature=0.0)
    
    # EL TRUCO DE LANGGRAPH: Le pasamos las herramientas de investigación 
    # Y TAMBIÉN el modelo Pydantic (PlanDeAccion) como si fuera una herramienta más.
    llm_con_herramientas = llm.bind_tools(herramientas_investigacion + [PlanDeAccion])
    
    # 5. Construimos el Prompt
    prompt_raw = fileSystem.get_file_content(file_name="planificador_prompt.md")
    prompt_sistema = prompt_raw.format(directorio=directorio)
    
    # Manejo de Resumen (Summarization)
    resumen = state.get("summary", "")
    if resumen:
        prompt_sistema += f"\n\n**Resumen de la conversación anterior:**\n{resumen}"
    
    # Preparamos los mensajes (Historial + Prompt)
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # Si es el primer turno (no hay mensajes previos), inyectamos la instrucción del usuario
    if not state["messages"]:
        mensajes.append(HumanMessage(content=state["instruccion_usuario"]))
        
    # 6. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)

    # Verificamos si el LLM decidió entregar el plan final (Buscamos PlanDeAccion en tool_calls)
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "PlanDeAccion":
                # Extraemos los argumentos que generó el LLM
                plan_generado = tool_call["args"]
                
                from app.settings.settings import settings
                proximo = "agente_codificador_silent" if not settings.HITL_ASK_FOR_READ else "agente_codificador"
                
                return Command(
                    update={
                        "plan_de_accion": plan_generado,
                        "proximo_paso": proximo # Destino tras resumir
                    }, 
                    goto="summarize_messages"                 
                )
        
        # Si no entregó el plan, significa que decidió usar read_file, list_directory o searx
        return Command(
            update={"messages": [respuesta]},         # Guardamos la intención de usar la herramienta
            goto="nodo_herramientas_planificador"     # Lo enviamos al nodo que ejecuta las herramientas
        )
    
    # Si no hay tool_calls, el agente respondió con texto plano
    else:
        return Command(
            update={
                "messages": [respuesta],
                "proximo_paso": "agente_planificador"
            },
            goto="summarize_messages"
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
            try:
                # Extraemos el string de búsqueda si args es un diccionario
                input_args = args.get("query", args) if isinstance(args, dict) and nombre == "busqueda_web_searx" else args
                resultado = herramientas[nombre].invoke(input_args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
                
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={
            "messages": respuestas_tools,
            "proximo_paso": "agente_planificador"
        },
        goto="summarize_messages" 
    )
