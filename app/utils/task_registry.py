"""
Registro de tareas persistente en SQLite (thread-safe) para el servidor MCP.

Este módulo actúa como una capa de estado ligera que permite rastrear el ciclo
de vida de las tareas delegadas al equipo de agentes LangGraph sin depender del
estado interno del grafo. Expone operaciones de registro, actualización,
consulta, listado y cancelación de tareas. La fachada síncrona ``TaskRegistry``
delega en ``_TaskRegistryDiferido``, que mantiene una conexión aiosqlite en un
event loop dedicado (patrón diferido de ``_CheckpointerDiferido``).

Los estados válidos son:
    - 'running':          La tarea está en ejecución activa.
    - 'paused_planning':  La tarea está pausada esperando aprobación del plan (PAUSA_1).
    - 'paused_code':      La tarea está pausada esperando aprobación del código (PAUSA_2).
    - 'completed':        La tarea finalizó exitosamente.
    - 'cancelled':        La tarea fue cancelada por el usuario.
    - 'timeout':          La tarea excedió el límite de tiempo de ejecución.
    - 'error':            La tarea falló con un error interno.
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Dict, List, Optional

import aiosqlite

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

# Archivo SQLite de persistencia en la raíz del proyecto.
_RUTA_SQLITE: Path = Path(__file__).resolve().parent.parent.parent / "task_registry.sqlite"

_SQL_CREAR_TABLA = """
CREATE TABLE IF NOT EXISTS tareas (
    tarea_id TEXT PRIMARY KEY,
    directorio_proyecto TEXT NOT NULL DEFAULT '',
    instruccion TEXT NOT NULL DEFAULT '',
    thread_id TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'running',
    timestamp_inicio REAL NOT NULL,
    timestamp_actualizacion REAL NOT NULL,
    detalle TEXT NOT NULL DEFAULT ''
)
"""


def _serializar_detalle(detalle: Any, extra: Dict[str, Any]) -> str:
    """Serializa detalle y campos extra en el blob JSON de la columna detalle."""
    return json.dumps({"detalle": detalle, "_extra": extra}, ensure_ascii=False)


def _deserializar_detalle(blob: str) -> tuple[Any, Dict[str, Any]]:
    """Reconstruye (detalle, extra) desde el blob JSON; ante datos corruptos devuelve (blob, {})."""
    try:
        valor = json.loads(blob)
        return valor["detalle"], valor["_extra"]
    except (json.JSONDecodeError, TypeError, KeyError):
        return blob, {}


class _TaskRegistryDiferido:
    """Proxy de conexión aiosqlite diferida al primer uso async.

    Replica el patrón de ``_CheckpointerDiferido`` (app/main.py): la conexión se
    crea de forma perezosa dentro de un event loop dedicado en un hilo daemon,
    de modo que el registro funciona en contextos síncronos y asíncronos sin
    depender del loop del hilo llamante.
    """

    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta
        self._conexion: Optional[aiosqlite.Connection] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _iniciar_loop(self) -> None:
        """Arranca el event loop dedicado en un hilo daemon (una sola vez)."""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            hilo = threading.Thread(
                target=self._loop.run_forever,
                daemon=True,
                name="task-registry-loop",
            )
            hilo.start()

    async def _obtener_conexion(self) -> aiosqlite.Connection:
        """Crea la conexión aiosqlite y la tabla en el primer uso."""
        if self._conexion is None:
            self._conexion = await aiosqlite.connect(str(self._ruta))
            await self._conexion.execute(_SQL_CREAR_TABLA)
            await self._conexion.commit()
        return self._conexion

    def _ejecutar_async(self, coro: Awaitable[Any]) -> Any:
        """Ejecuta una corrutina en el loop dedicado y re-lanza excepciones aquí."""
        self._iniciar_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _vaciar_tabla(self) -> None:
        conexion = await self._obtener_conexion()
        await conexion.execute("DELETE FROM tareas")
        await conexion.commit()

    async def _registrar(self, tarea: Dict[str, Any], extra: Dict[str, Any]) -> None:
        conexion = await self._obtener_conexion()
        await conexion.execute(
            "INSERT OR REPLACE INTO tareas "
            "(tarea_id, directorio_proyecto, instruccion, thread_id, estado, "
            "timestamp_inicio, timestamp_actualizacion, detalle) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tarea["tarea_id"],
                tarea["directorio_proyecto"],
                tarea["instruccion"],
                tarea["thread_id"],
                tarea["estado"],
                tarea["timestamp_inicio"],
                tarea["timestamp_actualizacion"],
                _serializar_detalle(tarea["detalle"], extra),
            ),
        )
        await conexion.commit()

    async def _actualizar(
        self, tarea_id: str, estado: str, detalle: Any, extra: Dict[str, Any]
    ) -> bool:
        conexion = await self._obtener_conexion()
        cursor = await conexion.execute(
            "SELECT detalle FROM tareas WHERE tarea_id = ?", (tarea_id,)
        )
        fila = await cursor.fetchone()
        if fila is None:
            return False
        detalle_previo, extra_previo = _deserializar_detalle(fila[0])
        if detalle is None:
            detalle = detalle_previo
        extra_previo.update(extra)
        nuevo_blob = _serializar_detalle(detalle, extra_previo)
        await conexion.execute(
            "UPDATE tareas SET estado = ?, timestamp_actualizacion = ?, detalle = ? "
            "WHERE tarea_id = ?",
            (estado, time.time(), nuevo_blob, tarea_id),
        )
        await conexion.commit()
        return True

    async def _obtener(self, tarea_id: str) -> Optional[Dict[str, Any]]:
        conexion = await self._obtener_conexion()
        cursor = await conexion.execute(
            "SELECT tarea_id, directorio_proyecto, instruccion, thread_id, estado, "
            "timestamp_inicio, timestamp_actualizacion, detalle "
            "FROM tareas WHERE tarea_id = ?",
            (tarea_id,),
        )
        fila = await cursor.fetchone()
        if fila is None:
            return None
        return self._reconstruir(fila)

    async def _listar(self, estado: str = "") -> List[Dict[str, Any]]:
        conexion = await self._obtener_conexion()
        if estado:
            cursor = await conexion.execute(
                "SELECT tarea_id, directorio_proyecto, instruccion, thread_id, estado, "
                "timestamp_inicio, timestamp_actualizacion, detalle "
                "FROM tareas WHERE estado = ?",
                (estado,),
            )
        else:
            cursor = await conexion.execute(
                "SELECT tarea_id, directorio_proyecto, instruccion, thread_id, estado, "
                "timestamp_inicio, timestamp_actualizacion, detalle FROM tareas"
            )
        filas = await cursor.fetchall()
        return [self._reconstruir(fila) for fila in filas]

    async def _eliminar(self, tarea_id: str) -> bool:
        conexion = await self._obtener_conexion()
        cursor = await conexion.execute(
            "DELETE FROM tareas WHERE tarea_id = ?", (tarea_id,)
        )
        await conexion.commit()
        return cursor.rowcount > 0

    async def _limpiar(self) -> None:
        conexion = await self._obtener_conexion()
        await conexion.execute("DELETE FROM tareas")
        await conexion.commit()

    @staticmethod
    def _reconstruir(fila: tuple) -> Dict[str, Any]:
        """Convierte una fila SQLite en dict, deserializando detalle y promoviendo _extra."""
        (
            tarea_id,
            directorio_proyecto,
            instruccion,
            thread_id,
            estado,
            timestamp_inicio,
            timestamp_actualizacion,
            detalle_blob,
        ) = fila
        detalle, extra = _deserializar_detalle(detalle_blob)
        tarea: Dict[str, Any] = {
            "tarea_id": tarea_id,
            "directorio_proyecto": directorio_proyecto,
            "instruccion": instruccion,
            "thread_id": thread_id,
            "estado": estado,
            "timestamp_inicio": timestamp_inicio,
            "timestamp_actualizacion": timestamp_actualizacion,
            "detalle": detalle,
        }
        tarea.update(extra)
        return tarea


class TaskRegistry:
    """Fachada síncrona thread-safe sobre el registro persistente en SQLite."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._deferido = _TaskRegistryDiferido(_RUTA_SQLITE)
        # Primer uso: conexión diferida + arranque limpio por instancia/proceso.
        self._deferido._ejecutar_async(self._deferido._vaciar_tabla())

    def register_task(
        self,
        tarea_id: str,
        directorio_proyecto: str = "",
        instruccion: str = "",
        thread_id: str = "",
        estado: str = "running",
        **extra: Any,
    ) -> Dict[str, Any]:
        """Registra una tarea y devuelve el diccionario completo de la misma."""
        estado = estado if estado in ESTADOS_VALIDOS else "running"
        thread_id = thread_id or tarea_id
        timestamp = time.time()
        tarea = {
            "tarea_id": tarea_id,
            "thread_id": thread_id,
            "directorio_proyecto": directorio_proyecto,
            "instruccion": instruccion,
            "estado": estado,
            "timestamp_inicio": timestamp,
            "timestamp_actualizacion": timestamp,
            "detalle": extra.get("detalle", ""),
        }
        extra_otros = {k: v for k, v in extra.items() if k != "detalle"}
        with self._lock:
            self._deferido._ejecutar_async(self._deferido._registrar(tarea, extra_otros))
        return dict(tarea)

    def update_status(
        self,
        tarea_id: str,
        estado: str,
        **extra: Any,
    ) -> bool:
        """Actualiza el estado de una tarea; True si existía, False en caso contrario."""
        if estado not in ESTADOS_VALIDOS:
            return False
        detalle = extra.get("detalle")
        extra_otros = {k: v for k, v in extra.items() if k != "detalle"}
        with self._lock:
            return bool(
                self._deferido._ejecutar_async(
                    self._deferido._actualizar(tarea_id, estado, detalle, extra_otros)
                )
            )

    def get_task(self, tarea_id: str) -> Optional[Dict[str, Any]]:
        """Devuelve una copia de la tarea solicitada o None si no existe."""
        with self._lock:
            return self._deferido._ejecutar_async(self._deferido._obtener(tarea_id))

    def list_tasks(self, estado: str = "") -> list:
        """Lista las tareas registradas, opcionalmente filtradas por estado."""
        with self._lock:
            return self._deferido._ejecutar_async(self._deferido._listar(estado))

    def remove_task(self, tarea_id: str) -> bool:
        """Elimina una tarea; True si existía, False en caso contrario."""
        with self._lock:
            return bool(self._deferido._ejecutar_async(self._deferido._eliminar(tarea_id)))

    def clear(self) -> None:
        """Elimina todas las tareas del registro (útil en pruebas)."""
        with self._lock:
            self._deferido._ejecutar_async(self._deferido._limpiar())


# Instancia singleton compartida por todo el servidor MCP.
task_registry = TaskRegistry()