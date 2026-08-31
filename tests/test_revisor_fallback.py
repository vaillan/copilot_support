import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from app.agents.agente_revisor import agente_revisor, _texto_indica_aprobacion


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


@pytest.mark.parametrize("texto", [
    "El código está aprobado",
    "Todo correcto",
    "sin errores encontrados",
    "revisión exitosa",
    "revisión aprobada",
    "revisión correcta",
    "no requiere pruebas",
    "pasó las pruebas",
    "paso las pruebas",
])
def test_texto_indica_aprobacion_espanol(texto):
    assert _texto_indica_aprobacion(texto) is True


@pytest.mark.parametrize("texto", [
    "The code is approved",
    "Everything is correct",
    "no errors found",
    "successful review",
    "no tests required",
    "passed the tests",
    "all tests pass",
])
def test_texto_indica_aprobacion_ingles(texto):
    assert _texto_indica_aprobacion(texto) is True


@pytest.mark.parametrize("texto", [
    "El código no aprobado",
    "no aprobado",
    "not approved",
    "The code is not approved",
    "tests failed",
    "el código falló",
    "no está aprobado",
    "no fue aprobado",
    "incorrect",
    "incorrecto",
])
def test_texto_indica_aprobacion_rechazo_explicito(texto):
    assert _texto_indica_aprobacion(texto) is False


@pytest.mark.parametrize("texto", [
    "He revisado el código",
    "I reviewed the code",
    "Revisión completada",
])
def test_texto_indica_aprobacion_texto_neutro(texto):
    assert _texto_indica_aprobacion(texto) is False


@pytest.mark.parametrize("texto", [
    "desaprobado",
    "El código está desaprobado",
    "incorrect",
])
def test_texto_indica_aprobacion_limites_de_palabra(texto):
    assert _texto_indica_aprobacion(texto) is False


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_texto_aprobado_ingles(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="The code is approved and all tests pass."
    )

    result = agente_revisor(mock_state)
    assert result.goto == END
    update = result.update or {}
    assert "Código aprobado" in update.get("errores_terminal", "")


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_texto_no_aprobado(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="El código no aprobado, hay errores."
    )

    result = agente_revisor(mock_state)
    assert result.goto == "agente_revisor"
    update = result.update or {}
    assert "Código aprobado" not in update.get("errores_terminal", "")


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_texto_neutro(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="He revisado el código."
    )

    result = agente_revisor(mock_state)
    assert result.goto == "agente_revisor"