import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langgraph.types import Command
from langgraph.graph import END
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
        "errores_terminal": "",
        "loop_counter": 0,
        "revision_count": 0
    }

@patch('app.agents.agente_planificador.get_planner_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_agente_planificador_tool_call(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "entregar_plan_de_accion",
        "args": {"explicacion_arquitectura": "test plan", "pasos": []},
        "id": "call_1"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_planificador(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == "agente_codificador"
    update = result.update or {}
    assert "plan_de_accion" in update
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)
    assert messages[1].tool_call_id == "call_1"

@patch('app.agents.agente_planificador.get_planner_llm')
@patch('app.agents.agente_planificador.fileSystem.get_file_content')
def test_agente_planificador_no_tool_call(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="Hola")
    
    result = agente_planificador(mock_state)
    
    assert result.goto == "agente_planificador"
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], HumanMessage)
    assert "Debes llamar a una herramienta" in messages[1].content

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_completion(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mock_state["messages"] = [
        HumanMessage(content="haz algo"),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "a.py", "text": "code"}, "id": "w1"}])
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "cambios hechos"},
        "id": "call_2"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_codificador(mock_state)
    
    assert result.goto == "agente_revisor"
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_approval(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "finalizar_revision",
        "args": {"aprobado": True},
        "id": "call_3"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_revisor(mock_state)
    
    assert result.goto == END
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

def test_agente_revisor_plan_sin_tests(mock_state):
    mock_state["plan_de_accion"] = {
        "pasos": [
            {"archivo": "README.md", "tarea": "Actualizar doc", "requiere_test": False}
        ]
    }
    result = agente_revisor(mock_state)
    assert result.goto == END
    update = result.update or {}
    assert "Aprobado automáticamente" in update.get("errores_terminal", "")

def test_agente_revisor_max_loop_limit(mock_state):
    mock_state["loop_counter"] = 6
    result = agente_revisor(mock_state)
    assert result.goto == END
    update = result.update or {}
    assert "Verificación completada" in update.get("errores_terminal", "")

@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_texto_aprobado(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="El código es correcto y paso las pruebas sin errores.")
    
    result = agente_revisor(mock_state)
    assert result.goto == END
    update = result.update or {}
    assert "Código aprobado" in update.get("errores_terminal", "")

@patch('app.agents.agente_planificador.get_planner_llm')
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
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)

@patch('app.agents.agente_codificador.get_coder_llm')
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
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)

@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_con_errores(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    mock_state["errores_terminal"] = "Error de sintaxis en linea 10"
    mock_state["messages"] = [
        HumanMessage(content="haz algo"),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "a.py", "text": "code"}, "id": "w1"}])
    ]

    tool_call = {
        "name": "CodigoCompletado",
        "args": {"resumen_cambios": "corregido"},
        "id": "call_corr"
    }
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_codificador(mock_state)
    
    call_args = mock_llm.bind_tools.return_value.invoke.call_args[0][0]
    system_message = call_args.messages[0].content
    assert "Error de sintaxis en linea 10" in system_message
    assert result.goto == "agente_revisor"

@patch('app.agents.agente_revisor.get_reviewer_llm')
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
    update = result.update or {}
    assert update["errores_terminal"] == "Falla test"
    messages = update["messages"]
    assert len(messages) == 2
    assert isinstance(messages[1], ToolMessage)

@patch('app.agents.agente_revisor.get_reviewer_llm')
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
    update = result.update or {}
    messages = update["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)

@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_comando_duplicado_evita_bucle(mock_get_file, mock_get_llm, mock_state):
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"
    
    tool_call = {
        "name": "terminal",
        "args": {"commands": ["pytest"]},
        "id": "call_term"
    }
    prev_ai_message = AIMessage(content="", tool_calls=[tool_call])
    mock_state["messages"] = [HumanMessage(content="test"), prev_ai_message]
    
    mock_llm.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
    
    result = agente_revisor(mock_state)
    
    assert isinstance(result, Command)
    assert result.goto == END
    update = result.update or {}
    assert "detección de comandos redundantes" in update.get("errores_terminal", "")

def test_herramienta_terminal_aislada():
    from app.utils.terminal_tool import terminal
    res = terminal.invoke({"commands": "echo hola"})
    assert "$ echo hola" in res
    assert "hola" in res


def test_get_tools_agente_codificador():
    from app.agents.agente_codificador import _get_tools
    tools = _get_tools("./")
    tool_names = [t.name for t in tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "edit_file" in tool_names
    assert "file_delete" in tool_names
    assert "copy_file" in tool_names
    assert "move_file" in tool_names
    assert "list_directory" in tool_names


indice_test = {
    "arbol": {},
    "resumenes": {
        "app/utils/files.py": {"resumen": "RESUMEN_FILES"},
        "README.md": {"resumen": "RESUMEN_README"},
    },
}


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_prompt_filtrado(mock_get_file, mock_get_llm, mock_state):
    """
    El codificador inyecta en el prompt solo los resúmenes de los archivos
    referenciados en el plan de acción.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_state["project_index"] = indice_test
    mock_state["plan_de_accion"] = {
        "pasos": [{"archivo": "app/utils/files.py", "tarea": "cambiar la tool", "requiere_test": True}]
    }

    tool_call = {"name": "write_file", "args": {"file_path": "a.py", "text": "x"}, "id": "w1"}
    capturado = {}

    def _capturar(prompt, *args, **kwargs):
        capturado["prompt"] = str(prompt)
        return AIMessage(content="", tool_calls=[tool_call])

    mock_llm.bind_tools.return_value.invoke.side_effect = _capturar

    result = agente_codificador(mock_state)

    prompt = capturado["prompt"]
    assert "ÍNDICE DEL PROYECTO" in prompt
    assert "RESUMEN_FILES" in prompt
    assert "RESUMEN_README" not in prompt
    assert result.goto == "nodo_herramientas_codificador"


@patch('app.agents.agente_codificador.get_coder_llm')
@patch('app.agents.agente_codificador.fileSystem.get_file_content')
def test_agente_codificador_prompt_fallback(mock_get_file, mock_get_llm, mock_state):
    """
    Sin coincidencias de archivos relevantes, el codificador inyecta
    el índice completo como fallback.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_state["project_index"] = indice_test
    mock_state["plan_de_accion"] = {
        "pasos": [{"archivo": "no_existe.py", "tarea": "x", "requiere_test": True}]
    }

    tool_call = {"name": "write_file", "args": {"file_path": "a.py", "text": "x"}, "id": "w2"}
    capturado = {}

    def _capturar(prompt, *args, **kwargs):
        capturado["prompt"] = str(prompt)
        return AIMessage(content="", tool_calls=[tool_call])

    mock_llm.bind_tools.return_value.invoke.side_effect = _capturar

    agente_codificador(mock_state)

    prompt = capturado["prompt"]
    assert "RESUMEN_README" in prompt
    assert "RESUMEN_FILES" in prompt


@patch('app.agents.agente_revisor.get_reviewer_llm')
@patch('app.agents.agente_revisor.fileSystem.get_file_content')
def test_agente_revisor_prompt_filtrado(mock_get_file, mock_get_llm, mock_state):
    """
    El revisor inyecta en el prompt solo los resúmenes de los archivos
    relevantes del plan de acción antes de emitir su veredicto.
    """
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_get_file.return_value = "system prompt"

    mock_state["project_index"] = indice_test
    mock_state["plan_de_accion"] = {
        "pasos": [{"archivo": "app/utils/files.py", "tarea": "cambiar la tool", "requiere_test": True}]
    }

    tool_call = {"name": "finalizar_revision", "args": {"aprobado": True}, "id": "r1"}
    capturado = {}

    def _capturar(prompt, *args, **kwargs):
        capturado["prompt"] = str(prompt)
        return AIMessage(content="", tool_calls=[tool_call])

    mock_llm.bind_tools.return_value.invoke.side_effect = _capturar

    result = agente_revisor(mock_state)

    prompt = capturado["prompt"]
    assert "RESUMEN_FILES" in prompt
    assert "RESUMEN_README" not in prompt
    assert result.goto == END