import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from app.agents.agente_codificador import agente_codificador

@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content=f"mensaje de prueba {i}") for i in range(15)],
        "directorio_proyecto": "./",
        "plan_de_accion": {
            "explicacion_arquitectura": "Test architecture",
            "pasos": [{"archivo": "app/main.py", "tarea": "Crear main", "requiere_test": True}]
        },
        "codigo_escrito": "",
        "errores_terminal": "",
        "loop_counter": 0,
        "revision_count": 0
    }

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_agente_codificador_aplica_middleware_resumen(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mensajes_resumidos = [HumanMessage(content="Resumen del historial previo"), HumanMessage(content="último mensaje")]
    mock_aplicar_middleware.return_value = mensajes_resumidos

    tool_call = {
        "name": "write_file",
        "args": {"path": "app/main.py", "content": "print('hello')"},
        "id": "call_write_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    mock_aplicar_middleware.assert_called_once()
    args, _ = mock_aplicar_middleware.call_args
    assert len(args[0]) == 15
    assert args[1] == mock_llm

    assert result.goto == "nodo_herramientas_codificador"

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_agente_codificador_codigo_completado_con_escritura_previa(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    mock_aplicar_middleware.side_effect = lambda msgs, llm: msgs

    # Historial que contiene una llamada a write_file previa
    mock_state["messages"] = [
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"path": "app/main.py", "content": "pass"}, "id": "call_w1"}]),
        ToolMessage(content="Archivo guardado", tool_call_id="call_w1")
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "Creado app/main.py"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    assert result.goto == "agente_revisor"
    assert result.update["codigo_escrito"] == "Creado app/main.py"
    assert result.update["errores_terminal"] == ""
    assert result.update["loop_counter"] == 0

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_agente_codificador_codigo_completado_sin_escritura_falla(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    mock_aplicar_middleware.side_effect = lambda msgs, llm: msgs

    # Estado sin escrituras de archivo previas
    mock_state["messages"] = [HumanMessage(content="Por favor implementa la función")]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "Terminado sin tocar archivos"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    # Debe rebotar hacia el agente_codificador advirtiendo que no escribió archivos
    assert result.goto == "agente_codificador"
    assert any("No hast modificado ni creado ningún archivo" in m.content for m in result.update["messages"] if isinstance(m, HumanMessage))

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_limite_maximo_iteraciones(mock_get_file, mock_get_llm, mock_state):
    mock_state["loop_counter"] = 15  # Al sumarse 1 llegará a 16 > 15

    result = agente_codificador(mock_state)

    assert result.goto == END
    assert any("límite máximo de iteraciones" in m.content for m in result.update["messages"])
