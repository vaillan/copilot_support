"""Módulo principal de orquestación del flujo de trabajo multi-agente.

Este módulo define y compila el grafo de LangGraph conectando los agentes
(Planificador, Codificador, Revisor) y sus respectivos nodos de herramientas.
"""

import sqlite3
from pathlib import Path
from typing import Any, Optional
from langgraph.graph import StateGraph, START
from langgraph.checkpoint.sqlite import SqliteSaver

from app.models.models import ProjectState
from app.agents.agente_planificador import agente_planificador
from app.agents.agente_codificador import agente_codificador
from app.agents.agente_revisor import agente_revisor
from app.utils.tool_nodes import (
    nodo_herramientas_planificador,
    nodo_herramientas_codificador,
    nodo_herramientas_revisor,
)


def _crear_checkpointer_sqlite() -> SqliteSaver:
    """Crea el checkpointer SQLite persistente por defecto.

    Se crea la conexión ``sqlite3`` directamente (en lugar de usar el gestor de
    contexto ``from_conn_string``) para mantener la conexión abierta durante
    toda la vida del grafo compilado; la ruta es fija relativa a la raíz del
    proyecto.
    """
    ruta = Path(__file__).resolve().parent.parent / "checkpoints.sqlite"
    conn = sqlite3.connect(str(ruta), check_same_thread=False)
    return SqliteSaver(conn)


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
        checkpointer: Instancia opcional de persistencia de estado (por defecto usa SqliteSaver persistente en checkpoints.sqlite).

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
