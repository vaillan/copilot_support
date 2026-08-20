from pydantic import BaseModel, Field
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.graph import END
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.prebuilt import ToolNode
from langchain_core.runnables import RunnableConfig
from app.utils.files import File, get_custom_file_tools
from app.models.models import ProjectState
from app.models.llm_factory import get_coder_llm
from app.utils.summarization import aplicar_resumen_middleware
from app.utils.prompt_utils import escapar_llaves
from functools import lru_cache

fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

# Conjunto de herramientas que realizan una escritura física en disco.
herramientas_modificacion = {"write_file", "edit_file", "copy_file", "move_file", "file_delete"}

# Cadenas de confirmación de éxito que devuelven las herramientas de escritura en disco.
_confirmaciones_exito = (
    "escrito exitosamente",
    "editado exitosamente",
    "eliminado exitosamente",
    "Copiado de",
    "Movido de",
)


def _hubo_escritura_exitosa(msgs, respuesta) -> bool:
    """
    Determina si se ha realizado (o al menos invocado) una escritura física en disco.

    Retorna True si:
      (a) algún AIMessage en `msgs` o en `respuesta.tool_calls` invoca una herramienta
          del conjunto `herramientas_modificacion`; O
      (b) algún ToolMessage en `msgs` contiene una cadena de confirmación de éxito
          en disco (p.ej. 'escrito exitosamente', 'editado exitosamente', 'Copiado de').
    """
    # (a) Herramienta de modificación invocada en el historial o en la respuesta actual
    for m in msgs:
        if isinstance(m, AIMessage) and m.tool_calls:
            if any(tc.get("name") in herramientas_modificacion for tc in m.tool_calls):
                return True
    if respuesta.tool_calls:
        if any(tc.get("name") in herramientas_modificacion for tc in respuesta.tool_calls):
            return True

    # (b) Confirmación de éxito en disco en ToolMessages del historial
    for m in msgs:
        if isinstance(m, ToolMessage):
            content = m.content or ""
            if any(kw in content for kw in _confirmaciones_exito):
                return True

    return False


@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    return get_custom_file_tools(directorio)

def agente_codificador(state: ProjectState) -> Command:
    """
    El Programador lee el plan de acción, escribe los archivos en el disco duro
    y corrige errores si el Revisor (QA) los encuentra.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > 15:
        return Command(
            update={
                "messages": [HumanMessage(content="Error: Se ha excedido el límite máximo de iteraciones (15) en el Agente Codificador. El proceso se detiene para evitar un bucle infinito.")]
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_codigo = _get_tools(directorio)
    
    llm = get_coder_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado])
    
    errores = state.get("errores_terminal", "")
    revision_count = state.get("revision_count", 0)
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    # Inyectar el índice del proyecto si está disponible en el estado (optimización de tokens)
    project_index = state.get("project_index")
    if project_index and isinstance(project_index, dict):
        from app.utils.project_index import formatear_indice_para_prompt
        indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index))
        prompt_sistema += (
            "\n\n=== ÍNDICE DEL PROYECTO (proporcionado, usa read_file_summary para detalles) ===\n"
            f"{indice_texto}"
        )
    
    if errores:
        prompt_sistema += (
            f"\n\n ATENCIÓN: Tu código anterior falló las pruebas (Intento de revisión #{revision_count}). "
            f"Corrige los siguientes errores:\n{escapar_llaves(errores)}"
        )
        
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    plan = state.get("plan_de_accion", "Sin plan.")
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa programando según el plan.")]

    prompt = prompt_template.invoke({
        "messages": mensajes_contexto,
        "directorio": directorio,
        "plan": plan
    })
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        # Verificar si se ha realizado una escritura física en disco (herramienta de
        # modificación invocada o confirmación de éxito en un ToolMessage del historial).
        has_written_files = _hubo_escritura_exitosa(msgs, respuesta)

        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                if not has_written_files:
                    msg_error = "Error: No has modificado ni creado ningún archivo usando las herramientas de escritura (write_file, edit_file, copy_file, move_file, file_delete). Debes escribir el código correspondiente antes de llamar a 'CodigoCompletado'."
                    return Command(
                        update={
                            "messages": [respuesta, HumanMessage(content=msg_error)],
                            "loop_counter": loop_counter
                        },
                        goto="agente_codificador"
                    )

                resumen = tool_call["args"].get("resumen_cambios", "Código completado.")
                
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
                        "messages": [respuesta] + tool_messages,
                        "loop_counter": 0
                    },
                    goto="agente_revisor"
                )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_codificador"
        )
    else:
        # Respuesta de texto sin tool_calls: SIEMPRE reintentar. Nunca avanzar a revisión
        # sin haber escrito archivos en disco (evita el bug de "revisión sin código").
        msg = (
            "No has llamado a ninguna herramienta. DEBES llamar a una herramienta de escritura "
            "de archivos (write_file, edit_file, etc.) para implementar el plan, o llamar a "
            "CodigoCompletado si ya escribiste todos los archivos en disco."
        )
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=msg)],
                "loop_counter": loop_counter
            },
            goto="agente_codificador"
        )

def nodo_herramientas_codificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de manejo de archivos utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state, config=config)