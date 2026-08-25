"""Módulo principal de orquestación del flujo de trabajo multi-agente.

Este módulo define y compila el grafo de LangGraph conectando los agentes
(Planificador, Codificador, Revisor) y sus respectivos nodos de herramientas.
"""

import aiosqlite
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from langgraph.graph import StateGraph, START
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.models.models import ProjectState
from app.agents.agente_planificador import agente_planificador
from app.agents.agente_codificador import agente_codificador
from app.agents.agente_revisor import agente_revisor
from app.utils.tool_nodes import (
    nodo_herramientas_planificador,
    nodo_herramientas_codificador,
    nodo_herramientas_revisor,
)


class _CheckpointerDiferido(BaseCheckpointSaver):
    """Proxy de ``AsyncSqliteSaver`` que difiere su construcción al primer uso async.

    ``AsyncSqliteSaver`` exige un event loop activo en su constructor
    (``asyncio.get_running_loop()``), pero el grafo se compila al importar
    ``mcp_server`` (sin loop). Este proxy delega los métodos async y crea el
    saver real en la primera llamada, ya dentro del loop del servidor MCP.
    """

    def __init__(self, ruta: Path):
        super().__init__()
        self._ruta = ruta
        self._saver: Optional[AsyncSqliteSaver] = None

    async def _obtener_saver(self) -> AsyncSqliteSaver:
        if self._saver is None:
            conn = await aiosqlite.connect(str(self._ruta))
            self._saver = AsyncSqliteSaver(conn)
        return self._saver

    async def aget_tuple(self, config):
        return await (await self._obtener_saver()).aget_tuple(config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await (await self._obtener_saver()).aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await (await self._obtener_saver()).aput_writes(config, writes, task_id, task_path)

    async def alist(
        self,
        config=None,
        *,
        filter=None,  # noqa: A002 - firma idéntica a BaseCheckpointSaver.alist
        before=None,
        limit=None,
    ) -> AsyncIterator:
        saver = await self._obtener_saver()
        async for tupla in saver.alist(config, filter=filter, before=before, limit=limit):
            yield tupla

    async def adelete_thread(self, thread_id):
        await (await self._obtener_saver()).adelete_thread(thread_id)


def _crear_checkpointer_sqlite() -> _CheckpointerDiferido:
    """Crea el checkpointer SQLite persistente por defecto (versión async diferida).

    La ruta es fija relativa a la raíz del proyecto (checkpoints.sqlite).

    Nota: se usa ``AsyncSqliteSaver`` porque el servidor MCP (mcp_server.py)
    ejecuta el grafo con ``ainvoke``/``aget_state``; el ``SqliteSaver`` síncrono
    no soporta métodos async y lanza NotImplementedError.
    """
    ruta = Path(__file__).resolve().parent.parent / "checkpoints.sqlite"
    return _CheckpointerDiferido(ruta)


def crear_grafo(
    interrumpir_en_codificador: bool = True,
    interrumpir_en_revisor: bool = True,
    checkpointer: Optional[Any] = None,
):
    """
    Construye y compila el flujo de trabajo multi-agente en LangGraph.

    Flujo de ejecución:
    1. START -> agente_planificador
    2. agente_planificador -> nodo_herramientas_planificador -> agente_planificador
       O agente_planificador -> agente_codificador (mediante Command)
    3. agente_codificador -> nodo_herramientas_codificador -> agente_codificador
       O agente_codificador -> agente_revisor (mediante Command)
    4. agente_revisor -> nodo_herramientas_revisor -> agente_revisor
       O agente_revisor -> agente_codificador (en caso de rechazo)
       O agente_revisor -> END (en caso de aprobación)

    Args:
        interrumpir_en_codificador: Si es True, pausa la ejecución antes del codificador para revisión humana.
        interrumpir_en_revisor: Si es True, pausa la ejecución antes del revisor para revisión humana.
        checkpointer: Instancia opcional de persistencia de estado (por defecto usa AsyncSqliteSaver persistente en checkpoints.sqlite).

    Returns:
        CompiledStateGraph: Grafo compilado y listo para ejecución.
    """
    workflow = StateGraph(ProjectState)

    # 1. Nodos de Agentes
    workflow.add_node("agente_planificador", agente_planificador)
    workflow.add_node("agente_codificador", agente_codificador)
    workflow.add_node("agente_revisor", agente_revisor)

    # 2. Nodos de Herramientas específicos
    workflow.add_node("nodo_herramientas_planificador", nodo_herramientas_planificador)
    workflow.add_node("nodo_herramientas_codificador", nodo_herramientas_codificador)
    workflow.add_node("nodo_herramientas_revisor", nodo_herramientas_revisor)

    # 3. Punto de entrada
    workflow.add_edge(START, "agente_planificador")

    # 4. Conexiones cíclicas de herramientas de vuelta al agente correspondiente
    workflow.add_edge("nodo_herramientas_planificador", "agente_planificador")
    workflow.add_edge("nodo_herramientas_codificador", "agente_codificador")
    workflow.add_edge("nodo_herramientas_revisor", "agente_revisor")

    # 5. Checkpointer para persistencia del estado
    if checkpointer is None:
        checkpointer = _crear_checkpointer_sqlite()

    # 6. Configuración de interrupciones para Human-in-the-loop
    interrupt_before = []
    if interrumpir_en_codificador:
        interrupt_before.append("agente_codificador")
    if interrumpir_en_revisor:
        interrupt_before.append("agente_revisor")

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before if interrupt_before else None,
    )


if __name__ == "__main__":
    app = crear_grafo()
    print("Grafo de agentes compilado exitosamente.")
