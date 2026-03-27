from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.messages import SystemMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.messages import ToolMessage
from app.utils.files import File
from app.models.models import ProjectState
from app.settings.settings import Settings
from app.models.llm_factory import get_llm

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
    
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    
    # Filtramos SOLO las herramientas que el codificador necesita
    herramientas_codigo =[
        t for t in toolkit_archivos.get_tools() 
        if t.name in["read_file", "write_file"]
    ]
    
    llm = get_llm(temperature=0.0)
    
    # Le "atamos" las herramientas de archivos + la herramienta de finalización
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    
    plan = state.get("plan_de_accion", {})
    errores = state.get("errores_terminal", "")
    
    # Prompt del Sistema
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    # CICLO DE AUTOCORRECCIÓN: Si el Revisor encontró errores, se los inyectamos aquí
    if errores:
        prompt_sistema += f"\n\n ATENCIÓN: Tu código anterior falló las pruebas. Corrige los siguientes errores:\n{errores}"
        
    mensajes =[SystemMessage(content=prompt_sistema)] + state["messages"]
    
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        # Buscamos si el LLM decidió que ya terminó su trabajo
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen = tool_call["args"].get("resumen_cambios", "Código completado.")
                
                return Command(
                    update={
                        "codigo_escrito": resumen,
                        "errores_terminal": "" # Limpiamos los errores pasados porque ya los intentó arreglar
                    },
                    goto="agente_revisor"      # ¡Terminó! Pasamos el turno al QA (Revisor)
                )
        
        # Si no llamó a CodigoCompletado, significa que usó write_file o read_file
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_codificador" # Lo enviamos al nodo que ejecuta las herramientas de código
        )
        
    else:
        # Si el LLM responde solo con texto (sin usar herramientas), lo forzamos a seguir en su loop
        return Command(
            update={"messages": [respuesta]},
            goto="agente_codificador"
        )

def nodo_herramientas_codificador(state: ProjectState) -> Command:
    """
    Ejecuta las herramientas de manejo de archivos (lectura y escritura) solicitadas por el codificador.
    
    Procesa las llamadas a herramientas presentes en el último mensaje del estado,
    ejecuta la acción correspondiente en el sistema de archivos y devuelve los
    resultados al agente codificador.
    
    Args:
        state (ProjectState): El estado actual del proyecto.
        
    Returns:
        Command: Un comando de LangGraph que actualiza los mensajes y redirige al agente codificador.
    """
    directorio = state.get("directorio_proyecto", "./")
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "write_file"]}
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools =[]
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        if nombre in herramientas:
            resultado = herramientas[nombre].invoke(args)
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
            
    return Command(
        update={"messages": respuestas_tools},
        goto="agente_codificador" # Regresamos el control al Codificador
    )