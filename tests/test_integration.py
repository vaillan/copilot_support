import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.main import crear_grafo

@pytest.fixture
def mock_llm():
    with patch('app.agents.agente_planificador.get_llm') as mock_plan, \
         patch('app.agents.agente_codificador.get_llm') as mock_cod, \
         patch('app.agents.agente_revisor.get_llm') as mock_rev:
        yield mock_plan, mock_cod, mock_rev

@pytest.fixture
def mock_file_system():
    with patch('app.agents.agente_planificador.fileSystem.get_file_content', return_value="prompt planificador"), \
         patch('app.agents.agente_codificador.fileSystem.get_file_content', return_value="prompt codificador"), \
         patch('app.agents.agente_revisor.fileSystem.get_file_content', return_value="prompt revisor"):
        yield

def test_flujo_completo_exito(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    # Setup mocks
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
    )
    
    mock_llm_cod = MagicMock()
    mock_cod.return_value = mock_llm_cod
    mock_llm_cod.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "test"}, "id": "2"}]
    )
    
    mock_llm_rev = MagicMock()
    mock_rev.return_value = mock_llm_rev
    mock_llm_rev.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "finalizar_revision", "args": {"aprobado": True}, "id": "3"}]
    )
    
    graph = crear_grafo()
    config = {"configurable": {"thread_id": "1"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    # Run to first interrupt (before agente_codificador)
    graph.invoke(state, config)
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_codificador',)
    
    # Resume to second interrupt (before agente_revisor)
    graph.invoke(None, config)
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_revisor',)
    
    # Resume to end
    graph.invoke(None, config)
    current_state = graph.get_state(config)
    assert len(current_state.next) == 0 # END

def test_flujo_con_errores_y_correccion(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    # Setup mocks
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
    )
    
    mock_llm_cod = MagicMock()
    mock_cod.return_value = mock_llm_cod
    mock_llm_cod.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "test"}, "id": "2"}]
    )
    
    mock_llm_rev = MagicMock()
    mock_rev.return_value = mock_llm_rev
    # First time rejects, second time approves
    mock_llm_rev.bind_tools.return_value.invoke.side_effect = [
        AIMessage(
            content="", 
            tool_calls=[{"name": "finalizar_revision", "args": {"aprobado": False, "reporte_errores": "Falla test"}, "id": "3"}]
        ),
        AIMessage(
            content="", 
            tool_calls=[{"name": "finalizar_revision", "args": {"aprobado": True}, "id": "4"}]
        )
    ]
    
    graph = crear_grafo()
    config = {"configurable": {"thread_id": "2"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    # Run to first interrupt (before agente_codificador)
    graph.invoke(state, config)
    assert graph.get_state(config).next == ('agente_codificador',)
    
    # Resume to second interrupt (before agente_revisor)
    graph.invoke(None, config)
    assert graph.get_state(config).next == ('agente_revisor',)
    
    # Resume, reviewer rejects, goes back to coder, interrupts before coder
    graph.invoke(None, config)
    assert graph.get_state(config).next == ('agente_codificador',)
    
    # Check that error is in state
    assert graph.get_state(config).values["errores_terminal"] == "Falla test"
    
    # Resume to reviewer
    graph.invoke(None, config)
    assert graph.get_state(config).next == ('agente_revisor',)
    
    # Resume to end
    graph.invoke(None, config)
    assert len(graph.get_state(config).next) == 0

def test_flujo_sin_herramientas_evita_bucle(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    
    # First call: no tools. Second call: entregar_plan_de_accion
    mock_llm_plan.bind_tools.return_value.invoke.side_effect = [
        AIMessage(content="Hola, soy el planificador"),
        AIMessage(
            content="", 
            tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
        )
    ]
    
    graph = crear_grafo()
    config = {"configurable": {"thread_id": "3"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    # Run graph. It should run planner twice, then interrupt before coder.
    graph.invoke(state, config)
    
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_codificador',)
    
    # Check messages to ensure HumanMessage was added
    messages = current_state.values["messages"]
    # Initial HumanMessage + AIMessage (no tools) + HumanMessage (warning) + AIMessage (entregar_plan_de_accion) + ToolMessage
    assert len(messages) == 5
    assert isinstance(messages[2], HumanMessage)
    assert "Debes llamar a una herramienta" in messages[2].content
