from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import SystemMessage
from langchain_community.tools import ShellTool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings

settings = Settings()
fileSystem = File(directory="prompts")

@tool
def finalizar_revision(aprobado: bool, reporte_errores: str = "") -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de probar el código.
    - Si el código falla o tiene errores de sintaxis, pon aprobado=False y detalla los errores en 'reporte_errores'.
    - Si el código pasa todas las pruebas y es perfecto, pon aprobado=True.
    """
    return "Revisión procesada."

def agente_revisor(state: ProjectState) -> Command:
    """
    El Tester ejecuta el código en la terminal. Si hay errores, 
    devuelve el flujo al Codificador. Si todo está bien, termina el proceso.
    """
    directorio = state.get("directorio_proyecto", "./")
    
    # 1. Herramienta de Terminal (ShellTool)
    terminal = ShellTool()
    terminal.name = "terminal"
    
    # 2. Herramienta de Lectura (FileManagementToolkit)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura =[
        t for t in toolkit_archivos.get_tools() 
        if t.name == "read_file"
    ]
    
    # Unimos todas las herramientas del QA
    herramientas_qa =[terminal, finalizar_revision] + herramientas_lectura
    
    # 3. Configuramos el LLM
    from app.settings.settings import get_llm
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_qa)
    
    # 4. Construimos el Prompt del Sistema
    prompt_raw = fileSystem.get_file_content(file_name="revisor_prompt.md")
    prompt_sistema = prompt_raw.format(
        directorio=directorio,
        codigo_escrito=state.get("codigo_escrito", "Sin reporte.")
    )
    
    # Manejo de Resumen (Summarization)
    resumen = state.get("summary", "")
    if resumen:
        prompt_sistema += f"\n\n**Resumen de la conversación anterior:**\n{resumen}"
    
    # Preparamos los mensajes
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 5. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            # Si el agente decide que ya terminó de evaluar...
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                errores = tool_call["args"].get("reporte_errores", "")
                
                if aprobado:
                    # ÉXITO: El código funciona. Pasamos al Documentador (via resumidor).
                    return Command(
                        update={
                            "errores_terminal": "Ninguno. Código aprobado.",
                            "proximo_paso": "agente_documentador"
                        },
                        goto="summarize_messages"
                    )
                else:
                    # FALLO: Hay errores. Devolvemos el control al Codificador (via resumidor).
                    return Command(
                        update={
                            "errores_terminal": errores,
                            "proximo_paso": "agente_codificador"
                        },
                        goto="summarize_messages"
                    )
        
        # Si no llamó a finalizar_revision, significa que está usando la terminal o leyendo logs
        return Command(
            update={"messages":[respuesta]},
            goto="nodo_herramientas_revisor"
        )
        
    else:
        # Forzamos al agente a seguir en su loop si responde solo con texto
        return Command(
            update={
                "messages": [respuesta],
                "proximo_paso": "agente_revisor"
            },
            goto="summarize_messages"
        )

def nodo_herramientas_revisor(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name == "read_file"}
    
    # Agregamos la terminal
    terminal = ShellTool()
    terminal.name = "terminal"
    herramientas["terminal"] = terminal
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas:
            try:
                # Aseguramos que los argumentos para terminal sean tratados correctamente
                input_args = args.get("commands", args) if isinstance(args, dict) and nombre == "terminal" else args
                resultado = herramientas[nombre].invoke(input_args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
            
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={
            "messages": respuestas_tools,
            "proximo_paso": "agente_revisor"
        },
        goto="summarize_messages"
    )
