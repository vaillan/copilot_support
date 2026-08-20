import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.utils.prompt_utils import escapar_llaves
from app.agents.agente_codificador import agente_codificador


def test_escapar_llaves_duplica_llaves():
    """Verifica que las llaves literales se escapen correctamente."""
    texto = "Optional[Dict[str, Any]] y {directorio}"
    resultado = escapar_llaves(texto)
    # Solo las llaves { } se escapan; los corchetes [ ] no se modifican
    assert resultado == "Optional[Dict[str, Any]] y {{directorio}}"


def test_escapar_llaves_vacio():
    """Verifica que una cadena vacía o None no rompa."""
    assert escapar_llaves("") == ""
    assert escapar_llaves(None) is None


def test_escapar_llaves_sin_llaves():
    """Verifica que el texto sin llaves no se modifique."""
    assert escapar_llaves("texto plano") == "texto plano"


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_agente_codificador_con_indice_con_llaves_no_lanza(mock_middleware, mock_get_file, mock_get_llm):
    """
    Verifica que el agente codificador NO lance excepción cuando el índice
    del proyecto contiene llaves literales de código fuente (Dict[str, Any],
    {directorio}, etc.) que antes rompían ChatPromptTemplate.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    mock_middleware.return_value = [HumanMessage(content="mensaje")]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios"},
        "id": "call_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", tool_calls=[tool_call]
    )

    state = {
        "messages": [HumanMessage(content="haz algo")],
        "directorio_proyecto": "./",
        "plan_de_accion": {"explicacion_arquitectura": "test", "pasos": []},
        "codigo_escrito": "",
        "errores_terminal": "",
        "loop_counter": 0,
        "revision_count": 0,
        # Índice con llaves literales que antes rompían el template
        "project_index": {
            "arbol": {},
            "resumenes": {
                "app/models/models.py": {
                    "resumen": "plan_de_accion: Optional[Dict[str, Any]]\nerrores_terminal: Optional[str]"
                },
                "app/prompts/codificador_prompt.md": {
                    "resumen": "El proyecto está ubicado en: {directorio}\n{plan}"
                }
            }
        }
    }

    # No debe lanzar excepción
    result = agente_codificador(state)
    assert result is not None


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_agente_codificador_con_errores_con_llaves_no_lanza(
    mock_middleware, mock_get_file, mock_get_llm
):
    """
    Verifica que el agente codificador no lance excepción cuando
    errores_terminal contiene tracebacks con llaves literales.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    mock_middleware.return_value = [HumanMessage(content="mensaje")]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "corregido"},
        "id": "call_2"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", tool_calls=[tool_call]
    )

    state = {
        "messages": [HumanMessage(content="haz algo")],
        "directorio_proyecto": "./",
        "plan_de_accion": {"explicacion_arquitectura": "test", "pasos": []},
        "codigo_escrito": "",
        "errores_terminal": "Traceback: KeyError: 'str' en Dict[str, Any] en {archivo}",
        "loop_counter": 0,
        "revision_count": 1,
    }

    result = agente_codificador(state)
    assert result is not None