from langgraph.graph import MessagesState

class ProjectState(MessagesState):
    # 'messages' ya está incluido automáticamente por MessagesState
    instruccion_usuario: str
    directorio_proyecto: str  # 🌟 Agregado para que funcione en cualquier editor
    plan_de_accion: dict      # El planificador escribirá aquí
    codigo_escrito: str       # El codificador escribirá aquí
    errores_terminal: str     # El revisor (QA) escribirá aquí
    summary: str              # Para almacenar el resumen del historial
    proximo_paso: str         # Para saber a qué agente regresar tras resumir
