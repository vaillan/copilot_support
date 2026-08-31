"""
Tests para el helper `_get_args` y el bug bloqueante de tool_call['args'] como string JSON.

El LLM (p.ej. deepseek) puede devolver `tool_call["args"]` como un STRING JSON
en lugar de un dict. Estos tests verifican que los 3 agentes no lanzan
`'str' object has no attribute 'get'` en ese escenario.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.utils.args_utils import _get_args
from app.agents.agente_planificador import agente_planificador
from app.agents.agente_codificador import agente_codificador
from app.agents.agente_revisor import agente_revisor


def _ai_message_con_args_string(tool_call: dict) -> AIMessage:
    """
    Construye un AIMessage cuyo tool_call tiene 'args' como STRING JSON.

    AIMessage (pydantic) valida que args sea dict al construirlo, así que
    creamos el mensaje con args dict y luego mutamos el tool_call a string,
    simulando el comportamiento real del LLM (deepseek).
    """
    tool_call_dict = dict(tool_call)
    args_original = tool_call_dict.get("args")
    if isinstance(args_original, dict):
        tool_call_dict["args"] = args_original
    else:
        tool_call_dict["args"] = {}
    msg = AIMessage(content="", tool_calls=[tool_call_dict])
    # Mutar args a string JSON (como lo devuelve el LLM real)
    msg.tool_calls[0]["args"] = json.dumps(args_original) if isinstance(args_original, dict) else str(args_original)
    return msg


# ---------------------------------------------------------------------------
# Tests unitarios de _get_args
# ---------------------------------------------------------------------------

def test_get_args_con_dict():
    """_get_args con args dict devuelve el dict tal cual."""
    tool_call = {"name": "x", "args": {"clave": "valor"}, "id": "1"}
    assert _get_args(tool_call) == {"clave": "valor"}


def test_get_args_con_string_json_valido():
    """_get_args con string JSON válido devuelve el dict parseado."""
    tool_call = {"name": "x", "args": '{"clave": "valor", "n": 1}', "id": "1"}
    assert _get_args(tool_call) == {"clave": "valor", "n": 1}


def test_get_args_con_string_invalido():
    """_get_args con string JSON inválido devuelve {}."""
    tool_call = {"name": "x", "args": "esto no es json {", "id": "1"}
    assert _get_args(tool_call) == {}


def test_get_args_con_string_json_no_dict():
    """_get_args con string JSON que parsea a lista devuelve {}."""
    tool_call = {"name": "x", "args": '["a", "b"]', "id": "1"}
    assert _get_args(tool_call) == {}


def test_get_args_sin_clave_args():
    """_get_args sin clave 'args' devuelve {}."""
    tool_call = {"name": "x", "id": "1"}
    assert _get_args(tool_call) == {}


def test_get_args_con_tipo_raro():
    """_get_args con args de tipo no soportado (int, None) devuelve {}."""
    assert _get_args({"name": "x", "args": 42, "id": "1"}) == {}
    assert _get_args({"name": "x", "args": None, "id": "1"}) == {}


# ---------------------------------------------------------------------------
# Tests de integración: LLM devuelve tool_call con args como string JSON
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="test")],
        "directorio_proyecto": "./",
        "plan_de_accion": None,
        "codigo_escrito": "",
        "errores_terminal": "",
        "loop_counter": 0,
        "revision_count": 0
    }


@patch('app.agents.agente_planificador.get_planner_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_planificador_args_string_json(mock_get_file, mock_get_llm, mock_state):
    """El planificador no lanza excepción cuando args es string JSON."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    tool_call = {
        "name": "entregar_plan_de_accion",
        "args": {
            "explicacion_arquitectura": "plan desde string",
            "pasos": [{"archivo": "app.py", "tarea": "implementar", "requiere_test": False}],
        },
        "id": "call_str_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = _ai_message_con_args_string(tool_call)

    result = agente_planificador(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert update["plan_de_accion"]["explicacion_arquitectura"] == "plan desde string"


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_codificador_args_string_json(mock_get_file, mock_get_llm, mock_state):
    """El codificador no lanza excepción cuando args es string JSON."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_state["messages"] = [
        HumanMessage(content="haz algo"),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "a.py", "text": "code"}, "id": "w1"}])
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios desde string"},
        "id": "call_str_2"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = _ai_message_con_args_string(tool_call)

    result = agente_codificador(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_revisor"
    update = result.update or {}
    assert update["codigo_escrito"] == "cambios desde string"


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_revisor_args_string_json(mock_get_file, mock_get_llm, mock_state):
    """El revisor no lanza excepción cuando args es string JSON."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": True, "requiere_pruebas": True},
        "id": "call_str_3"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = _ai_message_con_args_string(tool_call)

    result = agente_revisor(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador" or result.goto == "__end__"
    update = result.update or {}
    assert "Ninguno. Código probado y aprobado." in update.get("errores_terminal", "")


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_revisor_args_string_json_rechazo(mock_get_file, mock_get_llm, mock_state):
    """El revisor procesa correctamente un rechazo con args como string JSON."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": False, "requiere_pruebas": True, "reporte_errores": "Falla test desde string"},
        "id": "call_str_4"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = _ai_message_con_args_string(tool_call)

    result = agente_revisor(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert update["errores_terminal"] == "Falla test desde string"


@patch('app.agents.agente_planificador.get_planner_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_planificador_args_string_json_invalido(mock_get_file, mock_get_llm, mock_state):
    """Anti-bucle: con args string inválido (parsea a {}) NO se lanza excepción
    ni se acepta un plan vacío; se pide reintento con error de herramienta."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    tool_call = {
        "name": "entregar_plan_de_accion",
        "args": {"explicacion_arquitectura": "x", "pasos": []},
        "id": "call_str_5"
    }
    # Simular args como string JSON inválido
    msg = AIMessage(content="", tool_calls=[dict(tool_call)])
    msg.tool_calls[0]["args"] = "no es json {{{"
    mock_llm.bind_tools.return_value.invoke.return_value = msg

    result = agente_planificador(mock_state)

    assert isinstance(result, Command)
    assert result.goto == "agente_planificador"
    update = result.update or {}
    assert "plan_de_accion" not in update
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)
    assert messages[1].tool_call_id == "call_str_5"
    assert "ERROR" in messages[1].content