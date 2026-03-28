from langgraph.graph import StateGraph, START
from langgraph.checkpoint.memory import MemorySaver
from app.models.models import ProjectState

from app.agents.agente_planificador import agente_planificador, nodo_herramientas_planificador
from app.agents.agente_codificador import agente_codificador, nodo_herramientas_codificador
from app.agents.agente_revisor import agente_revisor, nodo_herramientas_revisor

def crear_grafo():
    """
    Configura y compila el grafo de estados para el flujo de trabajo de los agentes.
    
    Define los nodos para los agentes planificador, codificador y revisor, así como
    sus respectivos nodos de herramientas, estableciendo el punto de inicio y el
    sistema de persistencia de memoria.
    
    Returns:
        CompiledGraph: El grafo de estados listo para ser ejecutado.
    """
    workflow = StateGraph(ProjectState)
    workflow.add_node("agente_planificador", agente_planificador)
    workflow.add_node("agente_codificador", agente_codificador)
    workflow.add_node("agente_revisor", agente_revisor)
    workflow.add_node("nodo_herramientas_planificador", nodo_herramientas_planificador)
    workflow.add_node("nodo_herramientas_codificador", nodo_herramientas_codificador)
    workflow.add_node("nodo_herramientas_revisor", nodo_herramientas_revisor)

    workflow.add_edge(START, "agente_planificador")

    memory = MemorySaver()

    return workflow.compile(
            checkpointer=memory,
            interrupt_before=["agente_codificador", "agente_revisor"]
        )
