from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings

settings = Settings()
fileSystem = File(directory="prompts")

@tool
def finalizar_documentacion(resumen: str) -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de documentar el código.
    Describe brevemente qué archivos de documentación se crearon o modificaron.
    """
    return f"Documentación finalizada: {resumen}"

def agente_documentador(state: ProjectState) -> Command:
    """
    Analiza el código final y genera la documentación necesaria.
    """
    directorio = state.get("directorio_proyecto", "./")
    
    # 1. Configuramos las herramientas de archivos (lectura y escritura)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_archivos = [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "write_file", "list_directory"]
    ]
    
    # Unimos las herramientas
    herramientas_documentador = herramientas_archivos + [finalizar_documentacion]
    
    # 2. Configuramos el LLM
    from app.settings.settings import get_llm
    llm = get_llm(temperature=0.2)
    llm_con_herramientas = llm.bind_tools(herramientas_documentador)
    
    # 3. Construimos el Prompt del Sistema
    prompt_raw = fileSystem.get_file_content(file_name="documentador_prompt.md")
    prompt_sistema = prompt_raw.format(directorio=directorio)
    
    # Manejo de Resumen (Summarization)
    resumen_previo = state.get("summary", "")
    if resumen_previo:
        prompt_sistema += f"\n\n**Resumen de la conversación anterior:**\n{resumen_previo}"
    
    # Preparamos los mensajes
    mensajes = [SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 4. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            # Si el agente decide que ya terminó...
            if tool_call["name"] == "finalizar_documentacion":
                return Command(
                    update={"messages": [respuesta]},
                    goto=END
                )
        
        # Si está usando herramientas de archivos...
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_documentador"
        )
        
    else:
        # Forzamos al agente a seguir si responde solo con texto
        return Command(
            update={
                "messages": [respuesta],
                "proximo_paso": "agente_documentador"
            },
            goto="summarize_messages"
        )

def nodo_herramientas_documentador(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "write_file", "list_directory"]}
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools = []
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas:
            resultado = herramientas[nombre].invoke(args)
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={
            "messages": respuestas_tools,
            "proximo_paso": "agente_documentador"
        },
        goto="summarize_messages"
    )
