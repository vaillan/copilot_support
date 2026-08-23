import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from app.main import crear_grafo

@pytest.fixture
def mock_llm():
    with patch('app.agents.agente_planificador.get_planner_llm') as mock_plan, \
         patch('app.agents.agente_codificador.get_coder_llm') as mock_cod, \
         patch('app.agents.agente_revisor.get_reviewer_llm') as mock_rev:
        yield mock_plan, mock_cod, mock_rev

@pytest.fixture
def mock_file_system():
    with patch('app.agents.agente_planificador.fileSystem.get_file_content', return_value="prompt planificador"), \
         patch('app.agents.agente_codificador.fileSystem.get_file_content', return_value="prompt codificador"), \
         patch('app.agents.agente_revisor.fileSystem.get_file_content', return_value="prompt revisor"):
        yield

def test_flujo_completo_exito(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
    )
    
    mock_llm_cod = MagicMock()
    mock_cod.return_value = mock_llm_cod
    mock_llm_cod.bind_tools.return_value.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "test.py", "text": "print(1)"}, "id": "w1"}]),
        AIMessage(content="", tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "test"}, "id": "2"}])
    ]
    
    mock_llm_rev = MagicMock()
    mock_rev.return_value = mock_llm_rev
    mock_llm_rev.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "finalizar_revision", "args": {"aprobado": True}, "id": "3"}]
    )
    
    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "1"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    graph.invoke(state, config)
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_codificador',)
    
    graph.invoke(None, config) # write_file
    graph.invoke(None, config) # CodigoCompletado
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_revisor',)
    
    graph.invoke(None, config)
    current_state = graph.get_state(config)
    assert len(current_state.next) == 0

def test_flujo_con_errores_y_correccion(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="", 
        tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
    )
    
    mock_llm_cod = MagicMock()
    mock_cod.return_value = mock_llm_cod
    mock_llm_cod.bind_tools.return_value.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "test.py", "text": "print(1)"}, "id": "w1"}]),
        AIMessage(content="", tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "test"}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "test.py", "text": "print(2)"}, "id": "w2"}]),
        AIMessage(content="", tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "corregido"}, "id": "4"}])
    ]
    
    mock_llm_rev = MagicMock()
    mock_rev.return_value = mock_llm_rev
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
    
    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "2"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    graph.invoke(state, config)
    assert graph.get_state(config).next == ('agente_codificador',)
    
    graph.invoke(None, config) # write_file
    graph.invoke(None, config) # CodigoCompletado
    assert graph.get_state(config).next == ('agente_revisor',)
    
    graph.invoke(None, config)
    assert graph.get_state(config).next == ('agente_codificador',)
    
    assert graph.get_state(config).values["errores_terminal"] == "Falla test"
    
    graph.invoke(None, config) # write_file correction
    graph.invoke(None, config) # CodigoCompletado correction
    assert graph.get_state(config).next == ('agente_revisor',)
    
    graph.invoke(None, config)
    assert len(graph.get_state(config).next) == 0

def test_flujo_analisis_puro_no_genera_codigo(mock_llm, mock_file_system):
    """
    Una instrucción de solo reporte/arquitectura/análisis NO debe invocar al
    agente codificador: el grafo debe terminar en END con 'analisis_final'.
    """
    mock_plan, mock_cod, mock_rev = mock_llm

    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    # En el camino de análisis puro se llama a llm.bind_tools().invoke() (P3:
    # el LLM dispone de herramientas de lectura para fundamentar el reporte).
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="Reporte de arquitectura detallado del módulo de pagos..."
    )

    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "analisis-1"}}

    state = {
        "messages": [HumanMessage(content="genera un reporte del estado del proyecto")],
        "instruccion_usuario": "genera un reporte del estado del proyecto",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }

    graph.invoke(state, config)
    current_state = graph.get_state(config)

    # El grafo debe terminar (END) sin pasar por agente_codificador
    assert len(current_state.next) == 0
    assert current_state.values.get("analisis_final") is not None
    assert "Reporte de arquitectura" in current_state.values["analisis_final"]
    # El codificador NO debe haber sido invocado
    mock_cod.assert_not_called()


def test_flujo_arquitectura_pura_no_genera_codigo(mock_llm, mock_file_system):
    """
    Una instrucción de 'genera una arquitectura' (sin implementación) NO debe
    invocar al agente codificador.
    """
    mock_plan, mock_cod, mock_rev = mock_llm

    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="Arquitectura propuesta: microservicios con API Gateway..."
    )

    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "arquitectura-1"}}

    state = {
        "messages": [HumanMessage(content="genera una arquitectura de microservicios")],
        "instruccion_usuario": "genera una arquitectura de microservicios",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }

    graph.invoke(state, config)
    current_state = graph.get_state(config)

    assert len(current_state.next) == 0
    assert current_state.values.get("analisis_final") is not None
    assert "Arquitectura propuesta" in current_state.values["analisis_final"]
    mock_cod.assert_not_called()


def test_flujo_sin_herramientas_evita_bucle(mock_llm, mock_file_system):
    mock_plan, mock_cod, mock_rev = mock_llm
    
    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    
    mock_llm_plan.bind_tools.return_value.invoke.side_effect = [
        AIMessage(content="Hola, soy el planificador"),
        AIMessage(
            content="", 
            tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "test", "pasos": []}, "id": "1"}]
        )
    ]
    
    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "3"}}
    
    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }
    
    graph.invoke(state, config)
    
    current_state = graph.get_state(config)
    assert current_state.next == ('agente_codificador',)
    
    messages = current_state.values["messages"]
    assert len(messages) == 5
    assert isinstance(messages[2], HumanMessage)
    assert "Debes llamar a una herramienta" in messages[2].content


@patch("app.agents.agente_planificador._es_peticion_analisis", side_effect=[False, True])
def test_texto_plano_analisis_no_deriva_a_codificador(mock_es_analisis, mock_llm, mock_file_system):
    """
    Cuando el planificador responde con texto plano (sin tool_calls) y la
    instrucción es de análisis puro, el grafo debe terminar en END con
    'analisis_final' y NO debe invocar al agente codificador.
    (Verifica la eliminación del fallback peligroso que fabricaba un plan
    artificial hacia 'main.py'.)
    """
    mock_plan, mock_cod, mock_rev = mock_llm

    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    # El planificador responde con texto plano (reporte) sin tool_calls.
    # side_effect=[False, True]: la 1ª llamada a _es_peticion_analisis (inicio)
    # devuelve False para forzar el camino normal (bind_tools); la 2ª (fallback)
    # devuelve True para que el texto plano se trate como análisis puro.
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="Reporte detallado del estado del proyecto: ..."
    )

    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "texto-plano-analisis"}}

    state = {
        "messages": [HumanMessage(content="genera un reporte del estado del proyecto")],
        "instruccion_usuario": "genera un reporte del estado del proyecto",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }

    graph.invoke(state, config)
    current_state = graph.get_state(config)

    # Debe terminar en END sin pasar por agente_codificador
    assert len(current_state.next) == 0
    assert current_state.values.get("analisis_final") is not None
    assert "Reporte detallado" in current_state.values["analisis_final"]
    mock_cod.assert_not_called()


def test_texto_plano_creacion_no_deriva_a_codificador(mock_llm, mock_file_system):
    """
    Cuando el planificador responde con texto plano (sin tool_calls) y la
    instrucción SÍ es de creación de código, NO debe fabricar un plan artificial
    hacia 'main.py': debe reintentar pidiendo que use 'entregar_plan_de_accion'
    y continuar con el plan real del LLM.
    """
    mock_plan, mock_cod, mock_rev = mock_llm

    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    # 1ª respuesta: texto plano sin tool_calls (instrucción de creación).
    # 2ª respuesta: plan real vía entregar_plan_de_accion.
    mock_llm_plan.bind_tools.return_value.invoke.side_effect = [
        AIMessage(content="Voy a analizar el requerimiento..."),
        AIMessage(
            content="",
            tool_calls=[{"name": "entregar_plan_de_accion", "args": {"explicacion_arquitectura": "Plan real", "pasos": []}, "id": "1"}]
        )
    ]

    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "texto-plano-creacion"}}

    state = {
        "messages": [HumanMessage(content="implementa un módulo de pagos")],
        "instruccion_usuario": "implementa un módulo de pagos",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }

    graph.invoke(state, config)
    current_state = graph.get_state(config)

    # Debe pausar en agente_codificador (flujo normal), NO fabricar plan con texto plano
    assert current_state.next == ('agente_codificador',)
    plan = current_state.values.get("plan_de_accion", {})
    # El plan debe ser el real del LLM, no el artificial con "main.py"
    assert plan.get("explicacion_arquitectura") == "Plan real"
    # El historial debe contener el mensaje de reintento (no se fabricó plan)
    messages = current_state.values["messages"]
    assert any("Debes llamar a una herramienta" in str(m.content) for m in messages if isinstance(m, HumanMessage))
    mock_cod.assert_not_called()


def test_modo_solo_analisis_fuerza_analisis(mock_llm, mock_file_system):
    """
    Con solo_analisis=True, incluso una instrucción de creación de código debe
    tratarse como análisis puro: el grafo termina en END con 'analisis_final'
    sin invocar al codificador.
    """
    mock_plan, mock_cod, mock_rev = mock_llm

    mock_llm_plan = MagicMock()
    mock_plan.return_value = mock_llm_plan
    # En el camino de análisis puro se llama a llm.bind_tools().invoke() (P3)
    mock_llm_plan.bind_tools.return_value.invoke.return_value = AIMessage(
        content="Arquitectura propuesta para el módulo de pagos..."
    )

    graph = crear_grafo(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "solo-analisis-1"}}

    state = {
        "messages": [HumanMessage(content="implementa un módulo de pagos")],
        "instruccion_usuario": "implementa un módulo de pagos",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": "",
        "solo_analisis": True
    }

    graph.invoke(state, config)
    current_state = graph.get_state(config)

    assert len(current_state.next) == 0
    assert current_state.values.get("analisis_final") is not None
    assert "Arquitectura propuesta" in current_state.values["analisis_final"]
    mock_cod.assert_not_called()
