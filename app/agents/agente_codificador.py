import json
from typing import Any, Dict, List, Optional, Tuple
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
from app.utils.skills_loader import cargar_skills_para_prompt
from functools import lru_cache
from app.utils.args_utils import _get_args
from app.utils.plan_progress import avanzar_progreso, construir_contexto_compacto, construir_ledger, parsear_pasos_plan

fileSystem = File(directory="prompts")

class CodigoCompletado(BaseModel):
    """Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan."""
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")

class MarcarPasoCompletado(BaseModel):
    """Registra que el paso actual del plan quedó implementado y verificado."""
    numero_paso: int = Field(description="Número del paso del plan que quedó completo.")

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
    """
    Lista (con caché) las herramientas de manejo de archivos del directorio dado.

    Args:
        directorio: Ruta del directorio del proyecto (str).

    Returns:
        list: Herramientas de archivo configuradas para el directorio.
    """
    return get_custom_file_tools(directorio)

def agente_codificador(state: ProjectState) -> Command:
    """
    Ejecuta el agente codificador: lee el plan de acción, escribe los archivos en el disco duro y corrige errores si el Revisor (QA) los encuentra.

    Args:
        state: Estado global del proyecto (ProjectState).

    Returns:
        Command: Comando de LangGraph con la actualización de estado y el nodo destino.
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
    llm_con_herramientas = llm.bind_tools(herramientas_codigo + [CodigoCompletado, MarcarPasoCompletado])
    
    errores = state.get("errores_terminal", "")
    revision_count = state.get("revision_count", 0)
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    # Inyectar el índice del proyecto si está disponible en el estado (optimización de tokens)
    project_index = state.get("project_index")
    if project_index and isinstance(project_index, dict):
        from app.utils.project_index import extraer_archivos_relevantes, formatear_indice_para_prompt
        plan_estado = state.get("plan_de_accion")
        texto_fuentes = "\n".join(filter(None, [
            json.dumps(plan_estado, ensure_ascii=False, default=str) if plan_estado else "",
            str(state.get("analisis_final") or ""),
        ]))
        archivos_relevantes = extraer_archivos_relevantes(texto_fuentes, project_index)
        indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index, archivos_relevantes=archivos_relevantes))
        prompt_sistema += (
            "\n\n=== ÍNDICE DEL PROYECTO (proporcionado, usa read_file_summary para detalles) ===\n"
            f"{indice_texto}"
        )

    seccion_skills = cargar_skills_para_prompt(directorio, agente="codificador")
    if seccion_skills:
        prompt_sistema += "\n\n" + seccion_skills

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

    # Ledger de progreso + cuerpo del paso actual inyectados como contexto compacto,
    # regenerado en cada iteración desde el estado (sobrevive a la sumarización).
    contexto_compacto = construir_contexto_compacto(plan, state.get("progreso_plan"))
    plan_para_prompt = contexto_compacto if contexto_compacto is not None else plan

    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa programando según el plan.")]

    prompt = prompt_template.invoke({
        "messages": mensajes_contexto,
        "directorio": directorio,
        "plan": plan_para_prompt
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

                resumen = _get_args(tool_call).get("resumen_cambios", "Código completado.") # pyright: ignore[reportArgumentType]
                
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

def _procesar_llamadas_progreso(state: ProjectState, llamadas: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[ToolMessage]]:
    """
    Actualiza progreso_plan de forma determinista y genera los ToolMessage de las llamadas de progreso.
    """
    total = len(parsear_pasos_plan(state.get("plan_de_accion")))
    progreso = state.get("progreso_plan")
    tool_msgs: List[ToolMessage] = []

    for tc in llamadas:
        numero_paso = _get_args(tc).get("numero_paso")
        if total <= 0:
            tool_msgs.append(ToolMessage(
                tool_call_id=tc["id"],
                content="No se pudo parsear el plan de acción; el progreso no se registra.",
            ))
        elif not isinstance(numero_paso, int) or not (1 <= numero_paso <= total):
            tool_msgs.append(ToolMessage(
                tool_call_id=tc["id"],
                content=f"Paso {numero_paso} fuera de rango (1-{total}); no se registró progreso.",
            ))
        else:
            progreso = avanzar_progreso(progreso, numero_paso, total)
            tool_msgs.append(ToolMessage(
                tool_call_id=tc["id"],
                content=f"Paso {numero_paso} registrado como completado. {construir_ledger(progreso)}",
            ))

    return progreso, tool_msgs


def _refrescar_indice(resultado: Dict[str, Any], directorio: str, state: ProjectState) -> Dict[str, Any]:
    """
    Refresca project_index tras escritura en disco si PROJECT_INDEX_ENABLED está activo; silencia errores.
    """
    try:
        import os
        from app.settings.settings import Settings
        from app.utils.project_index import actualizar_indice_incremental

        if Settings().PROJECT_INDEX_ENABLED and os.path.isdir(directorio):
            indice_actualizado = actualizar_indice_incremental(directorio, state.get("project_index"))
            return {**resultado, "project_index": indice_actualizado}
    except Exception:
        pass

    return resultado


def nodo_herramientas_codificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas del codificador, registra el progreso del plan y actualiza el índice del proyecto.

    Args:
        state: Estado global del proyecto (ProjectState).
        config: Configuración de ejecución de LangGraph (RunnableConfig).

    Returns:
        dict: Resultado de la ejecución de las herramientas, con 'project_index' actualizado si el refresco fue exitoso.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)

    # Separar las tool_calls de progreso: nunca llegan al ToolNode (no escriben en disco).
    ultimo_ai = None
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage) and m.tool_calls:
            ultimo_ai = m
            break

    tool_calls = ultimo_ai.tool_calls if ultimo_ai is not None else []
    llamadas_progreso = [tc for tc in tool_calls if isinstance(tc, dict) and tc.get("name") == "MarcarPasoCompletado"]
    llamadas_archivo = [tc for tc in tool_calls if not (isinstance(tc, dict) and tc.get("name") == "MarcarPasoCompletado")]

    # Flujo normal sin llamadas de progreso: comportamiento idéntico al original.
    if not llamadas_progreso:
        return _refrescar_indice(nodo.invoke(state, config=config), directorio, state)

    progreso_final, tool_msgs = _procesar_llamadas_progreso(state, llamadas_progreso)

    if llamadas_archivo:
        # Reconstruir la última AIMessage solo con las llamadas que sí escriben en disco.
        estado_filtrado = {
            **{k: v for k, v in state.items() if k != "messages"},
            "messages": [
                m if m is not ultimo_ai else AIMessage(content=ultimo_ai.content, tool_calls=llamadas_archivo, id=ultimo_ai.id)
                for m in state.get("messages", [])
            ],
        }
        resultado = _refrescar_indice(nodo.invoke(estado_filtrado, config=config), directorio, state)
        return {
            **resultado,
            "messages": list(resultado.get("messages", [])) + tool_msgs,
            "progreso_plan": progreso_final,
        }

    # Solo llamadas de progreso: sin escritura en disco, sin refresco de índice.
    return {"messages": tool_msgs, "progreso_plan": progreso_final}