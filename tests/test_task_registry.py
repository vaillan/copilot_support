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
def registro(tmp_path):
    """Fixture que devuelve un TaskRegistry limpio por prueba (persistencia aislada en tmp)."""
    return TaskRegistry(ruta_persistencia=str(tmp_path / ".task_registry.json"))


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


def test_concurrencia_multihilo_no_corrompe_registro(tmp_path):
    """Varias operaciones simultáneas no deben corromper el registro."""
    registro = TaskRegistry(ruta_persistencia=str(tmp_path / ".task_registry.json"))

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


# ----------------------------------------------------------------------
# Persistencia en disco (supervivencia a reinicios del proceso MCP)
# ----------------------------------------------------------------------

def test_persistencia_sobrevive_reinicio_del_proceso(tmp_path):
    """Simula un reinicio del servidor MCP: una NUEVA instancia del registro
    debe recuperar las tareas persistidas por la instancia anterior."""
    ruta = str(tmp_path / ".task_registry.json")
    registro = TaskRegistry(ruta_persistencia=ruta)
    registro.register_task(tarea_id="task_reinicio", estado="running")
    registro.update_status("task_reinicio", "paused_planning", detalle="Plan listo")

    registro_reiniciado = TaskRegistry(ruta_persistencia=ruta)
    tarea = registro_reiniciado.get_task("task_reinicio")
    assert tarea is not None
    assert tarea["estado"] == "paused_planning"
    assert tarea["detalle"] == "Plan listo"


def test_update_status_persiste_estado_en_disco(tmp_path):
    """El cambio de estado debe reflejarse inmediatamente en el archivo JSON."""
    import json

    ruta = tmp_path / ".task_registry.json"
    registro = TaskRegistry(ruta_persistencia=str(ruta))
    registro.register_task(tarea_id="task_disco")
    registro.update_status("task_disco", "completed", detalle="OK")

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)
    assert datos["task_disco"]["estado"] == "completed"
    assert datos["task_disco"]["detalle"] == "OK"


def test_fallo_io_degrada_a_memoria_sin_excepcion(tmp_path):
    """Si la persistencia falla (ruta no escribible), el registro sigue
    funcionando en memoria y no propaga excepciones."""
    # 'padre' es un ARCHIVO: mkdir(parents=True) sobre su hijo fallará.
    padre_archivo = tmp_path / "padre"
    padre_archivo.write_text("no soy un directorio", encoding="utf-8")
    ruta_invalida = padre_archivo / "sub" / ".task_registry.json"

    registro = TaskRegistry(ruta_persistencia=str(ruta_invalida))
    tarea = registro.register_task(tarea_id="task_memoria")
    assert tarea["tarea_id"] == "task_memoria"
    assert registro.get_task("task_memoria") is not None
    assert registro.update_status("task_memoria", "completed") is True


def test_remove_task_y_clear_persisten_cambios(tmp_path):
    """remove_task y clear deben reflejarse en el archivo de persistencia."""
    import json

    ruta = tmp_path / ".task_registry.json"
    registro = TaskRegistry(ruta_persistencia=str(ruta))
    registro.register_task(tarea_id="task_borrar")
    registro.remove_task("task_borrar")

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)
    assert "task_borrar" not in datos

    registro.register_task(tarea_id="task_otra")
    registro.clear()
    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)
    assert datos == {}