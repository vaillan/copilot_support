import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompt_values import ChatPromptValue
from app.agents.agente_codificador import agente_codificador

_RESULTADO_SIN_DISPARAR = {
    "disparar": False,
    "archivos_modificados": [],
    "razon": "test",
    "hashes_actualizados": {},
    "last_ts": 0.0,
}


@pytest.fixture(autouse=True)
def _sin_regeneracion_tests():
    """Neutraliza el hook de regeneración de tests en las pruebas de enrutamiento.

    El comportamiento del hook se valida específicamente en
    tests/test_test_regenerator.py y en test_codificador_hook_regeneracion_dispara.
    """
    with patch('app.agents.agente_codificador.evaluar_regeneracion_tests',
               return_value=dict(_RESULTADO_SIN_DISPARAR)):
        yield


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


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_llama_write_file_cuando_se_ordena_modificar(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    Cuando el LLM emite una tool_call de write_file (se le ordenó modificar código),
    el nodo debe redirigir a nodo_herramientas_codificador para que la escritura
    se ejecute físicamente en disco.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    tool_call_write = {
        "name": "write_file",
        "args": {"path": "app/main.py", "content": "print('hola')"},
        "id": "call_write_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content="",
        tool_calls=[tool_call_write]
    )

    result = agente_codificador(mock_state)

    # El flujo debe ejecutar físicamente la escritura en el nodo de herramientas
    assert result.goto == "nodo_herramientas_codificador"
    # El AIMessage con la tool_call debe añadirse al historial
    assert len(result.update["messages"]) == 1
    assert result.update["messages"][0].tool_calls[0]["name"] == "write_file"
    # El loop_counter se incrementa
    assert result.update["loop_counter"] == 1


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_detecta_edit_file_como_modificacion(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    La validación debe reconocer edit_file como herramienta de modificación: si el
    historial contiene una llamada a edit_file y luego el LLM llama a CodigoCompletado,
    el nodo debe avanzar a agente_revisor.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    # El historial contiene una llamada a edit_file (modificación puntual de archivo existente)
    tool_call_edit = {
        "name": "edit_file",
        "args": {"path": "app/main.py", "old_text": "print('hola')", "new_text": "print('adiós')"},
        "id": "call_edit_1"
    }
    state_con_historial = dict(mock_state)
    state_con_historial["messages"] = [
        AIMessage(content="", tool_calls=[tool_call_edit]),
        HumanMessage(content="contexto")
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios aplicados"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(state_con_historial)

    # Debe avanzar a revisión porque edit_file es una herramienta de modificación
    assert result.goto == "agente_revisor"
    assert result.update["codigo_escrito"] == "cambios aplicados"


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
@patch('app.agents.agente_codificador.aplicar_resumen_middleware')
def test_codificador_detecta_confirmacion_exitosa_en_toolmessage(mock_aplicar_middleware, mock_get_file, mock_get_llm, mock_state):
    """
    La validación debe detectar confirmaciones de éxito en ToolMessages del historial:
    si write_file fue invocada y devolvió 'escrito exitosamente', el nodo debe avanzar
    a agente_revisor al llamar a CodigoCompletado.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt system prompt"
    mock_aplicar_middleware.return_value = [HumanMessage(content="contexto")]

    # Historial: write_file invocada + ToolMessage con confirmación de éxito en disco
    tool_call_write = {
        "name": "write_file",
        "args": {"path": "app/main.py", "content": "print('hola')"},
        "id": "call_write_1"
    }
    state_con_historial = dict(mock_state)
    state_con_historial["messages"] = [
        AIMessage(content="", tool_calls=[tool_call_write]),
        ToolMessage(
            tool_call_id="call_write_1",
            content="Archivo 'app/main.py' escrito exitosamente en 'C:\\proyecto\\app\\main.py'."
        ),
        HumanMessage(content="contexto")
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios aplicados"},
        "id": "call_cod_comp"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])

    result = agente_codificador(state_con_historial)

    # Debe avanzar a revisión porque el ToolMessage confirma la escritura exitosa en disco
    assert result.goto == "agente_revisor"
    assert result.update["codigo_escrito"] == "cambios aplicados"


def test_codificador_hook_regeneracion_dispara(mock_state):
    """Integración del hook: si el evaluador dispara, el codificador vuelve a su bucle
    con un HumanMessage de regeneración y el contador de regeneraciones se incrementa."""
    with patch('app.agents.agente_codificador.get_coder_llm') as mock_get_llm, \
         patch('app.agents.agente_codificador.fileSystem.get_file_content', return_value="prompt"), \
         patch('app.agents.agente_codificador.aplicar_resumen_middleware', return_value=[HumanMessage(content="ctx")]), \
         patch('app.agents.agente_codificador.evaluar_regeneracion_tests') as mock_eval:
        mock_eval.return_value = {
            "disparar": True,
            "archivos_modificados": ["app/main.py"],
            "razon": "ok",
            "hashes_actualizados": {"app/main.py": "abc123"},
            "last_ts": 123.0,
        }
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(
            content="",
            tool_calls=[{"name": "CodigoCompletado", "args": {"resumen_cambios": "hecho"}, "id": "cc"}]
        )
        estado = dict(mock_state)
        estado["messages"] = [
            AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "app/main.py"}, "id": "w"}])
        ]

        result = agente_codificador(estado)

        assert result.goto == "agente_codificador"
        contenidos = [str(m.content) for m in result.update["messages"]]
        assert any("Acción requerida" in c and "app/main.py" in c for c in contenidos)
        assert result.update["test_regeneration_count"] == 1
        assert result.update["test_regeneration_hashes"] == {"app/main.py": "abc123"}