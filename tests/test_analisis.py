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


@patch("app.agents.agente_planificador.get_planner_llm")
def test_agente_planificador_camino_analisis_con_indice(mock_get_planner_llm):
    """Verifica que el camino alternativo inyecta el índice del proyecto y devuelve Command a END."""
    from app.agents.agente_planificador import agente_planificador
    from langgraph.graph import END
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="### Resumen Ejecutivo\nDiagnóstico completado.\n- [ ] TODO: revisar")
    mock_get_planner_llm.return_value = mock_llm

    state = {
        "instruccion_usuario": "analiza la arquitectura del sistema",
        "directorio_proyecto": "./test_dir",
        "project_index": {
            "arbol": {
                "main.py": {"tipo": "archivo", "lineas": 10},
                "app": {
                    "tipo": "directorio",
                    "hijos": {
                        "service.py": {"tipo": "archivo", "lineas": 20}
                    }
                }
            },
            "resumenes": {
                "main.py": {"resumen": "def main(): ...", "simbolos": ["main"]}
            }
        },
        "messages": [],
        "loop_counter": 0
    }

    cmd = agente_planificador(state)
    assert cmd.goto == END
    assert "analisis_final" in cmd.update
    assert "- [ ] TODO: revisar" in cmd.update["analisis_final"]
    assert mock_llm.invoke.called
    # Verificar que el prompt invocado contenía el contexto del índice
    prompt_invocado = mock_llm.invoke.call_args[0][0]
    prompt_texto = str(prompt_invocado)
    assert "ÍNDICE DEL PROYECTO" in prompt_texto
    assert "test_dir" in prompt_texto