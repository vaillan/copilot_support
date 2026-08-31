from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.llm_factory import get_llm


def _agrupar_unidades(messages: List[AnyMessage]) -> List[List[AnyMessage]]:
    """
    Agrupa mensajes en unidades indivisibles para el corte del historial.

    Cada AIMessage con tool_calls se agrupa con los ToolMessage que le siguen,
    de modo que el corte del resumen nunca separe una llamada de herramientas
    de sus resultados (lo que produciría errores de emparejamiento 400 en la
    API del proveedor).

    Args:
        messages: Historial completo de mensajes (List[AnyMessage]).

    Returns:
        List[List[AnyMessage]]: Lista de unidades; cada unidad es un grupo de
        mensajes que debe permanecer junto (o separarse como bloque completo).
    """
    unidades: List[List[AnyMessage]] = []
    i = 0
    n = len(messages)
    while i < n:
        mensaje = messages[i]
        if isinstance(mensaje, AIMessage) and getattr(mensaje, "tool_calls", None):
            grupo = [mensaje]
            i += 1
            while i < n and isinstance(messages[i], ToolMessage):
                grupo.append(messages[i])
                i += 1
            unidades.append(grupo)
        else:
            unidades.append([mensaje])
            i += 1
    return unidades


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
      2. Los últimos mensajes (hasta acumular `keep_count`) se conservan
         íntegros (errores y resultados recientes de herramientas).
      3. El resumen generado conserva decisiones tomadas, errores detectados,
         archivos modificados y el plan de acción vigente.
      4. El corte NUNCA separa un AIMessage con tool_calls de sus ToolMessage:
         se agrupan en unidades indivisibles antes de dividir el historial.

    Ante cualquier fallo del modelo devuelve los mensajes originales sin modificar, de modo que
    la optimización de contexto nunca rompe el flujo del agente.
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        model = get_llm()

    try:
        unidades = _agrupar_unidades(messages)

        # (1) La instrucción original del usuario nunca se resume.
        idx_inicio = 0
        if unidades and isinstance(unidades[0][0], HumanMessage):
            idx_inicio = 1

        # (2) Unidades recientes: se toman desde el final hasta acumular al
        # menos keep_count mensajes (siempre se conserva al menos una unidad).
        recientes_unidades: List[List[AnyMessage]] = []
        acumulados = 0
        j = len(unidades) - 1
        while j >= idx_inicio and (acumulados < keep_count or not recientes_unidades):
            recientes_unidades.insert(0, unidades[j])
            acumulados += len(unidades[j])
            j -= 1

        antiguas_unidades = unidades[idx_inicio:j + 1]
        if not antiguas_unidades:
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
        antiguos = [m for unidad in antiguas_unidades for m in unidad]
        recientes = [m for unidad in recientes_unidades for m in unidad]
        contenido = "\n".join(f"{type(m).__name__}: {m.content}" for m in antiguos)
        resumen = model.invoke(prompt.format_messages(contenido=contenido))
        texto = str(resumen.content) if hasattr(resumen, "content") else str(resumen)
        resumen_msg = HumanMessage(content=f"[Resumen de conversación anterior] {texto}")
        # (1) + (2): instrucción original íntegra + resumen + mensajes recientes íntegros.
        primero = messages[0] if isinstance(messages[0], HumanMessage) else None
        return ([primero] if primero is not None else []) + [resumen_msg] + recientes
    except Exception:
        return messages
