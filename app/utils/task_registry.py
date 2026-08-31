"""
Registro de tareas persistente en SQLite (thread-safe) para el servidor MCP.

Este módulo actúa como una capa de estado ligera que permite rastrear el ciclo
de vida de las tareas delegadas al equipo de agentes LangGraph sin depender del
estado interno del grafo. Expone operaciones de registro, actualización,
consulta, listado y cancelación de tareas.

A diferencia del checkpointer del grafo (SQLite persistente en checkpoints.sqlite),
el registro era originalmente volátil: al reiniciarse el proceso del servidor MCP
se perdían las tareas registradas mientras el grafo conservaba su estado pausado,
produciendo la inconsistencia 'tarea no registrada' + 'grafo pausado'. Ahora el
registro se persiste en una base SQLite dedicada (tasks.db) con journal_mode WAL,
siguiendo el mismo patrón de persistencia que los checkpointers de LangGraph, de
modo que el ciclo de vida de las tareas sobrevive a reinicios del servidor.

Los estados válidos son:
    - 'running':          La tarea está en ejecución activa.
    - 'paused_planning':  La tarea está pausada esperando aprobación del plan (PAUSA_1).
    - 'paused_code':      La tarea está pausada esperando aprobación del código (PAUSA_2).
    - 'completed':        La tarea finalizó exitosamente.
    - 'cancelled':        La tarea fue cancelada por el usuario.
    - 'timeout':          La tarea excedió el límite de tiempo de ejecución.
    - 'error':            La tarea falló con un error interno.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.settings.settings import Settings, WORKING_DIRECTORY

# Estados válidos del ciclo de vida de una tarea.
ESTADOS_VALIDOS = {
    "running",
    "paused_planning",
    "paused_code",
    "completed",
    "cancelled",
    "timeout",
    "error",
}


class TaskRegistry:
    """
    Registro de tareas persistente en SQLite con seguridad para entornos asíncronos.

    Utiliza una única conexión sqlite3 con ``check_same_thread=False`` protegida
    por un ``threading.Lock`` para garantizar que las operaciones de
    lectura/escritura sean atómicas incluso si múltiples hilos o corrutinas
    acceden simultáneamente. La base se abre con ``journal_mode=WAL`` (mismo
    patrón que los checkpointers de LangGraph); ante cualquier fallo de E/S se
    degrada a una base en memoria (``:memory:``) sin lanzar excepciones, de modo
    que la persistencia nunca rompe el flujo del servidor.
    """

    def __init__(self, ruta_persistencia: Optional[str] = None) -> None:
        """
        Inicializa el registro y abre/crea la base SQLite de persistencia.

        Args:
            ruta_persistencia: Ruta del archivo SQLite de persistencia. Si es None,
                se usa el setting TASK_REGISTRY_PATH; si este está vacío, se usa
                <WORKING_DIRECTORY>/tasks.db.
        """
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        if ruta_persistencia is None:
            try:
                settings = Settings()
                ruta_persistencia = getattr(settings, "TASK_REGISTRY_PATH", "") or str(
                    WORKING_DIRECTORY / "tasks.db"
                )
            except Exception:
                ruta_persistencia = "tasks.db"
        self._ruta_persistencia = Path(ruta_persistencia)
        self._conectar()

    # ------------------------------------------------------------------
    # Conexión SQLite (WAL, tolerante a fallos)
    # ------------------------------------------------------------------

    def _conectar(self) -> None:
        """Abre la conexión SQLite y crea el esquema si no existe.

        Ante cualquier fallo (ruta no escribible, permisos, base corrupta)
        degrada a una base en memoria (``:memory:``) sin lanzar excepción.
        """
        try:
            self._ruta_persistencia.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._ruta_persistencia), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    tarea_id TEXT PRIMARY KEY,
                    datos TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.commit()
            self._conn = conn
        except Exception:
            # Degradación controlada: base en memoria.
            try:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        tarea_id TEXT PRIMARY KEY,
                        datos TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                    """
                )
                conn.commit()
                self._conn = conn
            except Exception:
                self._conn = None

    def _persistir(self, tarea_id: str, tarea: Dict[str, Any], timestamp: float) -> None:
        """Inserta o reemplaza la fila de una tarea (requiere el lock adquirido)."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (tarea_id, datos, timestamp) VALUES (?, ?, ?)",
                (tarea_id, json.dumps(tarea, ensure_ascii=False), timestamp),
            )
            self._conn.commit()
        except Exception:
            pass

    def _eliminar(self, tarea_id: str) -> None:
        """Elimina la fila de una tarea (requiere el lock adquirido)."""
        if self._conn is None:
            return
        try:
            self._conn.execute("DELETE FROM tasks WHERE tarea_id = ?", (tarea_id,))
            self._conn.commit()
        except Exception:
            pass

    def _get_tarea(self, tarea_id: str) -> Optional[Dict[str, Any]]:
        """Devuelve la tarea con el id dado o None (requiere el lock adquirido)."""
        if self._conn is None:
            return None
        try:
            fila = self._conn.execute(
                "SELECT datos FROM tasks WHERE tarea_id = ?", (tarea_id,)
            ).fetchone()
            if fila is None:
                return None
            tarea = json.loads(fila[0])
            return tarea if isinstance(tarea, dict) else None
        except Exception:
            return None

    def _cargar_todas(self) -> Dict[str, Dict[str, Any]]:
        """Carga todas las tareas desde la base (requiere el lock adquirido)."""
        tareas: Dict[str, Dict[str, Any]] = {}
        if self._conn is None:
            return tareas
        try:
            cursor = self._conn.execute("SELECT tarea_id, datos FROM tasks")
            for tarea_id, datos_json in cursor.fetchall():
                try:
                    tarea = json.loads(datos_json)
                    if isinstance(tarea, dict) and tarea.get("tarea_id"):
                        tareas[str(tarea_id)] = tarea
                except Exception:
                    continue
        except Exception:
            pass
        return tareas

    # ------------------------------------------------------------------
    # API pública (sin cambios de firma respecto a la versión JSON)
    # ------------------------------------------------------------------

    def register_task(
        self,
        tarea_id: str,
        directorio_proyecto: str = "",
        instruccion: str = "",
        thread_id: str = "",
        estado: str = "running",
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        Registra una nueva tarea en el registro (y la persiste en SQLite).

        Args:
            tarea_id: Identificador único de la tarea.
            directorio_proyecto: Ruta del proyecto sobre el que opera la tarea.
            instruccion: Instrucción original proporcionada por el usuario.
            thread_id: Identificador del hilo/grafo LangGraph asociado.
            estado: Estado inicial de la tarea (por defecto 'running').
            **extra: Campos adicionales opcionales (p. ej. 'detalle').

        Returns:
            El diccionario completo de la tarea recién registrada.
        """
        estado = estado if estado in ESTADOS_VALIDOS else "running"
        timestamp = time.time()
        tarea = {
            "tarea_id": tarea_id,
            "thread_id": thread_id or tarea_id,
            "directorio_proyecto": directorio_proyecto,
            "instruccion": instruccion,
            "estado": estado,
            "timestamp_inicio": timestamp,
            "timestamp_actualizacion": timestamp,
            "detalle": extra.get("detalle", ""),
        }
        # Permitir campos extra arbitrarios (p. ej. asyncio.Task para cancelación).
        for clave, valor in extra.items():
            if clave != "detalle":
                tarea[clave] = valor

        with self._lock:
            self._persistir(tarea_id, tarea, timestamp)
        return dict(tarea)

    def update_status(
        self,
        tarea_id: str,
        estado: str,
        **extra: Any,
    ) -> bool:
        """
        Actualiza el estado de una tarea existente (y persiste el cambio en SQLite).

        Args:
            tarea_id: Identificador de la tarea a actualizar.
            estado: Nuevo estado (debe ser uno de los estados válidos).
            **extra: Campos adicionales a actualizar (p. ej. 'detalle').

        Returns:
            True si la tarea existía y se actualizó; False en caso contrario.
        """
        if estado not in ESTADOS_VALIDOS:
            return False

        with self._lock:
            tarea = self._get_tarea(tarea_id)
            if tarea is None:
                return False
            tarea["estado"] = estado
            tarea["timestamp_actualizacion"] = time.time()
            for clave, valor in extra.items():
                tarea[clave] = valor
            self._persistir(tarea_id, tarea, tarea["timestamp_actualizacion"])
        return True

    def get_task(self, tarea_id: str) -> Optional[Dict[str, Any]]:
        """
        Devuelve una copia de la tarea solicitada o None si no existe.

        Args:
            tarea_id: Identificador de la tarea.

        Returns:
            Diccionario con los datos de la tarea o None.
        """
        with self._lock:
            tarea = self._get_tarea(tarea_id)
            return dict(tarea) if tarea is not None else None

    def list_tasks(self, estado: str = "") -> List[Dict[str, Any]]:
        """
        Lista las tareas registradas, opcionalmente filtradas por estado.

        Args:
            estado: Si se proporciona, filtra por ese estado (p. ej. 'running').

        Returns:
            Lista de diccionarios con los datos de las tareas.
        """
        with self._lock:
            tareas = list(self._cargar_todas().values())
        if estado:
            tareas = [t for t in tareas if t.get("estado") == estado]
        return [dict(t) for t in tareas]

    def remove_task(self, tarea_id: str) -> bool:
        """
        Elimina una tarea del registro (y persiste el cambio en SQLite).

        Args:
            tarea_id: Identificador de la tarea a eliminar.

        Returns:
            True si la tarea existía y fue eliminada; False en caso contrario.
        """
        with self._lock:
            if self._get_tarea(tarea_id) is None:
                return False
            self._eliminar(tarea_id)
            return True

    def clear(self) -> None:
        """Elimina todas las tareas del registro (útil en pruebas) y persiste el vaciado."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.execute("DELETE FROM tasks")
                    self._conn.commit()
                except Exception:
                    pass


# Instancia singleton compartida por todo el servidor MCP.
task_registry = TaskRegistry()