from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AnyMessage
from typing import List, Optional

from app.models.llm_factory import get_llm

# Timeout (segundos) para la llamada LLM de resumen. Si el proveedor se cuelga,
# se devuelve el historial original en lugar de bloquear al agente indefinidamente.
RESUMEN_TIMEOUT_SEGUNDOS = 60.0

# Executor dedicado (daemon) para que los resúmenes colgados no impidan el cierre.
_executor_resumen = ThreadPoolExecutor(max_workers=2, thread_name_prefix="resumen")


def _ejecutar_resumen(model, messages: List[AnyMessage], trigger_count: int, keep_count: int) -> List[AnyMessage]:
    """Ejecuta SummarizationMiddleware.before_model de forma aislada (llamable con timeout)."""
    mw = SummarizationMiddleware(
        model=model,
        trigger=("messages", trigger_count),
        keep=("messages", keep_count)
    )
    result = mw.before_model({"messages": messages}, {"callbacks": []})  # pyright: ignore[reportArgumentType]
    if result and "messages" in result:
        new_msgs = []
        for m in result["messages"]:
            # Excluir mensajes de remoción si existen en el resultado
            if hasattr(m, "id") and m.id == "__remove_all__":
                continue
            new_msgs.append(m)
        return new_msgs
    return messages


def aplicar_resumen_middleware(
    messages: List[AnyMessage],
    model=None,
    trigger_count: int = 15,
    keep_count: int = 8,
    timeout_segundos: Optional[float] = None,
) -> List[AnyMessage]:
    """
    Aplica SummarizationMiddleware para resumir automáticamente el historial de mensajes
    cuando se supera el umbral (trigger_count), conservando los últimos (keep_count) mensajes.

    La llamada LLM de resumen se ejecuta en un hilo con timeout: si el proveedor
    se cuelga o tarda demasiado, se devuelve el historial original sin bloquear
    al agente (antes, un resumen colgado congelaba todo el flujo).
    """
    if not messages or len(messages) <= trigger_count:
        return messages

    if model is None:
        model = get_llm()

    if timeout_segundos is None:
        timeout_segundos = RESUMEN_TIMEOUT_SEGUNDOS

    try:
        futuro = _executor_resumen.submit(
            _ejecutar_resumen, model, messages, trigger_count, keep_count
        )
        return futuro.result(timeout=timeout_segundos)
    except FuturesTimeoutError:
        # Resumen colgado: continuar con el historial completo (degradación
        # controlada) en lugar de bloquear el flujo del agente.
        return messages
    except Exception:
        return messages
