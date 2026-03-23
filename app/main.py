from langgraph.graph import StateGraph, START
from models.models import ProjectState

# Importamos las funciones desde tus archivos modulares
from agents.agente_planificador import agente_planificador, nodo_herramientas_planificador
from agents.agente_codificador import agente_codificador, nodo_herramientas_codificador
from agents.agente_revisor import agente_revisor, nodo_herramientas_revisor

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

    return workflow.compile()

#if __name__ == "__main__":
#    app = crear_grafo()
 
#    # Aquí puedes ejecutar app.stream(...) como vimos en la Tarea 4
#    print("Grafo modular compilado con éxito.")