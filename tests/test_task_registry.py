"""
Pruebas unitarias para app/utils/task_registry.py.

Cubre: register_task, update_status, get_task, list_tasks, remove_task
y concurrencia con múltiples hilos.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.utils.task_registry import TaskRegistry, ESTADOS_VALIDOS


@pytest.fixture
def registro():
    """Fixture que devuelve un TaskRegistry limpio por prueba."""
    return TaskRegistry()


def test_register_task_crea_entrada_con_estado_running(registro):
    tarea = registro.register_task(
        tarea_id="task_001",
        directorio_proyecto="/proyecto",
        instruccion="Crear función",
        thread_id="thread_001",
    )
    assert tarea["tarea_id"] == "task_001"
    assert tarea["estado"] == "running"
    assert tarea["directorio_proyecto"] == "/proyecto"
    assert tarea["thread_id"] == "thread_001"
    assert tarea["timestamp_inicio"] > 0
    assert tarea["timestamp_actualizacion"] > 0


def test_register_task_estado_invalido_se_normaliza_a_running(registro):
    tarea = registro.register_task(tarea_id="task_002", estado="estado_inexistente")
    assert tarea["estado"] == "running"


def test_update_status_cambia_estado_y_timestamp(registro):
    registro.register_task(tarea_id="task_003")
    time.sleep(0.01)
    ok = registro.update_status("task_003", "paused_planning", detalle="Plan listo")
    assert ok is True
    tarea = registro.get_task("task_003")
    assert tarea["estado"] == "paused_planning"
    assert tarea["detalle"] == "Plan listo"
    assert tarea["timestamp_actualizacion"] >= tarea["timestamp_inicio"]


def test_update_status_tarea_inexistente_devuelve_false(registro):
    ok = registro.update_status("task_no_existe", "completed")
    assert ok is False


def test_update_status_estado_invalido_devuelve_false(registro):
    registro.register_task(tarea_id="task_004")
    ok = registro.update_status("task_004", "estado_invalido")
    assert ok is False


def test_get_task_devuelve_tarea_o_none(registro):
    registro.register_task(tarea_id="task_005")
    tarea = registro.get_task("task_005")
    assert tarea is not None
    assert tarea["tarea_id"] == "task_005"
    assert registro.get_task("task_inexistente") is None


def test_list_tasks_devuelve_todas(registro):
    registro.register_task(tarea_id="task_a")
    registro.register_task(tarea_id="task_b")
    tareas = registro.list_tasks()
    assert len(tareas) == 2
    ids = {t["tarea_id"] for t in tareas}
    assert ids == {"task_a", "task_b"}


def test_list_tasks_filtra_por_estado(registro):
    registro.register_task(tarea_id="task_running")
    registro.register_task(tarea_id="task_completed", estado="completed")
    registro.update_status("task_completed", "completed")

    running = registro.list_tasks(estado="running")
    completed = registro.list_tasks(estado="completed")

    assert len(running) == 1
    assert running[0]["tarea_id"] == "task_running"
    assert len(completed) == 1
    assert completed[0]["tarea_id"] == "task_completed"


def test_remove_task_elimina_tarea(registro):
    registro.register_task(tarea_id="task_006")
    assert registro.remove_task("task_006") is True
    assert registro.get_task("task_006") is None
    assert registro.remove_task("task_006") is False


def test_clear_vacia_registro(registro):
    registro.register_task(tarea_id="task_007")
    registro.clear()
    assert registro.list_tasks() == []


def test_concurrencia_multihilo_no_corrompe_registro():
    """Varias operaciones simultáneas no deben corromper el registro."""
    registro = TaskRegistry()

    def operar(i: int):
        tid = f"task_{i}"
        registro.register_task(tarea_id=tid, estado="running")
        registro.update_status(tid, "completed")
        tarea = registro.get_task(tid)
        assert tarea is not None
        assert tarea["estado"] == "completed"

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(operar, range(100)))

    tareas = registro.list_tasks()
    assert len(tareas) == 100
    assert all(t["estado"] == "completed" for t in tareas)


def test_estados_validos_contiene_todos_los_esperados():
    assert ESTADOS_VALIDOS == {
        "running",
        "paused_planning",
        "paused_code",
        "completed",
        "cancelled",
        "timeout",
        "error",
    }


def test_registrar_metricas_tokens_acumula_por_agente(registro):
    registro.register_task(tarea_id="task_metrics_001")
    registro.registrar_metricas_tokens("task_metrics_001", "codificador", 100, 50)
    registro.registrar_metricas_tokens("task_metrics_001", "codificador", 200, 75)

    metricas = registro.obtener_metricas_tokens("task_metrics_001")
    assert metricas == {
        "codificador": {"tokens_entrada": 300, "tokens_salida": 125}
    }


def test_registrar_metricas_tokens_varios_agentes(registro):
    registro.register_task(tarea_id="task_metrics_002")
    registro.registrar_metricas_tokens("task_metrics_002", "planificador", 500, 100)
    registro.registrar_metricas_tokens("task_metrics_002", "codificador", 300, 80)
    registro.registrar_metricas_tokens("task_metrics_002", "revisor", 200, 40)

    metricas = registro.obtener_metricas_tokens("task_metrics_002")
    assert set(metricas.keys()) == {"planificador", "codificador", "revisor"}
    assert metricas["planificador"] == {"tokens_entrada": 500, "tokens_salida": 100}
    assert metricas["codificador"] == {"tokens_entrada": 300, "tokens_salida": 80}
    assert metricas["revisor"] == {"tokens_entrada": 200, "tokens_salida": 40}


def test_obtener_metricas_tokens_tarea_sin_metricas_devuelve_vacio(registro):
    registro.register_task(tarea_id="task_metrics_003")
    assert registro.obtener_metricas_tokens("task_metrics_003") == {}
    assert registro.obtener_metricas_tokens("task_inexistente") == {}


def test_obtener_metricas_tokens_devuelve_copia(registro):
    registro.register_task(tarea_id="task_metrics_004")
    registro.registrar_metricas_tokens("task_metrics_004", "codificador", 100, 50)

    copia = registro.obtener_metricas_tokens("task_metrics_004")
    copia["codificador"]["tokens_entrada"] = 9999
    copia["otro_agente"] = {"tokens_entrada": 1, "tokens_salida": 1}

    metricas = registro.obtener_metricas_tokens("task_metrics_004")
    assert metricas == {"codificador": {"tokens_entrada": 100, "tokens_salida": 50}}