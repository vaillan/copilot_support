import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langgraph.types import Command
from app.agents.agente_planificador import agente_planificador
from app.agents.agente_codificador import agente_codificador
from app.agents.agente_revisor import agente_revisor

@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="test")],
        "directorio_proyecto": "./",
        "plan_de_accion": None,
        "codigo_escrito": "",
        "errores_terminal": ""
    }

@patch('app.agents.agente_planificador.get_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_agente_planificador_tool_call(mock_get_file, mock_get_llm, mock_state):
    # Setup
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    # Simular llamada a herramienta PlanDeAccion
    tool_call = {
        "name": "PlanDeAccion",
        "args": {"explicacion_arquitectura": "test plan", "pasos": []},
        "id": "call_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    # Execute
    result = agente_planificador(mock_state)
    
    # Assert
    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    assert "plan_de_accion" in result.update
    # Verificar que se añadieron ToolMessages
    messages = result.update["messages"]
    assert len(messages) == 2 # AIMessage + ToolMessage
    assert isinstance(messages[1], ToolMessage)
    assert messages[1].tool_call_id == "call_1"

@patch('app.agents.agente_planificador.get_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_agente_planificador_no_tool_call(mock_get_file, mock_get_llm, mock_state):
    # Setup
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    # Simular respuesta sin herramientas (debería provocar HumanMessage para evitar bucle)
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="Hola")
    
    # Execute
    result = agente_planificador(mock_state)
    
    # Assert
    assert result.goto == "agente_planificador"
    messages = result.update["messages"]
    assert len(messages) == 2 # AIMessage + HumanMessage
    assert isinstance(messages[1], HumanMessage)
    assert "Debes llamar a una herramienta" in messages[1].content

@patch('app.agents.agente_codificador.get_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_completion(mock_get_file, mock_get_llm, mock_state):
    # Setup
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios hechos"},
        "id": "call_2"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    # Execute
    result = agente_codificador(mock_state)
    
    # Assert
    assert result.goto == "agente_revisor"
    messages = result.update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

@patch('app.agents.agente_revisor.get_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_approval(mock_get_file, mock_get_llm, mock_state):
    # Setup
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": True},
        "id": "call_3"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    # Execute
    result = agente_revisor(mock_state)
    
    # Assert
    from langgraph.graph import END
    assert result.goto == END
    messages = result.update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

@patch('app.agents.agente_planificador.get_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_agente_planificador_investigacion(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "read_file",
        "args": {"file_path": "main.py"},
        "id": "call_read"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_planificador(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == "nodo_herramientas_planificador"
    messages = result.update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)

@patch('app.agents.agente_codificador.get_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_herramienta_archivo(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "write_file",
        "args": {"file_path": "main.py", "text": "print('hola')"},
        "id": "call_write"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_codificador(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == "nodo_herramientas_codificador"
    messages = result.update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)

@patch('app.agents.agente_codificador.get_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_con_errores(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mock_state["errores_terminal"] = "Error de sintaxis en linea 10"
    
    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "corregido"},
        "id": "call_corr"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_codificador(mock_state)
    
    # Verificar que el prompt enviado al LLM incluye el error
    call_args = mock_llm.bind_tools.return_value.invoke.call_args[0][0]
    # call_args es un ChatPromptValue, podemos inspeccionar sus mensajes
    system_message = call_args.messages[0].content
    assert "Error de sintaxis en linea 10" in system_message
    assert result.goto == "agente_revisor"

@patch('app.agents.agente_revisor.get_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_rechazo(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": False, "reporte_errores": "Falla test"},
        "id": "call_rej"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_revisor(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    assert result.update["errores_terminal"] == "Falla test"
    messages = result.update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

@patch('app.agents.agente_revisor.get_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_herramienta_terminal(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "terminal",
        "args": {"commands": ["pytest"]},
        "id": "call_term"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_revisor(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == "nodo_herramientas_revisor"
    messages = result.update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)
