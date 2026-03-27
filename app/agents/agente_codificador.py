from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings, get_llm

settings = Settings()
fileSystem = File(directory="prompts")

# Herramientas de escritura y gestión de archivos
HERRAMIENTAS_ESCRITURA = ["write_file", "delete_file", "move_file", "copy_file"]
# Herramientas de lectura y exploración
HERRAMIENTAS_LECTURA = ["read_file", "list_directory", "file_search"]
# Todas las herramientas permitidas para el codificador
NOMBRES_HERRAMIENTAS = HERRAMIENTAS_ESCRITURA + HERRAMIENTAS_LECTURA

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

def get_herramientas_codificador(directorio: str):
    """Helper para obtener las herramientas configuradas para un directorio."""
    toolkit = FileManagementToolkit(root_dir=directorio)
    return [t for t in toolkit.get_tools() if t.name in NOMBRES_HERRAMIENTAS]

def agente_codificador(state: ProjectState) -> Command:
    """
    El Programador lee el plan de acción, escribe los archivos en el disco duro
    y corrige errores si el Revisor (QA) los encuentra.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas_codigo = get_herramientas_codificador(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    
    plan = state.get("plan_de_accion", {})
    errores = state.get("errores_terminal", "")
    
    prompt_raw = fileSystem.get_file_content(file_name="codificador_prompt.md")
    prompt_sistema = prompt_raw.format(
        directorio=directorio,
        plan=plan
    )
    
    mensajes = [SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # CICLO DE AUTOCORRECCIÓN: Si el Revisor encontró errores, se los inyectamos como HumanMessage
    if errores:
        aviso_error = f"ATENCIÓN: Tu código anterior falló las pruebas. Corrige los siguientes errores:\n{errores}"
        mensajes.append(HumanMessage(content=aviso_error))
        
    respuesta = llm_con_herramientas.invoke(mensajes)

    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen_codigo = tool_call["args"].get("resumen_cambios", "Código completado.")
                
                return Command(
                    update={
                        "codigo_escrito": resumen_codigo,
                        "errores_terminal": ""
                    },
                    goto="agente_revisor"      
                )
        
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_codificador"
        )
        
    else:
        # Validación: Si no hay tool_calls, inyectamos un aviso para evitar bucles sin acción
        aviso_no_tool = "Has respondido sin usar ninguna herramienta. Si aún no has terminado el plan, por favor utiliza las herramientas de archivos necesarias (read_file, write_file, etc.) o finaliza con CodigoCompletado."
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=aviso_no_tool)]
            },
            goto="agente_codificador"
        )

def nodo_herramientas_codificador(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    herramientas_lista = get_herramientas_codificador(directorio)
    herramientas_map = {t.name: t for t in herramientas_lista}
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools = []
    
    todas_lectura = True
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in HERRAMIENTAS_ESCRITURA:
            todas_lectura = False
            
        if nombre in herramientas_map:
            try:
                resultado = herramientas_map[nombre].invoke(args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
            
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    if todas_lectura and not settings.HITL_ASK_FOR_READ:
        proximo = "agente_codificador_silent"
    else:
        proximo = "agente_codificador"
            
    return Command(
        update={
            "messages": respuestas_tools
        },
        goto=proximo
    )
