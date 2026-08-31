"""
Registro de tareas persistente en disco (thread-safe) para el servidor MCP.

Este módulo actúa como una capa de estado ligera que permite rastrear el ciclo
de vida de las tareas delegadas al equipo de agentes LangGraph sin depender del
estado interno del grafo. Expone operaciones de registro, actualización,
consulta, listado y cancelación de tareas.

A diferencia del checkpointer del grafo (SQLite persistente en checkpoints.sqlite),
el registro era originalmente volátil: al reiniciarse el proceso del servidor MCP
se perdían las tareas registradas mientras el grafo conservaba su estado pausado,
produciendo la inconsistencia 'tarea no registrada' + 'grafo pausado'. Ahora el
registro se persiste en un archivo JSON con escritura atómica, de modo que el
ciclo de vida de las tareas sobrevive a reinicios del servidor.

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
import os
import tempfile
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
    Registro de tareas persistente en disco con seguridad para entornos asíncronos.

    Utiliza un ``threading.Lock`` para garantizar que las operaciones de
    lectura/escritura sobre el diccionario interno sean atómicas incluso si
    múltiples hilos o corrutinas acceden simultáneamente. El estado se persiste
    en un archivo JSON con escritura atómica (archivo temporal + rename); ante
    cualquier fallo de E/S se degrada a comportamiento en memoria sin lanzar
    excepciones, de modo que la persistencia nunca rompe el flujo del servidor.
    """

    def __init__(self, ruta_persistencia: Optional[str] = None) -> None:
        """
        Inicializa el registro y carga las tareas persistidas en disco.

        Args:
            ruta_persistencia: Ruta del archivo JSON de persistencia. Si es None,
                se usa el setting TASK_REGISTRY_PATH; si este está vacío, se usa
                <WORKING_DIRECTORY>/.task_registry.json.
        """
        self._lock = threading.Lock()
        self._tareas: Dict[str, Dict[str, Any]] = {}
        if ruta_persistencia is None:
            try:
                settings = Settings()
                ruta_persistencia = getattr(settings, "TASK_REGISTRY_PATH", "") or str(
                    WORKING_DIRECTORY / ".task_registry.json"
                )
            except Exception:
                ruta_persistencia = ".task_registry.json"
        self._ruta_persistencia = Path(ruta_persistencia)
        self._cargar_de_disco()

    # ------------------------------------------------------------------
    # Persistencia en disco (atómica y tolerante a fallos)
    # ------------------------------------------------------------------

    def _cargar_de_disco(self) -> None:
        """Carga las tareas desde el archivo JSON de persistencia.

        Ante cualquier fallo (archivo corrupto, permisos, formato inválido)
        degrada a un registro vacío en memoria sin lanzar excepción.
        """
        try:
            if self._ruta_persistencia.exists():
                with open(self._ruta_persistencia, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                if isinstance(datos, dict):
                    for tarea_id, tarea in datos.items():
                        if isinstance(tarea, dict) and tarea.get("tarea_id"):
                            self._tareas[str(tarea_id)] = tarea
        except Exception:
            self._tareas = {}

    def _guardar_a_disco(self) -> None:
        """Persiste el registro en disco con escritura atómica (temporal + rename).

        Nunca propaga excepciones: si la E/S falla, el registro sigue funcionando
        en memoria (degradación controlada) y se limpia el archivo temporal.
        """
        ruta_temporal = ""
        try:
            self._ruta_persistencia.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=str(self._ruta_persistencia.parent),
                prefix=f"{self._ruta_persistencia.name}.",
                suffix=".tmp",
            ) as f:
                json.dump(self._tareas, f, ensure_ascii=False, indent=2)
                ruta_temporal = f.name
            os.replace(ruta_temporal, self._ruta_persistencia)
        except Exception:
            if ruta_temporal:
                try:
                    os.remove(ruta_temporal)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # API pública (sin cambios de firma respecto a la versión en memoria)
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
        Registra una nueva tarea en el registro (y la persiste en disco).

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
            self._tareas[tarea_id] = tarea
            self._guardar_a_disco()
        return dict(tarea)

    def update_status(
        self,
        tarea_id: str,
        estado: str,
        **extra: Any,
    ) -> bool:
        """
        Actualiza el estado de una tarea existente (y persiste el cambio en disco).

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
            tarea = self._tareas.get(tarea_id)
            if tarea is None:
                return False
            tarea["estado"] = estado
            tarea["timestamp_actualizacion"] = time.time()
            for clave, valor in extra.items():
                tarea[clave] = valor
            self._guardar_a_disco()
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
            estado: Si se proporciona, filtra por ese estado (p. ej. 'running').

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
        Elimina una tarea del registro (y persiste el cambio en disco).

        Args:
            tarea_id: Identificador de la tarea a eliminar.

        Returns:
            True si la tarea existía y fue eliminada; False en caso contrario.
        """
        with self._lock:
            if tarea_id in self._tareas:
                del self._tareas[tarea_id]
                self._guardar_a_disco()
                return True
        return False

    def clear(self) -> None:
        """Elimina todas las tareas del registro (útil en pruebas) y persiste el vaciado."""
        with self._lock:
            self._tareas.clear()
            self._guardar_a_disco()


# Instancia singleton compartida por todo el servidor MCP.
task_registry = TaskRegistry()
