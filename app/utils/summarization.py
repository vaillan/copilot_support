from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AnyMessage
from typing import List
from app.models.llm_factory import get_llm

def aplicar_resumen_middleware(messages: List[AnyMessage], model=None, trigger_count: int = 15, keep_count: int = 8) -> List[AnyMessage]:
    """
    Aplica SummarizationMiddleware para resumir automáticamente el historial de mensajes
    cuando se supera el umbral (trigger_count), conservando los últimos (keep_count) mensajes.
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        model = get_llm()

    try:
        mw = SummarizationMiddleware(
            model=model,
            trigger=("messages", trigger_count),
            keep=("messages", keep_count)
        )
        result = mw.before_model({"messages": messages}, None)
        if result and "messages" in result:
            new_msgs = []
            for m in result["messages"]:
                # Excluir mensajes de remoción si existen en el resultado
                if hasattr(m, "id") and m.id == "__remove_all__":
                    continue
                new_msgs.append(m)
            return new_msgs
    except Exception:
        pass

    return messages
