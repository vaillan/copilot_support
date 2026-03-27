from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import SystemMessage
from app.models.llm_factory import get_llm
from langchain_community.tools import ShellTool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings

settings = Settings()
fileSystem = File(directory="prompts")

# ==========================================
# 1. HERRAMIENTA PERSONALIZADA (@tool)
# ==========================================
@tool
def finalizar_revision(aprobado: bool, reporte_errores: str = "") -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de probar el código.
    - Si el código falla o tiene errores de sintaxis, pon aprobado=False y detalla los errores en 'reporte_errores'.
    - Si el código pasa todas las pruebas y es perfecto, pon aprobado=True.
    """
    return "Revisión procesada."

# ==========================================
# 2. FUNCIÓN DEL AGENTE REVISOR
# ==========================================
def agente_revisor(state: ProjectState) -> Command:
    """
    El Tester ejecuta el código en la terminal. Si hay errores, 
    devuelve el flujo al Codificador. Si todo está bien, termina el proceso.
    """
    directorio = state.get("directorio_proyecto", "./")
    
    # 1. Herramienta de Terminal (ShellTool)
    terminal = ShellTool()
    
    # 2. Herramienta de Lectura (FileManagementToolkit)
    # Útil por si los tests generan un archivo 'coverage.xml' o 'error.log'
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura =[
        t for t in toolkit_archivos.get_tools() 
        if t.name == "read_file"
    ]
    
    # Unimos todas las herramientas del QA
    herramientas_qa =[terminal, finalizar_revision] + herramientas_lectura
    
    # 3. Configuramos el LLM
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_qa)
    
    # 4. Construimos el Prompt del Sistema
    prompt_sistema = fileSystem.get_file_content(file_name="revisor_prompt.md")
    
    # Preparamos los mensajes
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 5. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    # ==========================================
    # 6. ENRUTAMIENTO DINÁMICO (El Bucle de Feedback)
    # ==========================================
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            # Si el agente decide que ya terminó de evaluar...
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                errores = tool_call["args"].get("reporte_errores", "")
                
                if aprobado:
                    # ÉXITO: El código funciona. Terminamos el Grafo.
                    return Command(
                        update={"errores_terminal": "Ninguno. Código aprobado."},
                        goto=END # Importado de langgraph.graph
                    )
                else:
                    # FALLO: Hay errores. Devolvemos el control al Codificador.
                    return Command(
                        update={"errores_terminal": errores},
                        goto="agente_codificador" # ¡Viaje en el tiempo hacia atrás!
                    )
        
        # Si no llamó a finalizar_revision, significa que está usando la terminal o leyendo logs
        return Command(
            update={"messages":[respuesta]},
            goto="nodo_herramientas_revisor" # Lo enviamos a ejecutar el comando bash
        )
        
    else:
        # Forzamos al agente a seguir en su loop si responde solo con texto
        return Command(
            update={"messages": [respuesta]},
            goto="agente_revisor"
        )

def nodo_herramientas_revisor(state: ProjectState) -> Command:
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name == "read_file"}
    
    # Agregamos la terminal
    terminal = ShellTool()
    herramientas["terminal"] = terminal
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        # Nota: La herramienta 'finalizar_revision' no se ejecuta aquí, 
        # porque el Agente Revisor ya la interceptó en su propia función para hacer el enrutamiento.
        if nombre in herramientas:
            resultado = herramientas[nombre].invoke(args)
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={"messages": respuestas_tools},
        goto="agente_revisor" # Regresamos el control al Revisor
    )