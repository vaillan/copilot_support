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
