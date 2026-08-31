"""
Punto de acceso único al registro de tareas del servidor MCP.

mcp_server.py NO debe acceder directamente a app.utils.task_registry: toda
obtención/consulta de tareas pasa por este módulo, garantizando que la obtención
proviene del MCP y que la persistencia es SQLite (mismo patrón que los
checkpointers de LangGraph), nunca JSON. ``task_store`` es el MISMO objeto que
``task_registry`` (alias), de modo que se cumple ``task_registry is task_store``.
"""

from app.utils.task_registry import ESTADOS_VALIDOS, TaskRegistry, task_registry as task_store

__all__ = ["task_store", "TaskRegistry", "ESTADOS_VALIDOS"]