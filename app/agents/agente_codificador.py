from pydantic import BaseModel, Field
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from app.models.models import ProjectState
from app.settings.settings import get_llm
from app.utils.agent_factory import get_base_tools, prepare_messages, create_tool_node

# Configuración de herramientas del codificador
HERRAMIENTAS_CODIGO = ["write_file", "delete_file", "move_file", "copy_file", "read_file", "list_directory", "file_search"]

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

def get_herramientas_codificador(directorio: str):
    """Helper para obtener las herramientas configuradas para un directorio."""
    return get_base_tools(directorio, HERRAMIENTAS_CODIGO)

def agente_codificador(state: ProjectState) -> Command:
    """El Programador lee el plan de acción, escribe los archivos y corrige errores."""
    directorio = state.get("directorio_proyecto", "./")
    herramientas = get_herramientas_codificador(directorio)
    
    llm = get_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas + [CodigoCompletado])
    
    mensajes = prepare_messages(
        state=state,
        prompt_name="codificador_prompt.md",
        format_kwargs={
            "directorio": directorio,
            "plan": state.get("plan_de_accion", {})
        }
    )
    
    # Ciclo de autocorrección: si hay errores los inyectamos al final del historial
    if errores := state.get("errores_terminal"):
        aviso_error = f"ATENCIÓN: Tu código anterior falló las pruebas. Corrige los siguientes errores:\n{errores}"
        mensajes.append(HumanMessage(content=aviso_error))
        
    respuesta = llm_con_herramientas.invoke(mensajes)

    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                resumen_codigo = tool_call["args"].get("resumen_cambios", "Código completado.")
                return Command(
                    update={"codigo_escrito": resumen_codigo, "errores_terminal": ""},
                    goto="agente_revisor"      
                )
        
        return Command(update={"messages": [respuesta]}, goto="nodo_herramientas_codificador")
        
    # Aviso si no se usó ninguna herramienta
    aviso_no_tool = "Has respondido sin usar ninguna herramienta. Si aún no has terminado el plan, por favor utiliza las herramientas de archivos o finaliza con CodigoCompletado."
    return Command(
        update={"messages": [respuesta, HumanMessage(content=aviso_no_tool)]},
        goto="agente_codificador"
    )

nodo_herramientas_codificador = create_tool_node(get_herramientas_codificador, "agente_codificador")
