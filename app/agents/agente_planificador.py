import os
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from langchain_core.tools import Tool
from langchain_community.utilities import SearxSearchWrapper
from langchain_community.agent_toolkits import FileManagementToolkit
from app.models.models import ProjectState
from app.settings.settings import Settings, get_llm
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
    directorio_base = state.get("directorio_proyecto", "./")
    directorio = os.path.abspath(directorio_base)
    
    # 2. Configuramos las herramientas de lectura (restringidas al directorio)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura = [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    # 3. Configuramos la búsqueda con SearxNG
    searx = SearxSearchWrapper(searx_host=settings.SEARXNG_HOST, k=2) # type: ignore
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
    prompt_raw = fileSystem.get_file_content(file_name="planificador_prompt.md")
    prompt_sistema = prompt_raw.format(directorio=directorio)
    
    # Preparamos los mensajes (Historial + Prompt)
    mensajes = [SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # Si es el primer turno (no hay mensajes previos), inyectamos la instrucción del usuario
    if not state["messages"]:
        mensajes.append(HumanMessage(content=state.get("instruccion_usuario", "")))
        
    # 6. Invocamos al modelo
    print(f"[DEBUG Planificador] Invocando agente con {len(mensajes)} mensajes...")
    respuesta = llm_con_herramientas.invoke(mensajes)

    # Verificamos si el LLM decidió entregar el plan final (Buscamos PlanDeAccion en tool_calls)
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "PlanDeAccion":
                # Extraemos los argumentos que generó el LLM
                plan_generado = tool_call["args"]
                print(f"[DEBUG Planificador] Plan generado con {len(plan_generado.get('pasos', []))} pasos.")
                
                proximo = "agente_codificador"
                
                return Command(
                    update={
                        "plan_de_accion": plan_generado,
                        "messages": [respuesta]
                    }, 
                    goto=proximo                 
                )
        
        # Si no entregó el plan, significa que decidió usar read_file, list_directory o searx
        print(f"[DEBUG Planificador] El agente solicitó {len(respuesta.tool_calls)} herramientas.")
        return Command(
            update={"messages": [respuesta]},         # Guardamos la intención de usar la herramienta
            goto="nodo_herramientas_planificador"     # Lo enviamos al nodo que ejecuta las herramientas
        )
    
    # Si no hay tool_calls, el agente respondió con texto plano
    else:
        print("[DEBUG Planificador] Respuesta en texto plano, reintentando...")
        return Command(
            update={
                "messages": [respuesta]
            },
            goto="agente_planificador"
        )

def nodo_herramientas_planificador(state: ProjectState) -> Command:
    directorio_base = state.get("directorio_proyecto", "./")
    directorio = os.path.abspath(directorio_base)
    
    # 1. Inicializamos las herramientas dinámicamente para esta ruta
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "list_directory"]}
    
    searx = SearxSearchWrapper(searx_host=settings.SEARXNG_HOST)
    herramientas["busqueda_web_searx"] = Tool(
        name="busqueda_web_searx", 
        func=searx.run, 
        description="Busca en internet documentación técnica actualizada."
    )
    
    # 2. Obtenemos las herramientas que el LLM pidió usar
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools = []
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        print(f"[DEBUG Planificador Tools] Ejecutando: {nombre} con args: {args}")
        
        # 3. Ejecutamos la herramienta y guardamos el resultado
        if nombre in herramientas:
            try:
                # Extraemos el string de búsqueda si args es un diccionario
                input_args = args.get("query", args) if isinstance(args, dict) and nombre == "busqueda_web_searx" else args
                resultado = herramientas[nombre].invoke(input_args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
                print(f"[DEBUG Planificador Tools] Error: {resultado}")
                
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
        else:
            print(f"[DEBUG Planificador Tools] Herramienta desconocida: {nombre}")
            
    return Command(
        update={
            "messages": respuestas_tools
        },
        goto="agente_planificador" 
    )
