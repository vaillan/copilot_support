import pytest
from unittest.mock import patch, MagicMock
from app.agents.agente_planificador import nodo_herramientas_planificador
from app.agents.agente_codificador import nodo_herramientas_codificador
from app.agents.agente_revisor import nodo_herramientas_revisor

@pytest.fixture
def mock_state():
    return {
        "messages": [],
        "directorio_proyecto": "./",
        "plan_de_accion": None,
        "codigo_escrito": "",
        "errores_terminal": ""
    }

@patch('app.agents.agente_planificador.ToolNode')
def test_nodo_herramientas_planificador(mock_tool_node, mock_state):
    """
    Prueba que el nodo de herramientas del planificador inicializa ToolNode
    y llama a su método invoke con el estado y configuración correctos.
    """
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {"messages": ["resultado_planificador"]}
    
    config = {"configurable": {"thread_id": "1"}}
    result = nodo_herramientas_planificador(mock_state, config)
    
    # Verificar que ToolNode fue instanciado
    mock_tool_node.assert_called_once()
    
    # Verificar que se llamó a invoke con los parámetros correctos
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)
    
    # Verificar el resultado
    assert result == {"messages": ["resultado_planificador"]}

@patch('app.agents.agente_codificador.ToolNode')
def test_nodo_herramientas_codificador(mock_tool_node, mock_state):
    """
    Prueba que el nodo de herramientas del codificador inicializa ToolNode
    y llama a su método invoke con el estado y configuración correctos.
    """
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {"messages": ["resultado_codificador"]}
    
    config = {"configurable": {"thread_id": "1"}}
    result = nodo_herramientas_codificador(mock_state, config)
    
    # Verificar que ToolNode fue instanciado
    mock_tool_node.assert_called_once()
    
    # Verificar que se llamó a invoke con los parámetros correctos
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)
    
    # Verificar el resultado
    assert result == {"messages": ["resultado_codificador"]}

@patch('app.agents.agente_revisor.ToolNode')
def test_nodo_herramientas_revisor(mock_tool_node, mock_state):
    """
    Prueba que el nodo de herramientas del revisor inicializa ToolNode
    excluyendo la herramienta 'finalizar_revision' y llama a su método invoke.
    """
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {"messages": ["resultado_revisor"]}
    
    config = {"configurable": {"thread_id": "1"}}
    result = nodo_herramientas_revisor(mock_state, config)
    
    # Verificar que ToolNode fue instanciado
    mock_tool_node.assert_called_once()
    
    # Verificar que la herramienta 'finalizar_revision' fue excluida
    herramientas_pasadas = mock_tool_node.call_args[0][0]
    nombres_herramientas = [t.name for t in herramientas_pasadas]
    assert "finalizar_revision" not in nombres_herramientas
    
    # Verificar que se llamó a invoke con los parámetros correctos
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)
    
    # Verificar el resultado
    assert result == {"messages": ["resultado_revisor"]}
