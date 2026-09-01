"""
Registro de tareas en memoria (thread-safe) para el servidor MCP.

Este módulo actúa como una capa de estado ligera que permite rastrear el ciclo
de vida de las tareas delegadas al equipo de agentes LangGraph sin depender del
estado interno del grafo. Expone operaciones de registro, actualización,
consulta, listado y cancelación de tareas.

Los estados válidos son:
    - 'running':          La tarea está en ejecución activa.
    - 'paused_planning':  La tarea está pausada esperando aprobación del plan (PAUSA_1).
    - 'paused_code':      La tarea está pausada esperando aprobación del código (PAUSA_2).
    - 'completed':        La tarea finalizó exitosamente.
    - 'cancelled':        La tarea fue cancelada por el usuario.
    - 'timeout':          La tarea excedió el límite de tiempo de ejecución.
    - 'error':            La tarea falló con un error interno.
"""

import threading
import time
from typing import Any, Dict, List, Optional

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
    Registro de tareas en memoria con seguridad para entornos asíncronos.

    Utiliza un ``threading.Lock`` para garantizar que las operaciones de
    lectura/escritura sobre el diccionario interno sean atómicas incluso si
    múltiples hilos o corrutinas acceden simultáneamente.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tareas: Dict[str, Dict[str, Any]] = {}

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
        Registra una nueva tarea en el registro.

        Args:
            tarea_id: Identificador único de la tarea.
            directorio_proyecto: Ruta del proyecto sobre el que opera la tarea.
            instruccion: Instrucción original proporcionada por el usuario.
            thread_id: Identificador del hilo/grafo LangGraph asociado.
            estado: Estado inicial de la tarea (por defecto 'running').
            **extra: Campos adicionales opcionales (p.ej. 'detalle').

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
        # Permitir campos extra arbitrarios (p.ej. asyncio.Task para cancelación).
        for clave, valor in extra.items():
            if clave != "detalle":
                tarea[clave] = valor

        with self._lock:
            self._tareas[tarea_id] = tarea
        return dict(tarea)

    def update_status(
        self,
        tarea_id: str,
        estado: str,
        **extra: Any,
    ) -> bool:
        """
        Actualiza el estado de una tarea existente.

        Args:
            tarea_id: Identificador de la tarea a actualizar.
            estado: Nuevo estado (debe ser uno de los estados válidos).
            **extra: Campos adicionales a actualizar (p.ej. 'detalle').

        Returns:
            True si la tarea existía y se actualizó; False en caso contrario.
        """
        if estado not in ESTADOS_VALIDOS:
            return False

        with self._lock:
            tarea = self._tareas.get(tarea_id)
            if tarea is None:
                return False
            tarea["estado"] = estado
            tarea["timestamp_actualizacion"] = time.time()
            for clave, valor in extra.items():
                tarea[clave] = valor
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
            tarea = self._tareas.get(tarea_id)
            return dict(tarea) if tarea is not None else None

    def list_tasks(self, estado: str = "") -> list:
        """
        Lista las tareas registradas, opcionalmente filtradas por estado.

        Args:
            estado: Si se proporciona, filtra por ese estado (p.ej. 'running').

        Returns:
            Lista de diccionarios con los datos de las tareas.
        """
        with self._lock:
            tareas = list(self._tareas.values())
        if estado:
            tareas = [t for t in tareas if t.get("estado") == estado]
        return [dict(t) for t in tareas]

    def remove_task(self, tarea_id: str) -> bool:
        """
        Elimina una tarea del registro.

        Args:
            tarea_id: Identificador de la tarea a eliminar.

        Returns:
            True si la tarea existía y fue eliminada; False en caso contrario.
        """
        with self._lock:
            if tarea_id in self._tareas:
                del self._tareas[tarea_id]
                return True
        return False

    def clear(self) -> None:
        """Elimina todas las tareas del registro (útil en pruebas)."""
        with self._lock:
            self._tareas.clear()


# Instancia singleton compartida por todo el servidor MCP.
task_registry = TaskRegistry()