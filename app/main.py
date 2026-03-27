from langgraph.graph import StateGraph, START
from app.models.models import ProjectState

# Importamos las funciones desde tus archivos modulares
from app.agents.agente_planificador import agente_planificador, nodo_herramientas_planificador
from app.agents.agente_codificador import agente_codificador, nodo_herramientas_codificador
from app.agents.agente_revisor import agente_revisor, nodo_herramientas_revisor


def crear_grafo():
    workflow = StateGraph(ProjectState)

    # 1. Agregamos los Nodos (Cerebros)
    workflow.add_node("agente_planificador", agente_planificador)
    workflow.add_node("agente_codificador", agente_codificador)
    workflow.add_node("agente_revisor", agente_revisor)

    # 2. Agregamos los Nodos (Herramientas)
    workflow.add_node("nodo_herramientas_planificador", nodo_herramientas_planificador)
    workflow.add_node("nodo_herramientas_codificador", nodo_herramientas_codificador)
    workflow.add_node("nodo_herramientas_revisor", nodo_herramientas_revisor)

    # 3. Punto de entrada
    workflow.add_edge(START, "agente_planificador")

    # Importamos el checkpointer para la persistencia
    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()

    # Compilamos con el checkpointer e interrupción antes del agente_codificador (human in the loop)
    return workflow.compile(checkpointer=memory, interrupt_before=["agente_codificador"])
