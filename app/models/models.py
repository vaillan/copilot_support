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
    # --- Mecanismo de regeneración de tests (anti-bucle) ---
    # Número de regeneraciones de tests disparadas en la tarea actual.
    test_regeneration_count: int = 0
    # Hashes SHA-256 conocidos de los archivos modificados (detección de cambios reales).
    test_regeneration_hashes: Optional[Dict[str, str]] = None
    # Timestamp (time.time()) de la última regeneración disparada (cooldown/debounce).
    test_regeneration_last_ts: float = 0.0
