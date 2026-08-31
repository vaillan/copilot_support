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

    Garantías de preservación de contexto (conversaciones largas):
      1. El PRIMER mensaje humano (instrucción original del usuario) NUNCA se
         resume: se conserva íntegro al inicio del contexto resultante.
      2. Los últimos `keep_count` mensajes se conservan íntegros (errores y
         resultados recientes de herramientas).
      3. El resumen generado conserva decisiones tomadas, errores detectados,
         archivos modificados y el plan de acción vigente.

    Ante cualquier fallo del modelo devuelve los mensajes originales sin modificar, de modo que
    la optimización de contexto nunca rompe el flujo del agente.
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        model = get_llm()

    try:
        # (1) La instrucción original del usuario nunca se resume.
        primero = messages[0] if isinstance(messages[0], HumanMessage) else None
        antiguos = messages[1:-keep_count] if primero is not None else messages[:-keep_count]
        recientes = messages[-keep_count:]
        if not antiguos:
            return messages

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Resume de forma concisa la siguiente conversación entre humano y asistente. "
                "Conserva OBLIGATORIAMENTE: la instrucción original y su intención, el plan de "
                "acción vigente (pasos y archivos), los archivos ya creados o modificados, las "
                "decisiones tomadas y los errores detectados con su causa. Omite detalles "
                "redundantes para ahorrar tokens."
            )),
            ("human", "{contenido}"),
        ])
        contenido = "\n".join(f"{type(m).__name__}: {m.content}" for m in antiguos)
        resumen = model.invoke(prompt.format_messages(contenido=contenido))
        texto = str(resumen.content) if hasattr(resumen, "content") else str(resumen)
        resumen_msg = HumanMessage(content=f"[Resumen de conversación anterior] {texto}")
        # (1) + (2): instrucción original íntegra + resumen + mensajes recientes íntegros.
        return ([primero] if primero is not None else []) + [resumen_msg] + recientes
    except Exception:
        return messages