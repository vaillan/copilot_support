from typing import Dict, List, Optional, Tuple

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from app.models.llm_factory import get_llm

# Memoización del resumen por ids de mensajes para no repetir la llamada LLM
# en cada iteración del grafo cuando el historial no cambió.
_CACHE_RESUMEN: Dict[Tuple, List[AnyMessage]] = {}
_CACHE_RESUMEN_MAX = 32


def _ids_tool_calls_de_ai(mensaje: AIMessage) -> List[str]:
    """Ids de tool_calls de un AIMessage (parseado, additional_kwargs e invalid) deduplicados."""
    ids: List[str] = []
    fuentes = [
        getattr(mensaje, "tool_calls", None) or [],
        (getattr(mensaje, "additional_kwargs", None) or {}).get("tool_calls") or [],
        getattr(mensaje, "invalid_tool_calls", None) or [],
    ]
    for fuente in fuentes:
        for tc in fuente:
            cid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            if cid:
                ids.append(cid)
    return list(dict.fromkeys(ids))


def sanitizar_pares_tool_call(messages: List[AnyMessage]) -> List[AnyMessage]:
    """
    Elimina AIMessages con tool_calls huérfanos y ToolMessages sin respuesta.

    Conserva un AIMessage solo si todas sus tool_calls tienen su ToolMessage;
    conserva un ToolMessage solo si su tool_call_id fue solicitado por un AIMessage.
    """
    ids_solicitados: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            ids_solicitados.update(_ids_tool_calls_de_ai(m))
    ids_con_respuesta = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}

    resultado: List[AnyMessage] = []
    for m in messages:
        if isinstance(m, ToolMessage):
            if m.tool_call_id in ids_solicitados:
                resultado.append(m)
        elif isinstance(m, AIMessage):
            ids_m = _ids_tool_calls_de_ai(m)
            if not ids_m or all(cid in ids_con_respuesta for cid in ids_m):
                resultado.append(m)
        else:
            resultado.append(m)
    return resultado


def _clave_resumen(messages: List[AnyMessage]) -> Optional[Tuple]:
    """Devuelve la tupla de ids de mensajes, o None si ninguno tiene id."""
    ids = tuple(getattr(m, "id", None) for m in messages)
    return ids if any(ids) else None


def aplicar_resumen_middleware(messages: List[AnyMessage], model=None, trigger_count: int = 15, keep_count: int = 8) -> List[AnyMessage]:
    """
    Aplica SummarizationMiddleware para resumir el historial al superar el umbral.

    El resumen se memoiza por ids de mensajes y el resultado se sanitiza para
    eliminar pares tool_call/ToolMessage huérfanos tras el resumen.
    """
    if not messages or len(messages) <= trigger_count:
        return sanitizar_pares_tool_call(messages)

    clave = _clave_resumen(messages)
    if clave is not None and clave in _CACHE_RESUMEN:
        return _CACHE_RESUMEN[clave]

    if model is None:
        model = get_llm()

    try:
        mw = SummarizationMiddleware(
            model=model,
            trigger=("messages", trigger_count),
            keep=("messages", keep_count),
        )
        result = mw.before_model({"messages": messages}, {"callbacks": []})  # type: ignore[arg-type]
        if result and "messages" in result:
            nuevos_mensajes = [m for m in result["messages"] if getattr(m, "id", None) != "__remove_all__"]
            nuevos_mensajes = sanitizar_pares_tool_call(nuevos_mensajes)
            if clave is not None and len(nuevos_mensajes) < len(messages):
                if len(_CACHE_RESUMEN) >= _CACHE_RESUMEN_MAX:
                    _CACHE_RESUMEN.pop(next(iter(_CACHE_RESUMEN)))
                _CACHE_RESUMEN[clave] = nuevos_mensajes
            return nuevos_mensajes
    except Exception:
        pass

    return sanitizar_pares_tool_call(messages)
