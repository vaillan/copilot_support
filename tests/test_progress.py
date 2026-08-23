"""Tests unitarios para app/mcp/progress.py.

Cubre los helpers puros de notificación de progreso de forma directa:
``_log_stderr``, ``_safe_await`` y ``notificar_progreso``, mockeando
``fastmcp.Context`` con ``AsyncMock``. Sigue el estilo de tests/test_mcp_server.py
(pytest + unittest.mock + asyncio.run).
"""

import asyncio
import sys
from unittest.mock import AsyncMock

from app.mcp.progress import _log_stderr, _safe_await, notificar_progreso


# ---------------------------------------------------------------------------
# _log_stderr
# ---------------------------------------------------------------------------

def test_log_stderr_escribe_a_stderr(capsys):
    """Caso (a): _log_stderr escribe el mensaje con salto de línea en stderr."""
    _log_stderr("mensaje de prueba")
    captured = capsys.readouterr()
    assert "mensaje de prueba" in captured.err
    assert captured.err.endswith("\n")


def test_log_stderr_no_lanza_si_stderr_falla(monkeypatch):
    """Caso (a'): _log_stderr tolera fallos de escritura en stderr."""
    class _StderrRoto:
        def write(self, s):
            raise OSError("stderr cerrado")

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stderr", _StderrRoto())
    _log_stderr("no debe lanzar")  # No debe propagar excepción


# ---------------------------------------------------------------------------
# _safe_await
# ---------------------------------------------------------------------------

def test_safe_await_coro_rapido_se_ejecuta():
    """Caso (b): coro que completa rápido -> se ejecuta sin errores."""
    ejecutado = []

    async def coro_rapido():
        ejecutado.append(True)

    resultado = asyncio.run(_safe_await(coro_rapido()))
    assert ejecutado == [True]
    assert resultado is None


def test_safe_await_timeout_no_lanza():
    """Caso (b'): coro que excede el timeout -> no lanza y retorna None."""
    async def coro_lento():
        await asyncio.sleep(5)

    resultado = asyncio.run(_safe_await(coro_lento(), timeout=0.01))
    assert resultado is None


def test_safe_await_coro_que_lanza_no_propaga():
    """Caso (b''): coro que lanza excepción -> no propaga y retorna None."""
    async def coro_roto():
        raise RuntimeError("boom")

    resultado = asyncio.run(_safe_await(coro_roto()))
    assert resultado is None


# ---------------------------------------------------------------------------
# notificar_progreso
# ---------------------------------------------------------------------------

def test_notificar_progreso_con_contexto():
    """Caso (c): con Context mockeado -> report_progress e info con args esperados."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context = None  # sin progress token -> se formatea [pct%]

    asyncio.run(notificar_progreso(mock_ctx, "Mensaje de prueba", progreso=50, total=100))

    mock_ctx.report_progress.assert_awaited_once_with(
        50, total=100, message="Mensaje de prueba"
    )
    mock_ctx.info.assert_awaited_once_with("[50%] Mensaje de prueba")


def test_notificar_progreso_sin_progreso():
    """Caso (c'): progreso=None -> no llama report_progress y logea sin prefijo."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context = None

    asyncio.run(notificar_progreso(mock_ctx, "Solo log", progreso=None))

    mock_ctx.report_progress.assert_not_called()
    mock_ctx.info.assert_awaited_once_with("Solo log")


def test_notificar_progreso_contexto_none():
    """Caso (c''): Context None -> no lanza excepción."""
    asyncio.run(notificar_progreso(None, "sin contexto", progreso=10))
    asyncio.run(notificar_progreso(None, "sin contexto"))


def test_notificar_progreso_no_lanza_si_info_falla():
    """Caso (c'''): ctx.info lanza excepción -> no propaga."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context = None
    mock_ctx.info.side_effect = Exception("boom")

    asyncio.run(notificar_progreso(mock_ctx, "Mensaje", progreso=10))
    # No debe propagar la excepción


def test_notificar_progreso_con_progress_token():
    """Caso (c''''): con progressToken presente -> no se añade prefijo [pct%]."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context.meta.progressToken = 123

    asyncio.run(notificar_progreso(mock_ctx, "Mensaje", progreso=50, total=100))

    mock_ctx.report_progress.assert_awaited_once_with(
        50, total=100, message="Mensaje"
    )
    mock_ctx.info.assert_awaited_once_with("Mensaje")


def test_notificar_progreso_fallback_log():
    """Caso (c'''''): sin ctx.info -> usa ctx.log(level='info', message=...)."""
    class _CtxSinInfo:
        def __init__(self):
            self.log = AsyncMock()
            self.report_progress = AsyncMock()
            self.request_context = None

    ctx = _CtxSinInfo()
    asyncio.run(notificar_progreso(ctx, "Mensaje", progreso=25, total=100))

    ctx.report_progress.assert_awaited_once_with(25, total=100, message="Mensaje")
    ctx.log.assert_awaited_once_with(level="info", message="[25%] Mensaje")


def test_notificar_progreso_resume_mensaje_multilinea():
    """Caso (c''''''): mensaje multilínea -> se resume a la primera línea."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context = None

    mensaje = "Primera línea\nSegunda línea\nTercera"
    asyncio.run(notificar_progreso(mock_ctx, mensaje, progreso=10, total=100))

    mock_ctx.info.assert_awaited_once_with("[10%] Primera línea")