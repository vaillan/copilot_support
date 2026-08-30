import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import ToolMessage
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
    
    mock_tool_node.assert_called_once()
    
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)
    
    assert result == {"messages": ["resultado_planificador"]}

@patch('app.utils.project_index.actualizar_indice_incremental')
@patch('app.agents.agente_codificador.ToolNode')
def test_nodo_herramientas_codificador(mock_tool_node, mock_actualizar_indice, mock_state):
    """
    Prueba que el nodo de herramientas del codificador inicializa ToolNode,
    ejecuta las herramientas y, tras ellas, refresca el índice del proyecto
    (actualizar_indice_incremental) persistiéndolo SOLO en la caché de disco.
    El índice ya NO viaja en el estado del grafo (evita inflar los checkpoints
    de SQLite), por lo que el resultado NO contiene la clave 'project_index'.
    """
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {
        "messages": [ToolMessage(content="escrito exitosamente", tool_call_id="1")]
    }

    indice_actualizado = {"version": 1, "arbol": {"archivos": ["app/main.py"]}}
    mock_actualizar_indice.return_value = indice_actualizado

    config = {"configurable": {"thread_id": "1"}}

    with patch('app.settings.settings.Settings') as mock_settings:
        mock_settings.return_value.PROJECT_INDEX_ENABLED = True
        result = nodo_herramientas_codificador(mock_state, config)

    mock_tool_node.assert_called_once()
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)

    mock_actualizar_indice.assert_called_once_with(
        mock_state["directorio_proyecto"],
        mock_state.get("project_index")
    )

    assert result["messages"] == [ToolMessage(content="escrito exitosamente", tool_call_id="1")]
    # El índice se persiste en disco, no en el estado del grafo.
    assert "project_index" not in result


@patch('app.utils.project_index.actualizar_indice_incremental')
@patch('app.agents.agente_codificador.ToolNode')
def test_nodo_herramientas_codificador_index_deshabilitado(mock_tool_node, mock_actualizar_indice, mock_state):
    """
    Caso de borde: con PROJECT_INDEX_ENABLED=False el nodo NO refresca el índice:
    el resultado no contiene la clave 'project_index' y no se llama a
    actualizar_indice_incremental.
    """
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {
        "messages": [ToolMessage(content="resultado_codificador", tool_call_id="1")]
    }

    config = {"configurable": {"thread_id": "1"}}

    with patch('app.settings.settings.Settings') as mock_settings:
        mock_settings.return_value.PROJECT_INDEX_ENABLED = False
        result = nodo_herramientas_codificador(mock_state, config)

    mock_actualizar_indice.assert_not_called()
    assert "project_index" not in result
    assert result == {"messages": [ToolMessage(content="resultado_codificador", tool_call_id="1")]}

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
    
    mock_tool_node.assert_called_once()
    
    herramientas_pasadas = mock_tool_node.call_args[0][0]
    nombres_herramientas = [t.name for t in herramientas_pasadas]
    assert "finalizar_revision" not in nombres_herramientas
    
    mock_instance.invoke.assert_called_once_with(mock_state, config=config)
    
    assert result == {"messages": ["resultado_revisor"]}


# ---------------------------------------------------------------------------
# Agnosticidad: tool terminal del revisor (shell por defecto del SO)
# ---------------------------------------------------------------------------
@patch('app.agents.agente_revisor.ToolNode')
def test_nodo_herramientas_revisor_incluye_terminal(mock_tool_node, mock_state):
    """El nodo del revisor expone la tool 'terminal' y excluye 'finalizar_revision'."""
    mock_instance = MagicMock()
    mock_tool_node.return_value = mock_instance
    mock_instance.invoke.return_value = {"messages": ["resultado_revisor"]}

    config = {"configurable": {"thread_id": "1"}}
    nodo_herramientas_revisor(mock_state, config)

    herramientas_pasadas = mock_tool_node.call_args[0][0]
    nombres_herramientas = [t.name for t in herramientas_pasadas]
    assert "terminal" in nombres_herramientas
    assert "finalizar_revision" not in nombres_herramientas


@patch('app.agents.agente_revisor.subprocess.run')
def test_terminal_ejecuta_agnostico_shell(mock_run, tmp_path):
    """La tool terminal ejecuta con shell=True (shell por defecto del SO) y cwd."""
    from app.agents.agente_revisor import terminal

    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    resultado = terminal.func(["echo hola"], cwd=str(tmp_path))

    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["shell"] is True
    assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)
    assert "ok" in resultado


@patch('app.agents.agente_revisor.subprocess.run')
def test_terminal_bloquea_sin_ejecutar(mock_run, tmp_path):
    """Un comando destructivo se bloquea sin invocar subprocess.run."""
    from app.agents.agente_revisor import terminal

    resultado = terminal.func(['rm -rf /'], cwd=str(tmp_path))

    mock_run.assert_not_called()
    assert "Comando bloqueado" in resultado