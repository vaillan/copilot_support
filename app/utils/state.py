from langchain_core.messages import BaseMessage # type: ignore
from typing import TypedDict, Annotated, List
import operator

class GraphState(TypedDict):
    """
    Representa el estado de nuestro grafo de agentes.

    Atributos:
        messages: La lista de mensajes que componen la conversación.
        next_agent: El nombre del siguiente agente que el orquestador ha decidido ejecutar.
        search_results: Los resultados de la búsqueda por similitud.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    next_agent: str
    search_results: List[dict]