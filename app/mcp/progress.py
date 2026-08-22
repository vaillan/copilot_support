"""Helpers de notificación de progreso para el servidor MCP.

Este módulo contiene las funciones puras (sin dependencia del grafo LangGraph)
encargadas de enviar mensajes de log y progreso en tiempo real al cliente MCP
(Zoo Code / Cursor / CLI) de forma segura, capturando cualquier excepción para
nunca bloquear la ejecución principal del servidor.
"""

import asyncio
import sys
from typing import Optional

from fastmcp import Context


def _log_stderr(msg: str) -> None:
    """Escribe mensaje a stderr de forma segura (fire-and-forget)."""
    try:
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


async def _safe_await(coro, timeout: float = 1.0) -> None:
    """Await seguro con timeout que nunca propaga excepciones."""
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        pass


async def notificar_progreso(
    ctx: Optional[Context],
    mensaje: str,
    progreso: Optional[int] = None,
    total: int = 100,
) -> None:
    """
    Envía mensajes de log y progreso en tiempo real de forma segura y directa.
    Captura y maneja cualquier excepción para nunca bloquear la ejecución principal.
    """
    if ctx is None:
        return

    try:
        mensaje_resumido = mensaje.splitlines()[0][:200] if mensaje else ""

        has_progress_token = False
        try:
            if (
                hasattr(ctx, "request_context")
                and ctx.request_context is not None
                and hasattr(ctx.request_context, "meta")
                and ctx.request_context.meta is not None
                and getattr(ctx.request_context.meta, "progressToken", None) is not None
            ):
                has_progress_token = True
        except Exception:
            has_progress_token = False

        progreso_val = progreso if progreso is not None else 0

        if progreso is not None and hasattr(ctx, "report_progress"):
            try:
                res = ctx.report_progress(progreso_val, total=total, message=mensaje_resumido)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass

        if progreso is not None and not has_progress_token:
            pct = int((progreso_val / total) * 100) if total > 0 else progreso_val
            mensaje_formateado = f"[{pct}%] {mensaje_resumido}"
        else:
            mensaje_formateado = mensaje_resumido

        # Enviar mensaje de log al cliente MCP (Zoo Code).
        # FastMCP 3.2.4: ctx.info existe y envía 'notifications/message' de nivel INFO.
        # ctx.log(level, message) es el método genérico equivalente a report_log_message.
        if hasattr(ctx, "info"):
            try:
                res = ctx.info(mensaje_formateado)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass
        elif hasattr(ctx, "log"):
            try:
                res = ctx.log(level="info", message=mensaje_formateado)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass

        _log_stderr(f"[PROGRESO] {mensaje_formateado}")

    except Exception:
        pass