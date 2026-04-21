from langgraph.graph import MessagesState
from typing import Optional

class ProjectState(MessagesState):
    """
    Representa el estado global del proyecto dentro del grafo de agentes.
    
    Hereda de MessagesState para mantener un historial de mensajes y añade
    campos específicos para coordinar el flujo entre los agentes planificador,
    codificador y revisor.
    """
    instruccion_usuario: str
    directorio_proyecto: str
    plan_de_accion: Optional[dict]
    codigo_escrito: Optional[str]
    errores_terminal: Optional[str]
    revision_count: int
    loop_counter: int
