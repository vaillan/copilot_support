from langgraph.types import Command
from langchain_core.messages import SystemMessage, AIMessage
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
    
    # 2. Herramientas de Archivos (FileManagementToolkit)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_seleccionadas =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "list_directory"]
    ]
    
    # Unimos todas las herramientas del QA
    herramientas_qa =[terminal, finalizar_revision] + herramientas_seleccionadas
    
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
    
    # Preparamos los mensajes
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 5. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        # Buscamos si llamó a finalizar_revision en alguna de las llamadas
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                errores = tool_call["args"].get("reporte_errores", "")
                
                if aprobado:
                    # ÉXITO: El código funciona. Pasamos al Documentador.
                    return Command(
                        update={
                            "errores_terminal": "Ninguno. Código aprobado.",
                            "messages": [respuesta, ToolMessage(content="Revisión finalizada y aprobada.", tool_call_id=tool_call["id"])]
                        },
                        goto="agente_documentador"
                    )
                else:
                    # FALLO: Hay errores. Devolvemos el control al Codificador.
                    return Command(
                        update={
                            "errores_terminal": errores,
                            "messages": [respuesta, ToolMessage(content=f"Revisión finalizada con errores: {errores}", tool_call_id=tool_call["id"])]
                        },
                        goto="agente_codificador"
                    )
        
        # Si no llamó a finalizar_revision o llamó a otras herramientas además, vamos al nodo de herramientas
        return Command(
            update={"messages":[respuesta]},
            goto="nodo_herramientas_revisor"
        )
        
    else:
        # Manejo de respuesta sin herramientas (evitar bucle infinito de texto)
        mensaje_seguimiento = "Entiendo tu análisis. Por favor, procede a verificar el código usando las herramientas disponibles o finaliza la revisión si ya has terminado."
        return Command(
            update={
                "messages": [respuesta, AIMessage(content=mensaje_seguimiento)]
            },
            goto="agente_revisor"
        )

def nodo_herramientas_revisor(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "list_directory"]}
    
    # Agregamos la terminal
    terminal = ShellTool()
    terminal.name = "terminal"
    herramientas["terminal"] = terminal
    
    # Agregamos finalizar_revision para que no falle si viene en el grupo
    herramientas["finalizar_revision"] = finalizar_revision
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas:
            try:
                # Robustez de ShellTool: manejar tanto "commands" como "query" o el dict entero
                if nombre == "terminal":
                    comando = args.get("commands") or args.get("query") or args
                    resultado = herramientas[nombre].invoke(comando)
                else:
                    resultado = herramientas[nombre].invoke(args)
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
            
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"]))
        else:
            # Herramienta no reconocida: devolver error al modelo
            respuestas_tools.append(ToolMessage(
                content=f"Error: La herramienta '{nombre}' no es reconocida por el revisor.",
                tool_call_id=tool_call["id"]
            ))
            
    return Command(
        update={
            "messages": respuestas_tools
        },
        goto="agente_revisor"
    )
