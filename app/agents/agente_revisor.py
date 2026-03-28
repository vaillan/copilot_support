from langgraph.graph import END
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.models.llm_factory import get_llm
from langchain_community.tools import ShellTool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
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

def _get_tools(directorio: str):
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_lectura = [
        t for t in toolkit_archivos.get_tools() 
        if t.name == "read_file"
    ]
    terminal = ShellTool()
    return [terminal, finalizar_revision] + herramientas_lectura

def agente_revisor(state: ProjectState) -> Command:
    """
    El Tester ejecuta el código en la terminal. Si hay errores, 
    devuelve el flujo al Codificador. Si todo está bien, termina el proceso.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas_qa = _get_tools(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_qa)
    
    prompt_sistema = fileSystem.get_file_content(file_name="revisor_prompt.md")
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    cadena = prompt_template | llm_con_herramientas
    respuesta = cadena.invoke({"messages": state["messages"]})
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "finalizar_revision":
                aprobado = tool_call["args"].get("aprobado", False)
                errores = tool_call["args"].get("reporte_errores", "")
                
                if aprobado:
                    return Command(
                        update={"errores_terminal": "Ninguno. Código aprobado."},
                        goto=END
                    )
                else:
                    return Command(
                        update={"errores_terminal": errores},
                        goto="agente_codificador"
                    )
        
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_revisor"
        )
    else:
        return Command(
            update={"messages": [respuesta]},
            goto="agente_revisor"
        )

def nodo_herramientas_revisor(state: ProjectState):
    """
    Ejecuta las herramientas de revisión utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    # Excluimos finalizar_revision del ToolNode porque la manejamos manualmente en el agente
    herramientas_ejecutables = [t for t in herramientas if t.name != "finalizar_revision"]
    nodo = ToolNode(herramientas_ejecutables)
    return nodo.invoke(state)
