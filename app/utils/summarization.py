"""
Módulo de resumen y compresión de historial de mensajes (Trimming & Summarization).

Permite prevenir el desbordamiento de contexto en ejecuciones de agentes y grafos de LangGraph,
resumiendo conversaciones extensas o aplicando recorte inteligente sin perder decisiones
arquitectónicas clave ni el mensaje de sistema inicial.
"""

from typing import List, Optional, Union
from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain.agents.middleware import SummarizationMiddleware
from app.models.llm_factory import get_llm
from app.utils.token_calculator import count_tokens_in_messages, estimate_tokens_from_text


def extract_message_text(message: Union[BaseMessage, dict, str]) -> str:
    """
    Extrae la representación textual limpia de cualquier tipo de mensaje.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return str(message.get("content", ""))
    if hasattr(message, "content"):
        content = message.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return " ".join(parts)
        return str(content)
    return str(message)


def trim_messages_by_count(
    messages: List[AnyMessage],
    keep_first: int = 1,
    keep_last: int = 6
) -> List[AnyMessage]:
    """
    Recorta el historial manteniendo los primeros `keep_first` mensajes (ej. SystemMessage/Plan)
    y los últimos `keep_last` mensajes, descartando el medio si el total excede el umbral.
    """
    if not messages or len(messages) <= (keep_first + keep_last):
        return messages

    first_part = messages[:keep_first]
    last_part = messages[-keep_last:] if keep_last > 0 else []
    omitted_count = len(messages) - keep_first - keep_last

    summary_note = SystemMessage(
        content=f"[Contexto comprimido: se omitieron {omitted_count} mensajes intermedios para optimizar la ventana de contexto.]"
    )

    return [*first_part, summary_note, *last_part]


def trim_messages_by_tokens(
    messages: List[AnyMessage],
    max_tokens: int = 8000,
    keep_first: int = 1,
    keep_last_min: int = 4
) -> List[AnyMessage]:
    """
    Recorta progresivamente mensajes intermedios hasta que el conteo total de tokens
    se encuentre por debajo del umbral `max_tokens`, protegiendo el primer mensaje (sistema/plan)
    y un mínimo de mensajes recientes.
    """
    if not messages:
        return messages

    current_tokens = count_tokens_in_messages(messages)
    if current_tokens <= max_tokens:
        return messages

    if len(messages) <= keep_first + keep_last_min:
        return messages

    # Preservar primer mensaje si keep_first > 0
    first_msgs = messages[:keep_first] if keep_first > 0 else []
    remaining_pool = messages[keep_first:]

    # Tomar de atrás hacia adelante
    selected_recent = []
    for msg in reversed(remaining_pool):
        candidate = [msg] + selected_recent
        candidate_total = count_tokens_in_messages(first_msgs + candidate)
        if candidate_total <= max_tokens or len(selected_recent) < keep_last_min:
            selected_recent.insert(0, msg)
        else:
            break

    omitted = len(remaining_pool) - len(selected_recent)
    if omitted > 0:
        notice = SystemMessage(
            content=f"[Contexto ajustado por límite de tokens: se omitieron {omitted} mensajes anteriores manteniendo el estado crítico.]"
        )
        return [*first_msgs, notice, *selected_recent]

    return [*first_msgs, *selected_recent]


def aplicar_resumen_middleware(
    messages: List[AnyMessage],
    model=None,
    trigger_count: int = 15,
    keep_count: int = 8
) -> List[AnyMessage]:
    """
    Aplica SummarizationMiddleware para resumir automáticamente el historial de mensajes
    cuando se supera el umbral (trigger_count), conservando los últimos (keep_count) mensajes.
    Si falla el middleware o no hay modelo disponible, aplica compresión segura por recorte.
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        try:
            model = get_llm()
        except Exception:
            model = None

    if model is not None:
        try:
            mw = SummarizationMiddleware(
                model=model,
                trigger=("messages", trigger_count),
                keep=("messages", keep_count)
            )
            result = mw.before_model({"messages": messages}, None) # pyright: ignore[reportArgumentType]
            if result and "messages" in result:
                new_msgs = []
                for m in result["messages"]:
                    if hasattr(m, "id") and m.id == "__remove_all__":
                        continue
                    new_msgs.append(m)
                if new_msgs:
                    return new_msgs
        except Exception:
            pass

    # Fallback determinístico sin LLM
    return trim_messages_by_count(messages, keep_first=1, keep_last=keep_count)
