from langgraph.graph import MessagesState

class ProjectState(MessagesState):
    """
    Representa el estado global del proyecto dentro del grafo de agentes.
    
    Hereda de MessagesState para mantener un historial de mensajes y añade
    campos específicos para coordinar el flujo entre los agentes planificador,
    codificador y revisor.
    """
    # 'messages' ya está incluido automáticamente por MessagesState
    instruccion_usuario: str
    directorio_proyecto: str  # 🌟 Agregado para que funcione en cualquier editor
    plan_de_accion: dict      # El planificador escribirá aquí
    codigo_escrito: str       # El codificador escribirá aquí
    errores_terminal: str     # El revisor (QA) escribirá aquí
