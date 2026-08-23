"""Tests unitarios para app/mcp/reporting.py.

Cubre los helpers puros de reporting de forma directa (importando desde
``app.mcp.reporting``, NO desde ``mcp_server``): ``generar_markdown_pausa`` y
``visualizar_cambios``. Se mockean ``obtener_git_diff`` y ``notificar_progreso``
para no depender del grafo LangGraph ni de git real. Sigue el estilo de
tests/test_mcp_server.py (pytest + unittest.mock + asyncio.run).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp.reporting import generar_markdown_pausa, visualizar_cambios


# ---------------------------------------------------------------------------
# generar_markdown_pausa
# ---------------------------------------------------------------------------

def test_generar_markdown_pausa_con_cambios():
    """Caso (a): con diff_git -> el markdown contiene la sección de cambios."""
    diff = "diff --git a/app/main.py b/app/main.py\n+print('hola')"
    markdown = generar_markdown_pausa(
        tarea_id="task_1",
        tipo_pausa="aprobacion_plan",
        titulo="Plan de Acción",
        explicacion="Explicación de prueba",
        pasos=[{"tarea": "Crear tests", "archivo": "tests/test_x.py", "requiere_test": True}],
        diff_git=diff,
        directorio_proyecto="./",
    )

    assert "### 📌 Plan de Acción" in markdown
    assert "**ID Tarea:** `task_1`" in markdown
    assert "**Directorio:** `./`" in markdown
    assert "🔍 Git Diff / Cambios en Disco:" in markdown
    assert "diff --git a/app/main.py b/app/main.py" in markdown
    assert "+print('hola')" in markdown
    assert "ATENCIÓN ASISTENTE DE IA" in markdown
    assert "INSTRUCCIONES PARA EL USUARIO HUMANO" in markdown


def test_generar_markdown_pausa_sin_cambios():
    """Caso (a'): sin diff_git -> no incluye la sección de cambios."""
    markdown = generar_markdown_pausa(
        tarea_id="task_2",
        tipo_pausa="revision",
        titulo="Revisión",
        explicacion="Sin cambios en disco",
    )

    assert "Git Diff / Cambios en Disco" not in markdown
    assert "### 📌 Revisión" in markdown


def test_generar_markdown_pausa_con_pasos():
    """Caso (a''): con pasos -> genera la tabla de plan con requiere_test."""
    pasos = [
        {"tarea": "Crear tests", "archivo": "tests/test_a.py", "requiere_test": True},
        {"tarea": "Actualizar docs", "archivo": "README.md", "requiere_test": False},
    ]
    markdown = generar_markdown_pausa(
        tarea_id="task_3",
        tipo_pausa="aprobacion_plan",
        titulo="Plan",
        explicacion="Explicación",
        pasos=pasos,
    )

    assert "📋 Plan de Pasos Propuestos:" in markdown
    assert "| 1 | Crear tests | `tests/test_a.py` | Si |" in markdown
    assert "| 2 | Actualizar docs | `README.md` | No |" in markdown


# ---------------------------------------------------------------------------
# visualizar_cambios
# ---------------------------------------------------------------------------

@patch("app.mcp.reporting.notificar_progreso", new_callable=AsyncMock)
@patch("app.mcp.reporting.obtener_git_diff", return_value="diff --git a/x.py b/x.py\n+linea")
def test_visualizar_cambios_con_diff(mock_git_diff, mock_notificar):
    """Caso (b): con diff en disco -> retorna markdown y notifica progreso."""
    resultado = asyncio.run(visualizar_cambios(directorio_proyecto="./"))

    assert "CAMBIOS DETALLADOS EN DISCO" in resultado
    assert "diff --git a/x.py b/x.py" in resultado
    mock_git_diff.assert_called_once_with("./")
    assert mock_notificar.called


@patch("app.mcp.reporting.notificar_progreso", new_callable=AsyncMock)
@patch("app.mcp.reporting.obtener_git_diff", return_value="")
def test_visualizar_cambios_sin_cambios(mock_git_diff, mock_notificar):
    """Caso (b'): sin tarea_id ni cambios -> mensaje de no encontrado."""
    resultado = asyncio.run(visualizar_cambios(directorio_proyecto="./"))

    assert "No se proporcionó un 'tarea_id' válido" in resultado
    mock_git_diff.assert_called_once_with("./")


@patch("app.mcp.reporting.notificar_progreso", new_callable=AsyncMock)
@patch("app.mcp.reporting.obtener_git_diff", return_value="")
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_visualizar_cambios_con_tarea_id(mock_aget_state, mock_git_diff, mock_notificar):
    """Caso (b''): con tarea_id -> incluye resumen de cambios y estado del flujo."""
    mock_state = MagicMock()
    mock_state.values = {
        "codigo_escrito": "Se modificó main.py",
        "directorio_proyecto": "./",
    }
    mock_state.next = ["agente_revisor"]
    mock_aget_state.return_value = mock_state

    resultado = asyncio.run(visualizar_cambios(tarea_id="task_123"))

    assert "RESUMEN DE CAMBIOS (Tarea 'task_123')" in resultado
    assert "Se modificó main.py" in resultado
    assert "Pausado antes de 'agente_revisor'" in resultado
    mock_aget_state.assert_awaited_once()