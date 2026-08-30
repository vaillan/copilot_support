from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.llm_factory import get_llm


def aplicar_resumen_middleware(
    messages: List[AnyMessage],
    model: Optional[BaseChatModel] = None,
    trigger_count: int = 15,
    keep_count: int = 8,
) -> List[AnyMessage]:
    """Resume el historial antiguo con el LLM al superar el umbral y conserva los mensajes recientes.

    Ante cualquier fallo del modelo devuelve los mensajes originales sin modificar, de modo que
    la optimización de contexto nunca rompe el flujo del agente.
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        model = get_llm()

    try:
        antiguos = messages[:-keep_count]
        recientes = messages[-keep_count:]
        if not antiguos:
            return messages

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Resume de forma concisa la siguiente conversación entre humano y asistente, conservando decisiones tomadas, errores detectados y contexto relevante para continuar el trabajo."),
            ("human", "{contenido}"),
        ])
        contenido = "\n".join(f"{type(m).__name__}: {m.content}" for m in antiguos)
        resumen = model.invoke(prompt.format_messages(contenido=contenido))
        texto = str(resumen.content) if hasattr(resumen, "content") else str(resumen)
        return [HumanMessage(content=f"[Resumen de conversación anterior] {texto}")] + recientes
    except Exception:
        return messages