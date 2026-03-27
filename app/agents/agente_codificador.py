from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.messages import SystemMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.messages import ToolMessage
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings

settings = Settings()
fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

def agente_codificador(state: ProjectState) -> Command:
    """
    El Programador lee el plan de acción, escribe los archivos en el disco duro
    y corrige errores si el Revisor (QA) los encuentra.
    """
    # 1. Obtenemos la ruta dinámica desde el estado
    directorio = state.get("directorio_proyecto", "./")
    
    # 2. Configuramos las herramientas nativas de escritura y lectura
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    
    # Filtramos SOLO las herramientas que el codificador necesita (lectura, escritura y búsqueda)
    herramientas_codigo =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in["read_file", "write_file", "list_directory"]
    ]
    
    # 3. Configuramos el LLM
    from app.settings.settings import get_llm
    llm = get_llm(temperature=0.0)
    
    # Le "atamos" las herramientas de archivos + la herramienta de finalización
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    
    # 4. Extraemos el contexto del Estado
    plan = state.get("plan_de_accion", {})
    errores = state.get("errores_terminal", "")
    
    # 5. Construimos el Prompt del Sistema
    prompt_raw = fileSystem.get_file_content(file_name="codificador_prompt.md")
    prompt_sistema = prompt_raw.format(
        directorio=directorio,
        plan=plan
    )
    
    # Manejo de Resumen (Summarization)
    resumen = state.get("summary", "")
    if resumen:
        prompt_sistema += f"\n\n**Resumen de la conversación anterior:**\n{resumen}"
    
    # CICLO DE AUTOCORRECCIÓN: Si el Revisor encontró errores, se los inyectamos aquí
    if errores:
        prompt_sistema += f"\n\n ATENCIÓN: Tu código anterior falló las pruebas. Corrige los siguientes errores:\n{errores}"
        
    # Preparamos los mensajes
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 6. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)

    if respuesta.tool_calls:
        # Buscamos si el LLM decidió que ya terminó su trabajo
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen_codigo = tool_call["args"].get("resumen_cambios", "Código completado.")
                
                return Command(
                    update={
                        "codigo_escrito": resumen_codigo,
                        "errores_terminal": "",
                        "proximo_paso": "agente_revisor"
                    },
                    goto="summarize_messages"      
                )
        
        # Si no llamó a CodigoCompletado, significa que usó write_file o read_file
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_codificador"
        )
        
    else:
        # Si el LLM responde solo con texto, lo forzamos a seguir en su loop pero pasando por summarizer
        return Command(
            update={
                "messages": [respuesta],
                "proximo_paso": "agente_codificador"
            },
            goto="summarize_messages"
        )

def nodo_herramientas_codificador(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "write_file", "list_directory"]}
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    # 2. Identificar si todas las herramientas llamadas son de "lectura" para evitar el HITL
    todas_lectura = True
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        # Si usa write_file, ya no es solo lectura
        if nombre == "write_file":
            todas_lectura = False
            
        if nombre in herramientas:
            try:
                resultado = herramientas[nombre].invoke(args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
            
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    # Si todas fueron lectura y la configuración lo permite, vamos al nodo "silent" para no pedir permiso
    if todas_lectura and not settings.HITL_ASK_FOR_READ:
        proximo = "agente_codificador_silent"
    else:
        proximo = "agente_codificador"
            
    return Command(
        update={
            "messages": respuestas_tools,
            "proximo_paso": proximo
        },
        goto="summarize_messages"
    )
