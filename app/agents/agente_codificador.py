from pydantic import BaseModel, Field
from langchain_core.messages import ToolMessage, HumanMessage
from langgraph.types import Command
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.agent_toolkits import FileManagementToolkit
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from app.utils.files import File
from app.models.models import ProjectState
from app.models.llm_factory import get_llm
from functools import lru_cache
import os

fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas = [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "write_file"]
    ]
    
    @tool
    def replace_in_file(file_path: str, search_string: str, replace_string: str) -> str:
        """
        Lee un archivo, busca una cadena de texto exacta y la reemplaza por otra.
        Útil para modificar bloques específicos de código sin sobrescribir todo el archivo.
        """
        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(directorio, file_path)
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if search_string not in content:
                return f"Error: La cadena de búsqueda no se encontró en el archivo {file_path}."
                
            new_content = content.replace(search_string, replace_string)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return f"Reemplazo exitoso en {file_path}."
        except Exception as e:
            return f"Error al modificar el archivo: {str(e)}"
            
    herramientas.append(replace_in_file)
    return herramientas

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
        prompt_sistema += (
            f"\n\n ATENCIÓN: Tu código anterior falló las pruebas. "
            f"Corrige los siguientes errores:\n{errores}"
        )
        
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    plan = state.get("plan_de_accion", "Sin plan.")
    prompt = prompt_template.invoke({
        "messages": state["messages"], 
        "directorio": directorio, 
        "plan": plan
    })
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen = tool_call["args"].get("resumen_cambios", "Código completado.")
                
                # Bug fix: Attach ToolMessages for each tool_call
                tool_messages = []
                for tc in respuesta.tool_calls:
                    if tc["name"] == "CodigoCompletado":
                        content = f"Código guardado y listo para revisión: {resumen}"
                    else:
                        content = "Operación de archivo confirmada"
                    
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=tc["id"],
                            content=content,
                        )
                    )
                
                return Command(
                    update={
                        "codigo_escrito": resumen,
                        "errores_terminal": "",
                        "messages": [respuesta] + tool_messages
                    },
                    goto="agente_revisor"
                )
        
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_codificador"
        )
    else:
        # Bug fix: Avoid infinite loop
        msg = "Debes llamar a una herramienta para escribir código o llamar a CodigoCompletado si ya terminaste."
        return Command(
            update={"messages": [respuesta, HumanMessage(content=msg)]},
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
