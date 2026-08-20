import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompt_values import ChatPromptValue
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
    mock_get_file.return_value = "system prompt system prompt"
    
    # Configurar el middleware simulado para que devuelva un subconjunto o mensajes resumidos
    mensajes_resumidos = [HumanMessage(content="Resumen del historial previo"), HumanMessage(content="último mensaje")]
    mock_aplicar_middleware.return_value = mensajes_resumidos

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios aplicados"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    # Verificar que aplicar_resumen_middleware fue llamado con los mensajes del estado y el llm
    mock_aplicar_middleware.assert_called_once()
    args, kwargs = mock_aplicar_middleware.call_args
    assert len(args[0]) == 15  # Recibió los 15 mensajes originales
    assert args[1] == mock_llm  # Recibió el llm

    # Verificar que el prompt invocado utilizó los mensajes resumidos devueltos por el middleware
    invoke_call_args = mock_llm.bind_tools.return_value.invoke.call_args
    assert invoke_call_args is not None
    prompt_value = invoke_call_args[0][0]
    
    # Comprobar que los mensajes pasados al prompt contienen el contenido resumido
    messages_in_prompt = prompt_value.messages if hasattr(prompt_value, "messages") else prompt_value.to_messages()
    contenido_mensajes = [m.content for m in messages_in_prompt]
    assert any("Resumen del historial previo" in c for c in contenido_mensajes)


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_nunca_avanza_a_revision_sin_escribir_archivos(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    Verifica que cuando el LLM responde texto sin tool_calls (incluso con loop_counter >= 2),
    el nodo SIEMPRE reintenta (goto agente_codificador) y NUNCA avanza a revisión sin haber
    escrito archivos en disco.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    # Respuesta de texto sin tool_calls, con loop_counter alto (el bug original avanzaba a revisión aquí)
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="Aquí está el código que debes escribir...",
        tool_calls=[]
    )

    state_con_loop_alto = dict(mock_state)
    state_con_loop_alto["loop_counter"] = 5

    result = agente_codificador(state_con_loop_alto)

    # NUNCA debe ir a agente_revisor sin haber escrito archivos
    assert result.goto == "agente_codificador"
    # Debe incrementar el loop_counter (reintento)
    assert result.update["loop_counter"] == 6
    # El mensaje debe indicar que debe llamar a una herramienta de escritura
    mensajes = result.update["messages"]
    assert any("herramienta de escritura" in m.content for m in mensajes if hasattr(m, "content"))


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_rechaza_codigocompletado_sin_escribir_archivos(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    Si el LLM llama a CodigoCompletado sin haber llamado a ninguna herramienta de
    modificación de archivos, el nodo debe rechazarlo y volver a agente_codificador.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(mock_state)

    # No debe avanzar a revisión sin haber escrito archivos
    assert result.goto == "agente_codificador"
    mensajes = result.update["messages"]
    assert any("No has modificado ni creado ningún archivo" in m.content for m in mensajes if hasattr(m, "content"))


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_detecta_herramientas_de_modificacion_para_avanzar(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    La validación debe detectar CUALQUIER herramienta de modificación (write_file, copy_file,
    move_file, file_delete), no solo write_file, para permitir avanzar a revisión.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    # El historial contiene una llamada a copy_file (herramienta de modificación)
    tool_call_historial = {
        "name": "copy_file",
        "args": {"source": "a.py", "destination": "b.py"},
        "id": "call_copy"
    }
    state_con_historial = dict(mock_state)
    state_con_historial["messages"] = [
        AIMessage(content="", tool_calls=[tool_call_historial]),
        HumanMessage(content="contexto")
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios aplicados"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(state_con_historial)

    # Debe avanzar a revisión porque sí hubo modificación de archivos (copy_file)
    assert result.goto == "agente_revisor"
    assert result.update["codigo_escrito"] == "cambios aplicados"
