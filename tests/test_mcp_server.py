import sys
import os
import pytest
import asyncio
import anyio
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import visualizar_cambios, delegar_tarea_a_equipo_ia, obtener_git_diff, notificar_progreso, generar_markdown_pausa, consultar_estado_tarea, listar_tareas, cancelar_tarea, _es_error_real

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

    # La instruccion "Crear helpers" NO es un rechazo explícito,
    # por lo que el servidor debe re-pausar con feedback del usuario
    assert "🛑 AI ASSISTANT" in resultado
    assert "Creado archivo app/utils/helpers.py con funciones aux." in resultado
    assert "👉 ✅ = approve" in resultado
    assert "Revisión de Código (Feedback del Usuario Recibido)" in resultado
    assert "NO aprobó ni rechazó explícitamente" in resultado
    
    # Verificar que la función retorna el markdown de re-pausa (no procesa como rechazo)
    assert "**Estado/Status:** ⏸️ PAUSA_2" in resultado

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

    assert "🛑 AI ASSISTANT" in resultado
    assert "Formulario de Aprobación de Plan de Acción" in resultado
    assert "Plan de prueba" in resultado
    assert "👉 ✅ = approve" in resultado
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

    assert "✅ task: task_456" in resultado
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
    assert "✅ task: task_stdout_check" in resultado

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

    assert "✅ task:" in resultado
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

    assert "✅ task:" in resultado
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

    assert "🛑 AI ASSISTANT" in resultado
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

    assert "🚨 ⏱️ TIMEOUT" in resultado
    assert "task_timeout" in resultado

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
    assert "- **ID:** `task_xyz123`" in reporte
    assert "- **Dir:** `/ruta/proyecto`" in reporte
    assert "- **Estado/Status:** ⏸️ PAUSA_1" in reporte

    # Verificar que la explicación y la tabla de pasos aparecen en el reporte
    assert "#### 📄" in reporte
    assert "Esta es la explicación detallada de la arquitectura modular." in reporte
    assert "#### 📋" in reporte
    assert "| 1 | Crear archivo de configuración | `config.py` | — |" in reporte
    assert "| 2 | Implementar lógica principal | `main.py` | ✅ |" in reporte

    # Verificar orden estricto: El plan de acción (título, explicación, tabla) debe aparecer ANTES
    # de los avisos para la IA ("🛑 AI ASSISTANT") y de las instrucciones del usuario ("👉 ✅ = approve").
    pos_titulo = reporte.find("### 📌 Plan de Arquitectura Propuesto")
    pos_explicacion = reporte.find("Esta es la explicación detallada de la arquitectura modular.")
    pos_tabla = reporte.find("#### 📋")
    pos_ia = reporte.find("🛑 AI ASSISTANT")
    pos_humano = reporte.find("👉 ✅ = approve")

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
    assert "#### 🔍" in reporte
    assert "+print('hello')" in reporte

    pos_explicacion = reporte.find("Se creó el archivo app.py.")
    pos_diff = reporte.find("#### 🔍")
    pos_ia = reporte.find("🛑 AI ASSISTANT")

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
    with patch.dict(os.environ, {"FASTMCP_TRANSPORT": "sse"}, clear=False):
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
                port=8000,
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


# =============================================================================
# Pruebas del formato neutralizado (sin prosa en idioma natural)
# =============================================================================

def test_generar_markdown_pausa_sin_prosa_espanola():
    """El reporte de pausa NO debe contener las etiquetas fijas en español del formato antiguo."""
    pasos_ejemplo = [
        {"tarea": "Crear archivo de configuración", "archivo": "config.py", "requiere_test": False},
    ]
    reporte = generar_markdown_pausa(
        tarea_id="task_xyz123",
        tipo_pausa="PAUSA_1",
        titulo="Plan de Arquitectura Propuesto",
        explicacion="Esta es la explicación detallada.",
        pasos=pasos_ejemplo,
        directorio_proyecto="/ruta/proyecto"
    )

    cadenas_prohibidas = [
        "ATENCIÓN ASISTENTE DE IA",
        "INSTRUCCIONES PARA EL USUARIO HUMANO",
        "Plan de Pasos Propuestos",
        "Requiere aprobación humana",
        "PARA APROBAR",
        "PARA RECHAZAR",
        "ID Tarea",
        "Explicación / Resumen",
        "Git Diff / Cambios en Disco",
    ]
    for cadena in cadenas_prohibidas:
        assert cadena not in reporte, f"La cadena fija en español '{cadena}' no debe aparecer en el formato neutralizado."


def test_generar_markdown_pausa_estructura_neutralizada():
    """El reporte de pausa debe contener la estructura neutralizada con iconos."""
    pasos_ejemplo = [
        {"tarea": "Paso de prueba", "archivo": "a.py", "requiere_test": True},
    ]
    reporte = generar_markdown_pausa(
        tarea_id="task_xyz123",
        tipo_pausa="PAUSA_1",
        titulo="Título Dinámico",
        explicacion="Explicación dinámica.",
        pasos=pasos_ejemplo,
        directorio_proyecto="/ruta/proyecto"
    )

    assert "### 📌 Título Dinámico" in reporte
    assert "- **ID:** `task_xyz123`" in reporte
    assert "- **Dir:** `/ruta/proyecto`" in reporte
    assert "- **Estado/Status:** ⏸️ PAUSA_1" in reporte
    assert "#### 📄" in reporte
    assert "#### 📋" in reporte
    assert "| # | 📝 | 📄 | 🧪 |" in reporte
    assert "🛑 AI ASSISTANT" in reporte
    assert "👉 ✅ = approve / ❌ = reject + feedback" in reporte


def test_generar_markdown_pausa_tabla_usa_iconos():
    """La columna requiere_test de la tabla debe usar iconos ✅/— en lugar de Si/No."""
    pasos_ejemplo = [
        {"tarea": "A", "archivo": "a.py", "requiere_test": True},
        {"tarea": "B", "archivo": "b.py", "requiere_test": False},
    ]
    reporte = generar_markdown_pausa(
        tarea_id="task_icons",
        tipo_pausa="PAUSA_1",
        titulo="Título",
        explicacion="Explicación",
        pasos=pasos_ejemplo
    )

    assert "| 1 | A | `a.py` | ✅ |" in reporte
    assert "| 2 | B | `b.py` | — |" in reporte
    assert "| Si |" not in reporte
    assert "| No |" not in reporte


def test_generar_markdown_pausa_con_diff_neutralizado():
    """La sección de diff debe marcarse solo con el icono 🔍, sin encabezado textual."""
    diff_ejemplo = "diff --git a/app.py b/app.py\n+print('hello')"
    reporte = generar_markdown_pausa(
        tarea_id="task_diff789",
        tipo_pausa="PAUSA_2",
        titulo="Revisión de Código Desarrollado",
        explicacion="Se creó el archivo app.py.",
        diff_git=diff_ejemplo,
        directorio_proyecto="./"
    )

    assert "#### 🔍" in reporte
    assert "+print('hello')" in reporte
    assert "Git Diff / Cambios en Disco" not in reporte


def test_delegar_tarea_approve_sin_tarea_id_neutralizado():
    """El error de aprobación sin tarea_id debe estar neutralizado (sin prosa en español)."""
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="x",
        directorio_proyecto="./",
        approve=True
    ))

    assert "🚨 approve: tarea_id required" in resultado
    assert "No puedes aprobar" not in resultado


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_completado_sin_prosa_espanola(mock_aget_state, mock_ainvoke, mock_git_diff):
    """El mensaje de completado y el reporte final no deben contener prosa fija en español."""
    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "ok",
        "errores_terminal": "0"
    }
    mock_aget_state.return_value = mock_state_final

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea neutral",
        directorio_proyecto="./",
        tarea_id="task_neutral"
    ))

    assert "✅ task: task_neutral" in resultado
    assert "Tarea completada exitosamente" not in resultado
    assert "ADVERTENCIA" not in resultado


@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_error_interno_sin_prosa_espanola(mock_aget_state):
    """El mensaje de error interno no debe contener prosa fija en español."""
    mock_aget_state.side_effect = RuntimeError("boom")

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea con error",
        directorio_proyecto="./",
        tarea_id="task_err"
    ))

    assert "🚨 task: task_err: boom" in resultado
    assert "error interno" not in resultado


# =============================================================================
# Pruebas de la ruta de rechazo (O0A: Command sin as_node)
# =============================================================================

@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.Command")
@patch("mcp_server.agentes_app.aupdate_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_rechazo_pausa_2_genera_command_goto_codificador(mock_aget_state, mock_ainvoke, mock_aupdate_state, mock_command, mock_git_diff):
    """El rechazo en Pausa 2 aplica aupdate_state(as_node='agente_revisor') y Command solo con goto."""
    from langchain_core.messages import HumanMessage

    estado_pausado = MagicMock()
    estado_pausado.next = ["agente_revisor"]
    estado_pausado.values = {"codigo_escrito": "Código en revisión"}

    estado_final = MagicMock()
    estado_final.next = []
    estado_final.values = {"codigo_escrito": "Código en revisión", "errores_terminal": "0 errores"}

    mock_aget_state.side_effect = [estado_pausado, estado_final]

    asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="rechazo con feedback",
        directorio_proyecto="./",
        tarea_id="task_rechazo_p2",
        approve=False
    ))

    args_upd, kwargs_upd = mock_aupdate_state.call_args
    assert kwargs_upd["as_node"] == "agente_revisor"
    update = args_upd[1]
    assert update["loop_counter"] == 0
    assert update["errores_terminal"] == "El usuario rechazó el código con este feedback: rechazo con feedback"
    feedback = update["messages"][0]
    assert isinstance(feedback, HumanMessage)
    assert feedback.content == "Rechazo de código: rechazo con feedback"
    # El Command ya no transporta update: solo redirige el goto.
    assert mock_command.call_args.kwargs == {"goto": "agente_codificador"}
    assert mock_ainvoke.await_count == 1
    assert mock_ainvoke.await_args.args[0] is mock_command.return_value


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.Command")
@patch("mcp_server.agentes_app.aupdate_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_rechazo_pausa_1_genera_command_goto_planificador(mock_aget_state, mock_ainvoke, mock_aupdate_state, mock_command, mock_git_diff):
    """El rechazo en Pausa 1 aplica aupdate_state(as_node='agente_codificador') y Command solo con goto."""
    from langchain_core.messages import HumanMessage

    estado_pausado = MagicMock()
    estado_pausado.next = ["agente_codificador"]
    estado_pausado.values = {"plan_de_accion": {"explicacion_arquitectura": "Plan rechazado", "pasos": []}}

    estado_final = MagicMock()
    estado_final.next = []
    estado_final.values = {"codigo_escrito": "ok", "errores_terminal": "0 errores"}

    mock_aget_state.side_effect = [estado_pausado, estado_final]

    asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="no apruebo el plan de acción",
        directorio_proyecto="./",
        tarea_id="task_rechazo_p1",
        approve=False
    ))

    args_upd, kwargs_upd = mock_aupdate_state.call_args
    assert kwargs_upd["as_node"] == "agente_codificador"
    update = args_upd[1]
    assert update["loop_counter"] == 0
    assert "errores_terminal" not in update
    feedback = update["messages"][0]
    assert isinstance(feedback, HumanMessage)
    assert feedback.content == "El usuario rechazó el plan de acción: no apruebo el plan de acción"
    # El Command ya no transporta update: solo redirige el goto.
    assert mock_command.call_args.kwargs == {"goto": "agente_planificador"}
    assert mock_ainvoke.await_count == 1
    assert mock_ainvoke.await_args.args[0] is mock_command.return_value


@pytest.mark.parametrize("instruccion", ["", "   "])
@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.Command")
@patch("mcp_server.agentes_app.aupdate_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_rechazo_feedback_vacio_repausa_pausa_2(mock_aget_state, mock_ainvoke, mock_aupdate_state, mock_command, mock_git_diff, instruccion):
    """Feedback vacío o con solo espacios en Pausa 2 re-pausa sin construir Command ni reanudar."""
    estado_pausado = MagicMock()
    estado_pausado.next = ["agente_revisor"]
    estado_pausado.values = {"codigo_escrito": "Código en revisión"}

    mock_aget_state.return_value = estado_pausado

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion=instruccion,
        directorio_proyecto="./",
        tarea_id="task_repausa_2",
        approve=False
    ))

    assert "Revisión de Código (Feedback del Usuario Recibido)" in resultado
    assert "NO aprobó ni rechazó explícitamente" in resultado
    mock_aupdate_state.assert_not_awaited()
    mock_command.assert_not_called()
    mock_ainvoke.assert_not_awaited()


@pytest.mark.parametrize("instruccion", ["", "   "])
@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.Command")
@patch("mcp_server.agentes_app.aupdate_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_rechazo_feedback_vacio_repausa_pausa_1(mock_aget_state, mock_ainvoke, mock_aupdate_state, mock_command, mock_git_diff, instruccion):
    """Feedback vacío o con solo espacios en Pausa 1 re-pausa sin construir Command ni reanudar."""
    estado_pausado = MagicMock()
    estado_pausado.next = ["agente_codificador"]
    estado_pausado.values = {"plan_de_accion": {"explicacion_arquitectura": "Plan propuesto", "pasos": []}}

    mock_aget_state.return_value = estado_pausado

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion=instruccion,
        directorio_proyecto="./",
        tarea_id="task_repausa_1",
        approve=False
    ))

    assert "Plan de Acción (Feedback del Usuario Recibido)" in resultado
    assert "NO aprobó ni rechazó explícitamente" in resultado
    mock_aupdate_state.assert_not_awaited()
    mock_command.assert_not_called()
    mock_ainvoke.assert_not_awaited()


# =============================================================================
# Pruebas del fix: no marcar 'completed' sin evidencia de trabajo en disco
# =============================================================================

@pytest.mark.parametrize("texto,esperado", [
    # Errores reales → True
    ("Error: el archivo no existe", True),
    ("Abortado: el Agente Codificador excedió el límite máximo", True),
    ("Límite de revisiones alcanzado. Últimos errores: boom", True),
    ("Traceback (most recent call last)", True),
    ("fallo en la prueba test_x", True),
    # Mensajes de éxito del Revisor → False
    ("Ninguno. Código probado y aprobado.", False),
    ("Ninguno. Verificación completada tras múltiples iteraciones sin errores.", False),
    ("No se requirieron pruebas para este código. Aprobado automáticamente.", False),
    ("No se requirieron pruebas para este plan. Aprobado automáticamente.", False),
    ("Ninguno. Código aprobado en revisión.", False),
    ("No se ejecutaron pruebas de terminal pero la revisión se concluyó sin errores reportados.", False),
    ("0 errores", False),
    ("0", False),
    # Vacíos → False
    ("", False),
    ("-", False),
    (None, False),
])
def test_es_error_real(texto, esperado):
    """_es_error_real distingue errores reales de mensajes de éxito del Revisor."""
    assert _es_error_real(texto) is esperado


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_sin_evidencia_no_marca_completed(mock_aget_state, mock_ainvoke, mock_git_diff):
    """El grafo llega a END sin código escrito ni diff: NO debe marcarse 'completed'."""
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_sin_trabajo",
        directorio_proyecto="./",
        estado="running",
    )

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": None,
        "errores_terminal": "Ninguno. Código probado y aprobado.",
    }
    mock_aget_state.return_value = mock_state_final

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea sin trabajo",
        directorio_proyecto="./",
        tarea_id="task_sin_trabajo",
    ))

    tarea = task_registry.get_task("task_sin_trabajo")
    assert tarea["estado"] == "error", f"Se esperaba 'error', se obtuvo '{tarea['estado']}'"
    assert "working tree limpio" in tarea["detalle"]
    assert "✅ task: task_sin_trabajo" in resultado
    task_registry.clear()


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_con_codigo_escrito_marca_completed(mock_aget_state, mock_ainvoke, mock_git_diff):
    """Con codigo_escrito presente, la tarea se marca 'completed'."""
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_con_trabajo",
        directorio_proyecto="./",
        estado="running",
    )

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "Se creó app/main.py con la lógica principal.",
        "errores_terminal": "Ninguno. Código probado y aprobado.",
    }
    mock_aget_state.return_value = mock_state_final

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea con trabajo",
        directorio_proyecto="./",
        tarea_id="task_con_trabajo",
    ))

    tarea = task_registry.get_task("task_con_trabajo")
    assert tarea["estado"] == "completed"
    assert "Se creó app/main.py" in resultado
    task_registry.clear()


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_con_diff_marca_completed(mock_aget_state, mock_ainvoke, mock_git_diff):
    """Con diff git no vacío, la tarea se marca 'completed' aunque no haya resumen."""
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_con_diff",
        directorio_proyecto="./",
        estado="running",
    )

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": None,
        "errores_terminal": "Ninguno. Código probado y aprobado.",
    }
    mock_aget_state.return_value = mock_state_final
    mock_git_diff.return_value = "diff --git a/app/main.py b/app/main.py\n+print('hola')"

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea con diff",
        directorio_proyecto="./",
        tarea_id="task_con_diff",
    ))

    tarea = task_registry.get_task("task_con_diff")
    assert tarea["estado"] == "completed"
    task_registry.clear()


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_analisis_puro_marca_completed(mock_aget_state, mock_ainvoke, mock_git_diff):
    """Un análisis puro (analisis_final) llega a END sin código: se marca 'completed'."""
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_analisis",
        directorio_proyecto="./",
        estado="running",
    )

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": None,
        "errores_terminal": None,
        "analisis_final": "Este proyecto implementa un flujo multi-agente.",
    }
    mock_aget_state.return_value = mock_state_final

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="analiza este proyecto",
        directorio_proyecto="./",
        tarea_id="task_analisis",
    ))

    tarea = task_registry.get_task("task_analisis")
    assert tarea["estado"] == "completed"
    assert "Este proyecto implementa un flujo multi-agente." in resultado
    task_registry.clear()


@patch("mcp_server.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_delegar_tarea_con_error_real_marca_error(mock_aget_state, mock_ainvoke, mock_git_diff):
    """Con errores reales en errores_terminal, la tarea se marca 'error'."""
    from app.utils.task_registry import task_registry
    task_registry.clear()
    task_registry.register_task(
        tarea_id="task_error_real",
        directorio_proyecto="./",
        estado="running",
    )

    mock_state_final = MagicMock()
    mock_state_final.next = []
    mock_state_final.values = {
        "codigo_escrito": "Se escribió algo",
        "errores_terminal": "Abortado: el Agente Codificador excedió el límite máximo de 10 iteraciones",
    }
    mock_aget_state.return_value = mock_state_final

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Tarea con error",
        directorio_proyecto="./",
        tarea_id="task_error_real",
    ))

    tarea = task_registry.get_task("task_error_real")
    assert tarea["estado"] == "error"
    assert "excedió el límite máximo" in tarea["detalle"]
    task_registry.clear()
