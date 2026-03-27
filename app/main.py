from langgraph.graph import StateGraph, START, END
from app.models.models import ProjectState
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage
from langgraph.types import Command

# Importamos el checkpointer persistente en disco
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from pathlib import Path

# Importamos las funciones desde tus archivos modulares
from app.agents.agente_planificador import agente_planificador, nodo_herramientas_planificador
from app.agents.agente_codificador import agente_codificador, nodo_herramientas_codificador
from app.agents.agente_revisor import agente_revisor, nodo_herramientas_revisor
from app.agents.agente_documentador import agente_documentador, nodo_herramientas_documentador


def summarize_messages(state: ProjectState) -> Command:
    """
    Resume los mensajes antiguos para mantener el contexto manejable.
    Basado en las mejores prácticas de LangGraph.
    """
    messages = state["messages"]
    summary = state.get("summary", "")
    proximo_paso = state.get("proximo_paso", "agente_planificador")
    
    # Solo resumimos si hay más de 6 mensajes
    if len(messages) <= 6:
        return Command(goto=proximo_paso)

    from app.settings.settings import get_llm
    llm = get_llm(temperature=0)
    
    if summary:
        summary_message = (
            f"Este es el resumen de la conversación hasta ahora: {summary}\n\n"
            "Resume los nuevos mensajes arriba incorporándolos al resumen existente."
        )
    else:
        summary_message = "Crea un resumen de la siguiente conversación:"

    response = llm.invoke(messages + [HumanMessage(content=summary_message)])
    
    # Marcamos los mensajes antiguos para ser eliminados (excepto los últimos 2 para contexto inmediato)
    delete_messages = [RemoveMessage(id=m.id) for m in messages[:-2] if m.id is not None]
    
    return Command(
        update={
            "summary": response.content,
            "messages": delete_messages
        },
        goto=proximo_paso
    )

def crear_grafo():
    workflow = StateGraph(ProjectState)

    # (Cerebros)
    workflow.add_node("agente_planificador", agente_planificador)
    workflow.add_node("agente_codificador", agente_codificador)
    workflow.add_node("agente_codificador_silent", agente_codificador)
    workflow.add_node("agente_revisor", agente_revisor)
    workflow.add_node("agente_documentador", agente_documentador)
    workflow.add_node("summarize_messages", summarize_messages)

    # (Herramientas)
    workflow.add_node("nodo_herramientas_planificador", nodo_herramientas_planificador)
    workflow.add_node("nodo_herramientas_codificador", nodo_herramientas_codificador)
    workflow.add_node("nodo_herramientas_revisor", nodo_herramientas_revisor)
    workflow.add_node("nodo_herramientas_documentador", nodo_herramientas_documentador)

    # Punto de entrada
    workflow.add_edge(START, "agente_planificador")

    # Persistencia para cuando se reinicie o cierre el editor "memoria_agentes.db"
    ruta_raiz = Path(__file__).parent.parent
    ruta_db = ruta_raiz / "memoria_agentes.db"
    
    conn = sqlite3.connect(str(ruta_db), check_same_thread=False)
    memory = SqliteSaver(conn)

    # Compilamos con el checkpointer e interrupción antes del agente_codificador (human in the loop)
    return workflow.compile(checkpointer=memory, interrupt_before=["agente_codificador"])
