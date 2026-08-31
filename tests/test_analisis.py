import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from langchain_core.prompts import ChatPromptTemplate

from app.agents.agente_planificador import _es_peticion_analisis
from app.utils.files import File
from mcp_server import delegar_tarea_a_equipo_ia


def _cargar_prompt_analisis() -> str:
    """Carga el contenido real del prompt de análisis desde el repositorio."""
    ruta = Path(__file__).resolve().parent.parent / "app" / "prompts" / "analisis_prompt.md"
    return ruta.read_text(encoding="utf-8")


def test_analisis_prompt_incluye_yagni():
    """Verifica que el prompt contiene la directiva de alcance mínimo YAGNI/KISS."""
    prompt = _cargar_prompt_analisis()
    assert "ALCANCE MÍNIMO (YAGNI/KISS)" in prompt
    assert "sobre-ingeniería" in prompt


def test_analisis_prompt_incluye_concision():
    """Verifica que las secciones 2 y 3 del reporte exigen concisión (3-4 viñetas)."""
    prompt = _cargar_prompt_analisis()
    assert "3-4" in prompt
    assert "concis" in prompt


def test_analisis_prompt_referencia_indice():
    """Verifica que el prompt referencia el índice del proyecto como fuente de evidencia."""
    prompt = _cargar_prompt_analisis()
    assert "ÍNDICE DEL PROYECTO" in prompt


def test_analisis_prompt_placeholder_directorio():
    """Verifica que el placeholder {directorio} aparece exactamente dos veces (línea 2 y línea 7 del prompt)."""
    prompt = _cargar_prompt_analisis()
    assert prompt.count("{directorio}") == 2


def test_analisis_prompt_interpola_sin_errores():
    """Verifica que el prompt se interpola sin errores por ChatPromptTemplate."""
    prompt = _cargar_prompt_analisis()
    plantilla = ChatPromptTemplate.from_messages([
        ("system", prompt),
        ("human", "Requerimiento a analizar:\n{instruccion}"),
    ])
    resultado = plantilla.invoke({"directorio": "./test_dir", "instruccion": "analiza el módulo"})
    assert "./test_dir" in str(resultado)


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

    # Formato actual del reporte de análisis puro (mcp_server.py): "✅ task: <id>\n\n📋 <análisis>"
    assert "✅ task: task_analisis" in resultado
    assert "📋 Análisis detallado del módulo X" in resultado


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