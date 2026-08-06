import pytest
import asyncio
import anyio
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import visualizar_cambios, delegar_tarea_a_equipo_ia, obtener_git_diff, notificar_progreso

def test_visualizar_cambios_sin_parametros():
    resultado = asyncio.run(visualizar_cambios())
    assert "No se proporcionó un 'tarea_id' válido" in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_visualizar_cambios_con_tarea_id(mock_aget_state):
    mock_state = MagicMock()
    mock_state.values = {
        "codigo_escrito": "Se modificó main.py",
        "directorio_proyecto": "./"
    }
    mock_state.next = ["agente_revisor"]
    mock_aget_state.return_value = mock_state

    resultado = asyncio.run(visualizar_cambios(tarea_id="task_123"))
    assert "RESUMEN DE CAMBIOS (Tarea 'task_123')" in resultado
    assert "Se modificó main.py" in resultado
    assert "Pausado antes de 'agente_revisor'" in resultado

@patch("mcp_server.subprocess.run")
def test_obtener_git_diff_exito(mock_subproc):
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "diff --git a/file.txt b/file.txt\n+hola"
    mock_subproc.return_value = mock_res

    res = obtener_git_diff("./")
    assert "diff --git" in res

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_pausa_2_muestra_cambios(mock_ainvoke, mock_aget_state):
    # Simular estado pausado en agente_revisor
    mock_state_pausado = MagicMock()
    mock_state_pausado.next = ["agente_revisor"]
    mock_state_pausado.values = {
        "codigo_escrito": "Creado archivo app/utils/helpers.py con funciones aux."
    }
    mock_aget_state.return_value = mock_state_pausado

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Crear helpers",
        directorio_proyecto="./",
        tarea_id="task_test"
    ))

    assert "ATENCIÓN ASISTENTE DE IA" in resultado
    assert "Revisión de Código Desarrollado (Pausa 2)" in resultado
    assert "Creado archivo app/utils/helpers.py con funciones aux." in resultado
    assert "INSTRUCCIONES PARA EL USUARIO HUMANO" in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_con_contexto_notificaciones(mock_ainvoke, mock_aget_state):
    mock_state_inicial = MagicMock()
    mock_state_inicial.next = []
    
    mock_state_pausado = MagicMock()
    mock_state_pausado.next = ["agente_codificador"]
    mock_state_pausado.values = {"plan_de_accion": "Plan de prueba"}

    mock_aget_state.side_effect = [mock_state_inicial, mock_state_pausado]

    mock_ctx = AsyncMock()
    mock_ctx.info = AsyncMock()
    mock_ctx.report_progress = AsyncMock()

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Crear nueva funcion",
        directorio_proyecto="./",
        ctx=mock_ctx
    ))

    assert "ATENCIÓN ASISTENTE DE IA" in resultado
    assert "Formulario de Aprobación de Plan de Acción" in resultado
    assert "Plan de prueba" in resultado
    assert "INSTRUCCIONES PARA EL USUARIO HUMANO" in resultado
    assert mock_ctx.info.called
    assert mock_ctx.report_progress.called

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_aprobacion_y_completado(mock_ainvoke, mock_aget_state):
    mock_state_pausado = MagicMock()
    mock_state_pausado.next = ["agente_revisor"]

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "Se implementaron las funciones requeridas.",
        "errores_terminal": "0 errores en tests"
    }

    mock_aget_state.side_effect = [mock_state_pausado, mock_state_final, mock_state_final]

    mock_ctx = AsyncMock()

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Aprobar revision",
        directorio_proyecto="./",
        approve=True,
        tarea_id="task_456",
        ctx=mock_ctx
    ))

    assert "✅ Tarea completada exitosamente" in resultado
    assert "Se implementaron las funciones requeridas." in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_auto_approve_parametro(mock_ainvoke, mock_aget_state):
    mock_state_inicial = MagicMock()
    mock_state_inicial.next = []

    mock_state_pausa_1 = MagicMock()
    mock_state_pausa_1.next = ["agente_codificador"]
    mock_state_pausa_1.values = {"plan_de_accion": "Plan de prueba", "messages": []}

    mock_state_pausa_2 = MagicMock()
    mock_state_pausa_2.next = ["agente_revisor"]
    mock_state_pausa_2.values = {"codigo_escrito": "Código generado", "messages": []}

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "Código generado y verificado",
        "errores_terminal": "0 errores"
    }

    mock_aget_state.side_effect = [
        mock_state_inicial,
        mock_state_pausa_1,
        mock_state_pausa_2,
        mock_state_final
    ]

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Crear componente completo",
        directorio_proyecto="./",
        auto_approve=True
    ))

    assert "✅ Tarea completada exitosamente" in resultado
    assert "Código generado y verificado" in resultado
    assert mock_ainvoke.call_count == 3

@pytest.mark.parametrize("env_val", ["true", "1", "yes", "TRUE", " Yes "])
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_auto_approve_env_var(mock_ainvoke, mock_aget_state, env_val):
    mock_state_inicial = MagicMock()
    mock_state_inicial.next = []

    mock_state_pausa_1 = MagicMock()
    mock_state_pausa_1.next = ["agente_codificador"]
    mock_state_pausa_1.values = {"plan_de_accion": "Plan auto", "messages": []}

    mock_state_pausa_2 = MagicMock()
    mock_state_pausa_2.next = ["agente_revisor"]
    mock_state_pausa_2.values = {"codigo_escrito": "Código auto", "messages": []}

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "Código final via env var",
        "errores_terminal": "0 errores"
    }

    mock_aget_state.side_effect = [
        mock_state_inicial,
        mock_state_pausa_1,
        mock_state_pausa_2,
        mock_state_final
    ]

    with patch.dict("os.environ", {"MCP_AUTO_APPROVE": env_val}):
        resultado = asyncio.run(delegar_tarea_a_equipo_ia(
            instruccion="Crear servicio",
            directorio_proyecto="./",
            auto_approve=False
        ))

    assert "✅ Tarea completada exitosamente" in resultado
    assert "Código final via env var" in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_sin_auto_approve_mantiene_pausa(mock_ainvoke, mock_aget_state):
    mock_state_inicial = MagicMock()
    mock_state_inicial.next = []

    mock_state_pausa_1 = MagicMock()
    mock_state_pausa_1.next = ["agente_codificador"]
    mock_state_pausa_1.values = {"plan_de_accion": "Plan manual"}

    mock_aget_state.side_effect = [mock_state_inicial, mock_state_pausa_1]

    with patch.dict("os.environ", {"MCP_AUTO_APPROVE": "false"}):
        resultado = asyncio.run(delegar_tarea_a_equipo_ia(
            instruccion="Crear modulo manual",
            directorio_proyecto="./",
            auto_approve=False
        ))

    assert "ATENCIÓN ASISTENTE DE IA" in resultado
    assert "Plan manual" in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_timeout_excedido(mock_aget_state):
    async def _lento(*args, **kwargs):
        await asyncio.sleep(2)

    mock_aget_state.side_effect = _lento

    with patch.dict("os.environ", {"MCP_TASK_TIMEOUT_SECONDS": "1"}):
        resultado = asyncio.run(delegar_tarea_a_equipo_ia(
            instruccion="Tarea muy pesada",
            directorio_proyecto="./",
            tarea_id="task_timeout"
        ))

    assert "🚨 Timeout:" in resultado
    assert "excedió el límite máximo de ejecución" in resultado

def test_notificar_progreso_captura_broken_resource_error():
    mock_ctx = AsyncMock()
    mock_ctx.info.side_effect = anyio.BrokenResourceError
    # No debe lanzar excepción
    asyncio.run(notificar_progreso(mock_ctx, "Mensaje de prueba"))

def test_notificar_progreso_con_progress_token():
    mock_ctx = AsyncMock()
    mock_meta = MagicMock()
    mock_meta.progressToken = "token_123"
    mock_ctx.request_context.meta = mock_meta
    
    asyncio.run(notificar_progreso(mock_ctx, "Ejecutando paso 1", progreso=30, total=100))
    
    mock_ctx.report_progress.assert_called_once_with(30, total=100, message="Ejecutando paso 1")
    mock_ctx.info.assert_called_once_with("Ejecutando paso 1")

def test_notificar_progreso_fallback_sin_progress_token():
    mock_ctx = AsyncMock()
    mock_meta = MagicMock()
    mock_meta.progressToken = None
    mock_ctx.request_context.meta = mock_meta
    
    asyncio.run(notificar_progreso(mock_ctx, "Ejecutando paso sin token", progreso=25, total=100))
    
    assert mock_ctx.report_progress.called
    mock_ctx.info.assert_called_once_with("[25%] Ejecutando paso sin token")

def test_notificar_progreso_fallback_sin_request_context():
    mock_ctx = AsyncMock(spec=["info", "report_progress"])
    
    asyncio.run(notificar_progreso(mock_ctx, "Mensaje directo", progreso=50, total=100))
    
    mock_ctx.info.assert_called_once_with("[50%] Mensaje directo")


from mcp_server import obtener_formulario_aprobacion, responder_formulario_aprobacion

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_obtener_formulario_aprobacion_pausa_1(mock_aget_state):
    mock_state = MagicMock()
    mock_state.next = ["agente_codificador"]
    mock_state.values = {
        "plan_de_accion": {
            "explicacion_arquitectura": "Arquitectura modular",
            "pasos": [{"tarea": "Crear modulo", "archivo": "app/m.py", "requiere_test": True}]
        },
        "directorio_proyecto": "/tmp/test"
    }
    mock_aget_state.return_value = mock_state

    # Prueba formato html
    res_html = asyncio.run(obtener_formulario_aprobacion(tarea_id="t_form1", formato="html"))
    assert "<!DOCTYPE html>" in res_html
    assert "Arquitectura modular" in res_html

    # Prueba formato markdown
    res_md = asyncio.run(obtener_formulario_aprobacion(tarea_id="t_form1", formato="markdown"))
    assert "ATENCIÓN ASISTENTE DE IA" in res_md

    # Prueba formato json
    res_json = asyncio.run(obtener_formulario_aprobacion(tarea_id="t_form1", formato="json"))
    assert '"tarea_id": "t_form1"' in res_json

    # Prueba formato cli
    res_cli = asyncio.run(obtener_formulario_aprobacion(tarea_id="t_form1", formato="cli"))
    assert "[DETENER IA - PAUSA_1]" in res_cli

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_obtener_formulario_aprobacion_sin_pausa(mock_aget_state):
    mock_state = MagicMock()
    mock_state.next = []
    mock_aget_state.return_value = mock_state

    res = asyncio.run(obtener_formulario_aprobacion(tarea_id="t_no_pause"))
    assert "no se encuentra en estado pausado" in res

@patch("mcp_server.delegar_tarea_a_equipo_ia", new_callable=AsyncMock)
def test_responder_formulario_aprobacion_aprobar(mock_delegar):
    mock_delegar.return_value = "✅ Tarea completada exitosamente"
    
    res = asyncio.run(responder_formulario_aprobacion(
        tarea_id="t_resp1",
        accion="approve",
        directorio_proyecto="/app"
    ))

    assert "✅ Tarea completada exitosamente" in res
    mock_delegar.assert_called_once_with(
        instruccion="",
        directorio_proyecto="/app",
        approve=True,
        tarea_id="t_resp1",
        ctx=None
    )

@patch("mcp_server.delegar_tarea_a_equipo_ia", new_callable=AsyncMock)
def test_responder_formulario_aprobacion_rechazar(mock_delegar):
    mock_delegar.return_value = "🛑 Re-evaluando plan..."

    res = asyncio.run(responder_formulario_aprobacion(
        tarea_id="t_resp2",
        accion="reject",
        feedback="Cambiar el patrón por singleton",
        directorio_proyecto="/app"
    ))

    assert "🛑 Re-evaluando plan..." in res
    mock_delegar.assert_called_once_with(
        instruccion="Cambiar el patrón por singleton",
        directorio_proyecto="/app",
        approve=False,
        tarea_id="t_resp2",
        ctx=None
    )
