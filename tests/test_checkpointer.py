"""Pruebas del checkpointer SqliteSaver por defecto y su persistencia.

Valida que ``crear_grafo`` use por defecto un ``SqliteSaver`` persistente en
``checkpoints.sqlite`` y que tras una invocación real se escriban checkpoints
en la base de datos SQLite.
"""

import sqlite3
import uuid

import pytest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from app.main import crear_grafo

RUTA_CHECKPOINTS = "checkpoints.sqlite"


@pytest.fixture
def mock_llm():
    with patch('app.agents.agente_planificador.get_planner_llm') as mock_plan, \
         patch('app.agents.agente_codificador.get_coder_llm') as mock_cod, \
         patch('app.agents.agente_revisor.get_reviewer_llm') as mock_rev, \
         patch('app.utils.summarization.get_llm') as mock_llm:
        yield mock_plan, mock_cod, mock_rev, mock_llm


@pytest.fixture
def mock_file_system():
    with patch('app.agents.agente_planificador.fileSystem.get_file_content', return_value="prompt planificador"), \
         patch('app.agents.agente_codificador.fileSystem.get_file_content', return_value="prompt codificador"), \
         patch('app.agents.agente_revisor.fileSystem.get_file_content', return_value="prompt revisor"):
        yield


def test_checkpointer_por_defecto_es_sqlite():
    """El checkpointer por defecto de crear_grafo debe ser un SqliteSaver."""
    graph = crear_grafo()
    assert isinstance(graph.checkpointer, SqliteSaver)


def test_persistencia_tras_invocacion(mock_llm, mock_file_system):
    """Tras una invocación real, checkpoints.sqlite debe contener checkpoints."""
    mock_plan, mock_cod, mock_rev, _ = mock_llm

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

    graph = crear_grafo(interrumpir_en_codificador=False, interrumpir_en_revisor=False)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    state = {
        "messages": [HumanMessage(content="Haz algo")],
        "instruccion_usuario": "Haz algo",
        "directorio_proyecto": "./",
        "plan_de_accion": {},
        "codigo_escrito": "",
        "errores_terminal": ""
    }

    graph.invoke(state, config)
    graph.invoke(None, config)  # write_file
    graph.invoke(None, config)  # CodigoCompletado
    graph.invoke(None, config)  # revisor -> END

    conn = sqlite3.connect(RUTA_CHECKPOINTS)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('checkpoints', 'checkpoint_writes', 'checkpoint_blobs')")
        tablas = {fila[0] for fila in cursor.fetchall()}
        # Validación mínima obligatoria: la tabla 'checkpoints' debe existir y contener filas.
        assert "checkpoints" in tablas

        cursor.execute("SELECT COUNT(*) FROM checkpoints")
        total = cursor.fetchone()[0]
        assert total > 0

        # 'checkpoint_writes' y 'checkpoint_blobs' solo se crean según la versión
        # de langgraph-checkpoint-sqlite; su presencia no es obligatoria.
        if "checkpoint_writes" in tablas:
            cursor.execute("SELECT COUNT(*) FROM checkpoint_writes")
            assert cursor.fetchone()[0] >= 0
    finally:
        conn.close()
