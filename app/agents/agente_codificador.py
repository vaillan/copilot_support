from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.agent_toolkits import FileManagementToolkit
from langgraph.prebuilt import ToolNode
from app.utils.files import File
from app.models.models import ProjectState
from app.settings.settings import Settings
from app.models.llm_factory import get_llm

settings = Settings()
fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

def _get_tools(directorio: str):
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    return [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "write_file"]
    ]

def agente_codificador(state: ProjectState) -> Command:
    """
    El Programador lee el plan de acción, escribe los archivos en el disco duro
    y corrige errores si el Revisor (QA) los encuentra.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas_codigo = _get_tools(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    
    errores = state.get("errores_terminal", "")
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    if errores:
        prompt_sistema += f"\n\n ATENCIÓN: Tu código anterior falló las pruebas. Corrige los siguientes errores:\n{errores}"
        
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    cadena = prompt_template | llm_con_herramientas
    respuesta = cadena.invoke({"messages": state["messages"]})
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen = tool_call["args"].get("resumen_cambios", "Código completado.")
                
                return Command(
                    update={
                        "codigo_escrito": resumen,
                        "errores_terminal": ""
                    },
                    goto="agente_revisor"
                )
        
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_codificador"
        )
    else:
        return Command(
            update={"messages": [respuesta]},
            goto="agente_codificador"
        )

def nodo_herramientas_codificador(state: ProjectState):
    """
    Ejecuta las herramientas de manejo de archivos utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state)
