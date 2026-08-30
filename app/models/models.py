from typing import Optional, Any, Dict
from langgraph.graph import MessagesState


class ProjectState(MessagesState):
    """
    Representa el estado global del proyecto dentro del grafo de agentes.
    
    Hereda de MessagesState para mantener un historial de mensajes y añade
    campos específicos para coordinar el flujo entre los agentes planificador,
    codificador y revisor.
    """
    instruccion_usuario: str
    directorio_proyecto: str
    plan_de_accion: Optional[Dict[str, Any]]
    codigo_escrito: Optional[str]
    errores_terminal: Optional[str]
    revision_count: int
    loop_counter: int
    project_index: Optional[Dict[str, Any]] = None
    analisis_final: Optional[str] = None
    # Motivo de la próxima pausa antes de agente_codificador:
    #   - "plan_nuevo": el planificador entregó un plan y espera aprobación (PAUSA 1 legítima).
    #   - "retrabajo_qa": el revisor rechazó el código y el flujo regresa al codificador
    #     (re-trabajo interno; NO debe renderizarse como formulario de plan).
    #   - None: sin semántica especial (comportamiento por defecto = PAUSA 1).
    pausa_motivo: Optional[str] = None
