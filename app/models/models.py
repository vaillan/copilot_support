from typing import Optional, Any, Dict, Annotated
from langgraph.graph import MessagesState


def _ultimo_valor(a: int, b: int) -> int:
    """
    Reducer de LangGraph para campos contadores.

    Ante múltiples actualizaciones concurrentes al MISMO key dentro de un
    superstep (p. ej. cuando mcp_server.py reanuda el grafo con ainvoke(None)
    en bucles y varios nodos actualizan loop_counter/revision_count a la vez),
    se conserva el ÚLTIMO valor recibido.

    Sin este reducer, LangGraph lanza el error:
    "At key 'loop_counter': Can receive only one value per step.
     Use an Annotated key to handle multiple values."
    (INVALID_CONCURRENT_GRAPH_UPDATE)
    """
    return b


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
    # Reducers Annotated: permiten múltiples actualizaciones concurrentes al
    # mismo key en un superstep sin lanzar INVALID_CONCURRENT_GRAPH_UPDATE.
    revision_count: Annotated[int, _ultimo_valor] = 0 # pyright: ignore[reportGeneralTypeIssues]
    loop_counter: Annotated[int, _ultimo_valor] = 0 # pyright: ignore[reportGeneralTypeIssues]
    project_index: Optional[Dict[str, Any]] = None # pyright: ignore[reportGeneralTypeIssues]
    analisis_final: Optional[str] = None # pyright: ignore[reportGeneralTypeIssues]
    solo_analisis: Optional[bool] = None # pyright: ignore[reportGeneralTypeIssues]
