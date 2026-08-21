import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from app.agents.agente_planificador import _es_peticion_analisis
from mcp_server import delegar_tarea_a_equipo_ia


def test_es_peticion_analisis_detecta_analisis():
    """Verifica que las instrucciones de análisis puro se detectan correctamente."""
    assert _es_peticion_analisis("analiza este código") is True
    assert _es_peticion_analisis("explica cómo funciona") is True
    assert _es_peticion_analisis("resume el proyecto") is True


def test_es_peticion_analisis_no_detecta_creacion():
    """Verifica que la presencia de palabras de creación anula la detección de análisis."""
    assert _es_peticion_analisis("crea una función") is False
    assert _es_peticion_analisis("implementa y analiza el módulo") is False


@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_reporte_final_incluye_analisis(mock_ainvoke, mock_aget_state):
    """Verifica que el reporte final del MCP incluye el análisis puro cuando el grafo llega a END."""
    mock_state = MagicMock()
    mock_state.next = []
    mock_state.values = {
        "analisis_final": "Análisis detallado del módulo X",
        "codigo_escrito": "No se reportó código.",
        "errores_terminal": "Sin errores.",
    }
    # Ambas llamadas a aget_state devuelven el mismo estado (inicial y final).
    mock_aget_state.return_value = mock_state

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="analiza el módulo",
        directorio_proyecto="./",
        tarea_id="task_analisis",
    ))

    assert "✅ Análisis completado por el equipo LangGraph" in resultado
    assert "Análisis detallado del módulo X" in resultado


def test_es_peticion_analisis_con_refactorizacion_contexto():
    """Verifica que 'refactorizacion' como sustantivo de contexto NO anula el análisis."""
    assert _es_peticion_analisis(
        "Realiza el analisis para los demas tipos de facturas, en este caso solo se cubrio la refactorizacion para estimaciones"
    ) is True


def test_es_peticion_analisis_analiza_y_luego_implementa():
    """Verifica que 'analiza y luego implementa' se considera creación (no análisis puro)."""
    assert _es_peticion_analisis("analiza y luego implementa el módulo") is False


def test_es_peticion_analisis_frases_inicio():
    """Verifica que las frases de análisis al inicio de la instrucción se detectan."""
    assert _es_peticion_analisis("haz el analisis del proyecto") is True
    assert _es_peticion_analisis("realiza un analisis de la arquitectura") is True