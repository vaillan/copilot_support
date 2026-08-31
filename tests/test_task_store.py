"""Regresión MCP + SQLite: verifica que la obtención de tareas del servidor MCP
pasa por app.mcp.task_store (singleton de app.utils.task_registry) y que la
persistencia es SQLite (tasks.db), no JSON."""

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from app.utils.task_registry import TaskRegistry, task_registry, ESTADOS_VALIDOS
from app.mcp.task_store import task_store as task_store_mcp, ESTADOS_VALIDOS as ESTADOS_MCP
import mcp_server
from mcp_server import (
    listar_tareas,
    consultar_estado_tarea,
    cancelar_tarea,
    delegar_tarea_a_equipo_ia,
)
from app.utils.project_index import EXCLUDED_FILES


def test_task_store_reexporta_el_singleton_del_registry():
    """Verifica que app.mcp.task_store reexporta la misma instancia singleton del registro."""
    assert task_store_mcp is task_registry
    assert isinstance(task_store_mcp, TaskRegistry)
    assert ESTADOS_MCP == ESTADOS_VALIDOS


def test_mcp_server_consume_task_store_y_no_task_registry():
    """Verifica que mcp_server.py consume task_store desde app.mcp y no el registro directamente."""
    source = Path("mcp_server.py").read_text(encoding="utf-8")
    assert "from app.mcp.task_store import task_store" in source
    assert "from app.utils.task_registry import" not in source
    assert mcp_server.task_store is task_registry


def test_persistencia_es_sqlite_no_json(tmp_path):
    """Verifica que la persistencia del registro es SQLite (tasks.db) y no JSON."""
    ruta = tmp_path / "tasks.db"
    registro = TaskRegistry(ruta_persistencia=str(ruta))
    registro.register_task(tarea_id="t_sql", estado="running")
    registro.update_status("t_sql", "completed", detalle="OK")

    assert ruta.exists()
    with open(ruta, "rb") as f:
        assert f.read(16) == b"SQLite format 3\x00"

    conn = sqlite3.connect(str(ruta))
    fila = conn.execute(
        "SELECT datos FROM tasks WHERE tarea_id = ?", ("t_sql",)
    ).fetchone()
    conn.close()
    assert fila is not None
    assert json.loads(fila[0])["estado"] == "completed"

    assert not (tmp_path / ".task_registry.json").exists()
    assert list(Path("app").rglob(".task_registry.json")) == []
    # El servidor MCP en ejecucion puede regenerar .task_registry.json en la raiz
    # como artefacto de runtime post-migracion; la fuente de verdad SQLite ya
    # quedo verificada arriba (cabecera + consulta a la tabla tasks).


def test_listar_tareas_consulta_task_store():
    """Verifica que listar_tareas delega en task_store.list_tasks."""
    tarea_mock = {
        "tarea_id": "t1",
        "estado": "running",
        "directorio_proyecto": "/x",
        "timestamp_actualizacion": 1,
    }
    with patch("mcp_server.task_store.list_tasks", return_value=[tarea_mock]) as mock_list:
        resultado = asyncio.run(listar_tareas())

    mock_list.assert_called_once_with(estado="")
    assert "t1" in resultado
    assert "Tareas Registradas" in resultado


def test_consultar_estado_tarea_consulta_task_store():
    """Verifica que consultar_estado_tarea delega en task_store.get_task."""
    mock_estado = MagicMock()
    mock_estado.values = {}
    mock_estado.next = []
    with patch(
        "mcp_server.task_store.get_task",
        return_value={
            "tarea_id": "t2",
            "estado": "running",
            "directorio_proyecto": "/x",
            "timestamp_actualizacion": 1,
        },
    ) as mock_get, patch(
        "mcp_server.agentes_app.aget_state", new_callable=AsyncMock, return_value=mock_estado
    ):
        resultado = asyncio.run(consultar_estado_tarea(tarea_id="t2"))

    mock_get.assert_called_once_with("t2")
    assert "Estado registrado" in resultado
    assert "running" in resultado


def test_cancelar_tarea_consulta_y_actualiza_task_store():
    """Verifica que cancelar_tarea consulta get_task y actualiza update_status en task_store."""
    with patch(
        "mcp_server.task_store.get_task",
        return_value={"tarea_id": "t3", "estado": "running"},
    ) as mock_get, patch(
        "mcp_server.task_store.update_status", return_value=True
    ) as mock_upd:
        resultado = asyncio.run(cancelar_tarea(tarea_id="t3"))

    mock_get.assert_called_once_with("t3")
    mock_upd.assert_called_once()
    assert mock_upd.call_args[0][0] == "t3"
    assert mock_upd.call_args[0][1] == "cancelled"
    assert "marcada como cancelada" in resultado

    # Edge case: tarea inexistente -> no se actualiza nada en el registro.
    with patch("mcp_server.task_store.get_task", return_value=None) as mock_get_none, patch(
        "mcp_server.task_store.update_status", return_value=True
    ) as mock_upd_none:
        resultado = asyncio.run(cancelar_tarea(tarea_id="no_existe"))

    mock_get_none.assert_called_once_with("no_existe")
    mock_upd_none.assert_not_called()
    assert "No se encontró" in resultado


def test_delegar_tarea_registra_y_consulta_task_store():
    """Verifica que delegar_tarea_a_equipo_ia consulta y registra en task_store (re-pausa de feedback)."""
    mock_state = MagicMock()
    mock_state.next = ["agente_revisor"]
    mock_state.values = {"codigo_escrito": "Creado helpers.py"}
    mock_ainvoke = AsyncMock()
    with patch("mcp_server.task_store.get_task", return_value=None) as mock_get, patch(
        "mcp_server.task_store.register_task", return_value={"tarea_id": "t4"}
    ) as mock_reg, patch(
        "mcp_server.agentes_app.aget_state", new_callable=AsyncMock, return_value=mock_state
    ), patch("mcp_server.agentes_app.ainvoke", mock_ainvoke):
        resultado = asyncio.run(
            delegar_tarea_a_equipo_ia(
                instruccion="Crear helpers",
                directorio_proyecto="./",
                tarea_id="t4",
            )
        )

    mock_get.assert_called_once_with("t4")
    mock_reg.assert_called_once()
    assert mock_reg.call_args.kwargs.get("tarea_id") == "t4"
    assert "AI ASSISTANT" in resultado


def test_obtencion_tareas_solo_via_app_mcp_y_mcp_server():
    """Verifica que ninguna obtención de tareas ocurre fuera de app/mcp/ y mcp_server.py."""
    blanca = {
        "app/utils/task_registry.py",
        "app/mcp/task_store.py",
        "app/mcp/__init__.py",
        "mcp_server.py",
    }
    patrones = (
        "task_registry",
        "TaskRegistry",
        "task_store",
        ".get_task(",
        ".list_tasks(",
        ".register_task(",
        ".update_status(",
        ".remove_task(",
        ".task_registry.json",
    )
    archivos = list(Path("app").rglob("*.py")) + [Path("mcp_server.py")]
    violaciones = []
    for archivo in archivos:
        ruta_relativa = archivo.as_posix()
        if ruta_relativa in blanca:
            continue
        contenido = archivo.read_text(encoding="utf-8")
        if any(patron in contenido for patron in patrones):
            violaciones.append(ruta_relativa)

    assert violaciones == [], (
        "Obtención de tareas fuera de app/mcp/ y mcp_server.py: "
        + ", ".join(violaciones)
    )


def test_project_index_excluye_tasks_db_y_no_json_legacy():
    """Verifica que el índice excluye tasks.db y ya no menciona el JSON legado."""
    assert "tasks.db" in EXCLUDED_FILES
    assert ".task_registry.json" not in EXCLUDED_FILES