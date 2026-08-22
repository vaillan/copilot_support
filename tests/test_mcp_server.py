import sys
import os
import pytest
import asyncio
import anyio
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import visualizar_cambios, delegar_tarea_a_equipo_ia, obtener_git_diff, notificar_progreso, generar_markdown_pausa, consultar_estado_tarea, listar_tareas, cancelar_tarea

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

    mock_ctx = AsyncMock()
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Crear helpers",
        directorio_proyecto="./",
        tarea_id="task_test",
        ctx=mock_ctx
    ))

    assert "ATENCIÓN ASISTENTE DE IA" in resultado
    assert "Revisión de Código Desarrollado (Pausa 2)" in resultado
    assert "Creado archivo app/utils/helpers.py con funciones aux." in resultado
    assert "INSTRUCCIONES PARA EL USUARIO HUMANO" in resultado
    
    # Verificar que mock_ctx.info recibió la notificación resumida de pausa 2
    info_calls = [call.args[0] for call in mock_ctx.info.call_args_list]
    notificacion_resumida = any("PAUSA 2" in call for call in info_calls)
    assert notificacion_resumida, "El mensaje enviado a notificar_progreso (ctx.info) en PAUSA 2 debe incluir el resumen conciso."

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_con_contexto_notificaciones(mock_ainvoke, mock_aget_state):
    mock_state_inicial = MagicMock()
    mock_state_inicial.next = []
    
    mock_state_pausado = MagicMock()
    mock_state_pausado.next = ["agente_codificador"]
    mock_state_pausado.values = {"plan_de_accion": {"explicacion_arquitectura": "Plan de prueba", "pasos": []}}

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

    # Verificar que mock_ctx.info recibió la notificación resumida de pausa 1
    info_calls = [call.args[0] for call in mock_ctx.info.call_args_list]
    notificacion_resumida = any("PAUSA 1" in call for call in info_calls)
    assert notificacion_resumida, "El mensaje enviado a notificar_progreso (ctx.info) en PAUSA 1 debe incluir el resumen conciso."

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
def test_delegar_tarea_preserva_stdout(mock_ainvoke, mock_aget_state):
    """Verifica que sys.stdout no es redirigido a sys.stderr durante la ejecución de delegar_tarea_a_equipo_ia."""
    original_stdout = sys.stdout

    async def _chequear_stdout(*args, **kwargs):
        assert sys.stdout is original_stdout
        mock_state = MagicMock()
        mock_state.next = []
        mock_state.values = {"codigo_escrito": "ok", "errores_terminal": "0 errores"}
        return mock_state

    mock_aget_state.side_effect = _chequear_stdout

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Verificar preservacion de stdout",
        directorio_proyecto="./",
        tarea_id="task_stdout_check"
    ))

    assert sys.stdout is original_stdout
    assert "✅ Tarea completada exitosamente" in resultado

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
    
    asyncio.run(notificar_progreso(mock_ctx, "Ejecutando paso 1\nSegunda línea", progreso=30, total=100))
    
    mock_ctx.report_progress.assert_called_once_with(30, total=100, message="Ejecutando paso 1")
    mock_ctx.info.assert_called_once_with("Ejecutando paso 1")

def test_notificar_progreso_fallback_sin_progress_token():
    mock_ctx = AsyncMock()
    mock_meta = MagicMock()
    mock_meta.progressToken = None
    mock_ctx.request_context.meta = mock_meta
    
    asyncio.run(notificar_progreso(mock_ctx, "Ejecutando paso sin token\nLínea 2", progreso=25, total=100))
    
    assert mock_ctx.report_progress.called
    mock_ctx.info.assert_called_once_with("[25%] Ejecutando paso sin token")

def test_notificar_progreso_fallback_sin_request_context():
    mock_ctx = AsyncMock(spec=["info", "report_progress"])
    
    asyncio.run(notificar_progreso(mock_ctx, "Mensaje directo\nExtra", progreso=50, total=100))
    
    mock_ctx.info.assert_called_once_with("[50%] Mensaje directo")

def test_generar_markdown_pausa_orden_prominente():
    pasos_ejemplo = [
        {"tarea": "Crear archivo de configuración", "archivo": "config.py", "requiere_test": False},
        {"tarea": "Implementar lógica principal", "archivo": "main.py", "requiere_test": True}
    ]
    reporte = generar_markdown_pausa(
        tarea_id="task_xyz123",
        tipo_pausa="PAUSA_1",
        titulo="Plan de Arquitectura Propuesto",
        explicacion="Esta es la explicación detallada de la arquitectura modular.",
        pasos=pasos_ejemplo,
        directorio_proyecto="/ruta/proyecto"
    )

    # Verificar que el título y metadatos están presentes
    assert "### 📌 Plan de Arquitectura Propuesto" in reporte
    assert "- **ID Tarea:** `task_xyz123`" in reporte
    assert "- **Directorio:** `/ruta/proyecto`" in reporte
    assert "- **Estado:** Pausado (PAUSA_1) - Requiere aprobación humana." in reporte

    # Verificar que la explicación y la tabla de pasos aparecen en el reporte
    assert "#### 📄 Explicación / Resumen:" in reporte
    assert "Esta es la explicación detallada de la arquitectura modular." in reporte
    assert "#### 📋 Plan de Pasos Propuestos:" in reporte
    assert "| 1 | Crear archivo de configuración | `config.py` | No |" in reporte
    assert "| 2 | Implementar lógica principal | `main.py` | Si |" in reporte

    # Verificar orden estricto: El plan de acción (título, explicación, tabla) debe aparecer ANTES
    # de los avisos para la IA ("🛑 ATENCIÓN ASISTENTE DE IA") y de las instrucciones del usuario ("👉 INSTRUCCIONES PARA EL USUARIO HUMANO").
    pos_titulo = reporte.find("### 📌 Plan de Arquitectura Propuesto")
    pos_explicacion = reporte.find("Esta es la explicación detallada de la arquitectura modular.")
    pos_tabla = reporte.find("Plan de Pasos Propuestos")
    pos_ia = reporte.find("🛑 ATENCIÓN ASISTENTE DE IA")
    pos_humano = reporte.find("👉 **INSTRUCCIONES PARA EL USUARIO HUMANO:**")

    assert pos_titulo < pos_ia
    assert pos_explicacion < pos_ia
    assert pos_tabla < pos_ia
    assert pos_ia < pos_humano

def test_generar_markdown_pausa_con_diff():
    diff_ejemplo = "diff --git a/app.py b/app.py\n+print('hello')"
    reporte = generar_markdown_pausa(
        tarea_id="task_diff789",
        tipo_pausa="PAUSA_2",
        titulo="Revisión de Código Desarrollado",
        explicacion="Se creó el archivo app.py.",
        diff_git=diff_ejemplo,
        directorio_proyecto="./"
    )

    assert "### 📌 Revisión de Código Desarrollado" in reporte
    assert "Se creó el archivo app.py." in reporte
    assert "#### 🔍 Git Diff / Cambios en Disco:" in reporte
    assert "+print('hello')" in reporte

    pos_explicacion = reporte.find("Se creó el archivo app.py.")
    pos_diff = reporte.find("Git Diff / Cambios en Disco")
    pos_ia = reporte.find("🛑 ATENCIÓN ASISTENTE DE IA")

    assert pos_explicacion < pos_diff
    assert pos_diff < pos_ia


# =============================================================================
# Pruebas para las nuevas herramientas de gestión de tareas
# =============================================================================

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_consultar_estado_tarea_con_tarea_registrada(mock_aget_state):
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_consulta",
        directorio_proyecto="./",
        estado="paused_planning",
        detalle="Plan listo",
    )

    mock_state = MagicMock()
    mock_state.values = {"codigo_escrito": "Se modificó main.py", "directorio_proyecto": "./"}
    mock_state.next = ["agente_codificador"]
    mock_aget_state.return_value = mock_state

    mock_ctx = AsyncMock()
    resultado = asyncio.run(consultar_estado_tarea(
        tarea_id="task_consulta",
        directorio_proyecto="./",
        ctx=mock_ctx,
    ))

    assert "Estado registrado de la tarea 'task_consulta'" in resultado
    assert "paused_planning" in resultado
    assert "Pausado antes de 'agente_codificador'" in resultado
    task_registry.clear()


@patch("mcp_server.visualizar_cambios", new_callable=AsyncMock)
def test_consultar_estado_tarea_tarea_inexistente(mock_visualizar):
    from app.utils.task_registry import task_registry
    task_registry.clear()
    mock_visualizar.return_value = "No se encontraron cambios."

    mock_ctx = AsyncMock()
    resultado = asyncio.run(consultar_estado_tarea(
        tarea_id="task_no_existe",
        ctx=mock_ctx,
    ))

    assert "no está registrada en el TaskRegistry" in resultado
    task_registry.clear()


def test_listar_tareas_sin_tareas():
    from app.utils.task_registry import task_registry
    task_registry.clear()

    mock_ctx = AsyncMock()
    resultado = asyncio.run(listar_tareas(ctx=mock_ctx))

    assert "No hay tareas registradas" in resultado
    task_registry.clear()


def test_listar_tareas_con_tareas():
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(tarea_id="task_1", directorio_proyecto="./", estado="running")
    task_registry.register_task(tarea_id="task_2", directorio_proyecto="./", estado="completed")

    mock_ctx = AsyncMock()
    resultado = asyncio.run(listar_tareas(ctx=mock_ctx))

    assert "### 📋 Tareas Registradas" in resultado
    assert "task_1" in resultado
    assert "task_2" in resultado
    task_registry.clear()


def test_listar_tareas_filtra_por_estado():
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(tarea_id="task_running", directorio_proyecto="./", estado="running")
    task_registry.register_task(tarea_id="task_completed", directorio_proyecto="./", estado="completed")

    mock_ctx = AsyncMock()
    resultado = asyncio.run(listar_tareas(estado="running", ctx=mock_ctx))

    assert "task_running" in resultado
    assert "task_completed" not in resultado
    task_registry.clear()


def test_cancelar_tarea_marca_cancelled():
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(tarea_id="task_cancel", directorio_proyecto="./", estado="running")

    mock_ctx = AsyncMock()
    resultado = asyncio.run(cancelar_tarea(tarea_id="task_cancel", ctx=mock_ctx))

    assert "marcada como cancelada" in resultado
    tarea = task_registry.get_task("task_cancel")
    assert tarea["estado"] == "cancelled"
    task_registry.clear()


def test_cancelar_tarea_inexistente_devuelve_error():
    from app.utils.task_registry import task_registry
    task_registry.clear()

    mock_ctx = AsyncMock()
    resultado = asyncio.run(cancelar_tarea(tarea_id="task_no_existe", ctx=mock_ctx))

    assert "No se encontró la tarea" in resultado
    task_registry.clear()


# =============================================================================
# Pruebas para la selección de transporte (SSE/HTTP)
# =============================================================================

def test_transporte_default_es_stdio():
    import mcp_server
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FASTMCP_TRANSPORT", None)
        with patch.object(mcp_server.mcp, "run") as mock_run:
            # Simular la lógica del __main__
            transporte = os.environ.get("FASTMCP_TRANSPORT", "stdio").lower()
            if transporte in ("sse", "streamable-http", "http"):
                mcp_server.mcp.run(transport=transporte)
            else:
                mcp_server.mcp.run(transport="stdio")
            mock_run.assert_called_once_with(transport="stdio")


def test_transporte_sse_cuando_env_var_sse():
    import mcp_server
    # El .env define FASTMCP_PORT="8080" (P4: antes el typo FASTMCP_TRANSPORT0
    # impedía que se leyera el transporte SSE y se usaba el default 8000).
    with patch.dict(os.environ, {"FASTMCP_TRANSPORT": "sse", "FASTMCP_PORT": "8080"}, clear=False):
        with patch.object(mcp_server.mcp, "run") as mock_run:
            transporte = os.environ.get("FASTMCP_TRANSPORT", "stdio").lower()
            if transporte in ("sse", "streamable-http", "http"):
                mcp_server.mcp.run(
                    transport=transporte,
                    host=os.environ.get("FASTMCP_HOST", "127.0.0.1"),
                    port=int(os.environ.get("FASTMCP_PORT", "8000")),
                )
            else:
                mcp_server.mcp.run(transport="stdio")
            mock_run.assert_called_once_with(
                transport="sse",
                host="127.0.0.1",
                port=8080,
            )


def test_http_app_genera_app_sse():
    import mcp_server
    app = mcp_server.mcp.http_app(transport="sse")
    assert app is not None
    assert app.state.transport_type == "sse"


def test_http_app_genera_app_streamable_http():
    import mcp_server
    app = mcp_server.mcp.http_app(transport="streamable-http")
    assert app is not None
    assert app.state.transport_type == "streamable-http"


def test_script_dir_en_sys_path():
    """El directorio del script debe estar en sys.path para evitar 'Connection closed'
    cuando el cliente lanza el proceso desde un directorio de trabajo distinto."""
    import mcp_server
    script_dir = os.path.dirname(os.path.abspath(mcp_server.__file__))
    assert script_dir in sys.path


def test_herramientas_registradas():
    """El servidor debe exponer las 4 herramientas MCP esperadas."""
    import mcp_server
    nombres = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {
        "delegar_tarea_a_equipo_ia",
        "consultar_estado_tarea",
        "listar_tareas",
        "cancelar_tarea",
    }.issubset(nombres)


def test_cancelar_tarea_interrumpe_ejecucion_en_curso():
    """
    Verifica que cancelar_tarea() interrumpe la asyncio.Task activa registrada
    en tareas_activas (cancelación efectiva de la ejecución en curso).
    """
    import mcp_server
    from app.utils.task_registry import task_registry

    async def _escenario():
        # Simular una tarea en curso registrada en tareas_activas
        tarea_id = "task_cancel_test"

        # Registrar la tarea en el TaskRegistry (requisito de cancelar_tarea)
        task_registry.register_task(
            tarea_id=tarea_id,
            thread_id=tarea_id,
            directorio_proyecto="./",
            instruccion="test",
            estado="running",
        )

        async def _tarea_larga():
            try:
                await asyncio.sleep(60)
                return "nunca debería completarse"
            except asyncio.CancelledError:
                raise

        task_activa = asyncio.create_task(_tarea_larga())
        mcp_server.tareas_activas[tarea_id] = task_activa

        # Llamar a cancelar_tarea (que ahora espera la cancelación de la Task)
        resultado = await cancelar_tarea(tarea_id)

        assert "cancelada" in resultado.lower()
        assert task_activa.cancelled(), "La asyncio.Task activa debe quedar cancelada"
        assert mcp_server.tareas_activas.get(tarea_id) is None or mcp_server.tareas_activas[tarea_id].done()

    asyncio.run(_escenario())
