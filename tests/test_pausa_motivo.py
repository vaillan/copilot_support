"""Tests de regresión para el fix del bucle de re-pausa (PAUSA 1 fantasma).

Cubre:
- Marcado de `pausa_motivo` en el estado ("retrabajo_qa" / "plan_nuevo").
- Limpieza de `pausa_motivo` cuando el codificador entrega.
- Renderizado diferenciado en mcp_server (re-trabajo QA vs. PAUSA 1).
- Cap configurable del bucle de herramientas (MCP_TOOL_LOOP_MAX).
- Pausas en nodos no canónicos (sin etiquetar como PAUSA 1/2).
- Sincronización del TaskRegistry en el camino de re-trabajo.
- Inclusión de la tool `terminal` en el codificador.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.agente_codificador import agente_codificador
from app.agents.agente_planificador import agente_planificador
from app.agents.agente_revisor import agente_revisor
from mcp_server import delegar_tarea_a_equipo_ia
from app.utils.task_registry import task_registry


@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="test")],
        "directorio_proyecto": "./",
        "plan_de_accion": None,
        "codigo_escrito": "",
        "errores_terminal": "",
        "loop_counter": 0,
        "revision_count": 0,
        "pausa_motivo": None,
    }


# ---------------------------------------------------------------------------
# Revisor: marca pausa_motivo="retrabajo_qa" en los caminos de rechazo
# ---------------------------------------------------------------------------
@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_revisor_rechazo_qa_marca_pausa_motivo(mock_get_file, mock_get_llm, mock_state):
    """QA rechaza (aprobado=False) → goto codificador con pausa_motivo='retrabajo_qa'."""
    mock_get_file.return_value = "system prompt"
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm

    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": False, "requiere_pruebas": True, "reporte_errores": "3 tests fallidos"},
        "id": "call_qa",
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_revisor(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert update.get("pausa_motivo") == "retrabajo_qa"
    assert "3 tests fallidos" in update.get("errores_terminal", "")


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_revisor_limite_iteraciones_marca_pausa_motivo(mock_get_file, mock_get_llm, mock_state):
    """loop_counter>5 con errores y revisiones disponibles → retrabajo_qa."""
    mock_get_file.return_value = "system prompt"
    mock_state["loop_counter"] = 6
    mock_state["revision_count"] = 0
    mock_state["messages"] = [
        HumanMessage(content="test"),
        ToolMessage(content="FAILED tests/test_x.py::test_y - AssertionError", tool_call_id="t1"),
    ]
    # Sin tool_calls el revisor entra por la rama de límite de iteraciones
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="no puedo continuar")

    result = agente_revisor(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert update.get("pausa_motivo") == "retrabajo_qa"


# ---------------------------------------------------------------------------
# Planificador: marca pausa_motivo="plan_nuevo"
# ---------------------------------------------------------------------------
@patch('app.agents.agente_planificador.get_planner_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_planificador_marca_pausa_motivo_plan_nuevo(mock_get_file, mock_get_llm, mock_state):
    """Plan entregado → goto codificador con pausa_motivo='plan_nuevo' (PAUSA 1 legítima)."""
    mock_get_file.return_value = "system prompt"
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm

    tool_call = {
        "name": "entregar_plan_de_accion",
        "args": {"explicacion_arquitectura": "plan test", "pasos": []},
        "id": "call_plan",
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_planificador(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert update.get("pausa_motivo") == "plan_nuevo"


# ---------------------------------------------------------------------------
# Codificador: limpia pausa_motivo al entregar y recibe la tool terminal
# ---------------------------------------------------------------------------
@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_codificador_limpia_pausa_motivo_al_entregar(mock_get_file, mock_get_llm, mock_state):
    """Al entregar con CodigoCompletado, pausa_motivo se resetea a None."""
    mock_get_file.return_value = "system prompt"
    mock_state["pausa_motivo"] = "retrabajo_qa"
    mock_state["messages"] = [
        HumanMessage(content="corrige"),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "a.py", "text": "code"}, "id": "w1"}]),
    ]

    tool_call = {"name": "CodigoCompletado", "args": {"resumen_cambios": "corregido"}, "id": "call_c"}
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_revisor"
    update = result.update or {}
    assert update.get("pausa_motivo") is None


def test_codificador_tools_incluyen_terminal():
    """Con CODIFICADOR_TERMINAL_ENABLED activo (default), el codificador recibe `terminal`."""
    from app.agents.agente_codificador import _get_tools

    _get_tools.cache_clear()
    try:
        tools = _get_tools("./")
        nombres = [t.name for t in tools]
        assert "terminal" in nombres
        assert "write_file" in nombres
    finally:
        _get_tools.cache_clear()


def test_codificador_tools_sin_terminal_cuando_deshabilitado(monkeypatch):
    """Con CODIFICADOR_TERMINAL_ENABLED=false, el codificador NO recibe `terminal`."""
    from app.agents.agente_codificador import _get_tools

    mock_settings = MagicMock()
    mock_settings.CODIFICADOR_TERMINAL_ENABLED = False
    monkeypatch.setattr("app.agents.agente_codificador.Settings", lambda: mock_settings)

    _get_tools.cache_clear()
    try:
        tools = _get_tools("./")
        nombres = [t.name for t in tools]
        assert "terminal" not in nombres
        assert "write_file" in nombres
    finally:
        _get_tools.cache_clear()


# ---------------------------------------------------------------------------
# mcp_server: renderizado diferenciado y cap configurable
# ---------------------------------------------------------------------------
def _mock_estado(next_nodos, values):
    estado = MagicMock()
    estado.next = next_nodos
    estado.values = values
    return estado


@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_pausa_codificador_retrabajo_qa_renderiza_mensaje_retrabajo(mock_ainvoke, mock_aget_state):
    """Pausa antes del codificador con pausa_motivo='retrabajo_qa' NO muestra PAUSA 1."""
    tarea_id = "task_retrabajo_qa_test"
    estado_pausado = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "retrabajo_qa", "errores_terminal": "AssertionError: 2 tests fallidos"},
    )
    estado_intermedio = _mock_estado(["nodo_herramientas_codificador"], {})
    estado_final = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "retrabajo_qa", "errores_terminal": "AssertionError: 2 tests fallidos"},
    )
    mock_aget_state.side_effect = [estado_pausado, estado_intermedio, estado_final]
    mock_ainvoke.return_value = {}

    mock_ctx = AsyncMock()
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Aprobar",
        directorio_proyecto="./",
        approve=True,
        tarea_id=tarea_id,
        ctx=mock_ctx,
    ))

    assert "Re-trabajo interno" in resultado
    assert "QA rechazó" in resultado
    assert "2 tests fallidos" in resultado
    assert "Formulario de Aprobación" not in resultado
    # El TaskRegistry debe quedar sincronizado como 'running' (re-trabajo activo)
    tarea = task_registry.get_task(tarea_id)
    assert tarea is not None
    assert tarea["estado"] == "running"


@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_pausa_codificador_plan_nuevo_renderiza_pausa_1(mock_ainvoke, mock_aget_state):
    """Pausa antes del codificador con pausa_motivo='plan_nuevo' SÍ muestra PAUSA 1."""
    tarea_id = "task_plan_nuevo_test"
    estado_pausado = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "plan_nuevo", "plan_de_accion": {"explicacion_arquitectura": "Plan nuevo", "pasos": []}},
    )
    estado_intermedio = _mock_estado(["nodo_herramientas_planificador"], {})
    estado_final = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "plan_nuevo", "plan_de_accion": {"explicacion_arquitectura": "Plan nuevo", "pasos": []}},
    )
    mock_aget_state.side_effect = [estado_pausado, estado_intermedio, estado_final]
    mock_ainvoke.return_value = {}

    mock_ctx = AsyncMock()
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Aprobar",
        directorio_proyecto="./",
        approve=True,
        tarea_id=tarea_id,
        ctx=mock_ctx,
    ))

    assert "Formulario de Aprobación de Plan de Acción" in resultado
    assert "Plan nuevo" in resultado
    assert "Re-trabajo interno" not in resultado
    tarea = task_registry.get_task(tarea_id)
    assert tarea is not None
    assert tarea["estado"] == "paused_planning"


@patch("mcp_server.Settings")
@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_tool_loop_cap_configurable(mock_ainvoke, mock_aget_state, mock_settings_cls):
    """El bucle de herramientas respeta MCP_TOOL_LOOP_MAX y no se pasa del cap."""
    mock_settings = MagicMock()
    mock_settings.MCP_TOOL_LOOP_MAX = 1
    mock_settings_cls.return_value = mock_settings

    tarea_id = "task_cap_test"
    estado_pausado = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "plan_nuevo", "plan_de_accion": {"explicacion_arquitectura": "Plan", "pasos": []}},
    )
    # El grafo sigue pausado en el mismo nodo tras cada ainvoke (ciclo de herramientas)
    estado_loop_1 = _mock_estado(["agente_codificador"], {"pausa_motivo": "plan_nuevo"})
    estado_loop_2 = _mock_estado(["agente_codificador"], {"pausa_motivo": "plan_nuevo"})
    estado_final = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "plan_nuevo", "plan_de_accion": {"explicacion_arquitectura": "Plan", "pasos": []}},
    )
    mock_aget_state.side_effect = [estado_pausado, estado_loop_1, estado_loop_2, estado_final]
    mock_ainvoke.return_value = {}

    mock_ctx = AsyncMock()
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Aprobar",
        directorio_proyecto="./",
        approve=True,
        tarea_id=tarea_id,
        ctx=mock_ctx,
    ))

    # Con cap=1: 1 ainvoke de reanudación + 1 del bucle = 2 invocaciones exactas
    assert mock_ainvoke.call_count == 2
    # El post-procesamiento informa el estado real (PAUSA 1 legítima aquí)
    assert "Formulario de Aprobación de Plan de Acción" in resultado


@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_pausa_no_canonica_renderiza_estado_real(mock_ainvoke, mock_aget_state):
    """Pausa en un nodo no canónico (bucle agotado) no se etiqueta como PAUSA 1/2."""
    tarea_id = "task_no_canonica_test"
    estado_pausado = _mock_estado(
        ["agente_codificador"],
        {"pausa_motivo": "plan_nuevo", "plan_de_accion": {"explicacion_arquitectura": "Plan", "pasos": []}},
    )
    estado_intermedio = _mock_estado(["nodo_herramientas_codificador"], {})
    estado_final = _mock_estado(["nodo_herramientas_codificador"], {})
    mock_aget_state.side_effect = [estado_pausado, estado_intermedio, estado_final]
    mock_ainvoke.return_value = {}

    mock_ctx = AsyncMock()
    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Aprobar",
        directorio_proyecto="./",
        approve=True,
        tarea_id=tarea_id,
        ctx=mock_ctx,
    ))

    assert "Ejecución pausada" in resultado
    assert "nodo_herramientas_codificador" in resultado
    assert "Formulario de Aprobación" not in resultado
    tarea = task_registry.get_task(tarea_id)
    assert tarea is not None
    assert tarea["estado"] == "running"
