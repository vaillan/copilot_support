from mcp.server.fastmcp import FastMCP
from app.main import crear_grafo

# Servidor MCP
mcp = FastMCP("AIDevTeam")

# Grafo
agentes_app = crear_grafo()

# Grafo como una Herramienta MCP usando el decorador @mcp.tool()
@mcp.tool()
def delegar_tarea_a_equipo_ia(instruccion: str, directorio_proyecto: str, thread_id: str = "1", approve: bool = False) -> str:
    """
    ÚSA ESTA HERRAMIENTA PARA DELEGAR TAREAS COMPLEJAS DE PROGRAMACIÓN Y DOCUMENTACIÓN.
    Esta herramienta invoca a un equipo de 4 agentes autónomos (Arquitecto, Programador, QA y Documentador).
    Ellos planearán, escribirán el código, ejecutarán los tests y documentarán los cambios automáticamente.
    
    El proceso se detendrá para que lo apruebes después de la fase de planificación.
    Para continuar después de la pausa, llama a esta misma herramienta con approve=True y el mismo thread_id.
    
    Args:
        instruccion: Lo que el usuario quiere construir (ej. "Crea un sistema de login").
        directorio_proyecto: La ruta absoluta de la carpeta actual del proyecto.
        thread_id: ID del hilo de conversación para la persistencia de la sesión (ej. "1").
        approve: Booleano para aprobar el plan y continuar con la codificación si el proceso está pausado.
    """
    
    config = {"configurable": {"thread_id": thread_id}}
    
    if approve:
        try:
            # Continuar desde la interrupción (human in the loop)
            resultado = agentes_app.invoke(None, config) # type: ignore
        except Exception as e:
            return f" El equipo de agentes falló al continuar con un error interno: {str(e)}"
    else:
        # Preparamos el estado inicial que nuestro LangGraph espera
        estado_inicial = {
            "instruccion_usuario": instruccion,
            "directorio_proyecto": directorio_proyecto,
            "messages":[]
        }
        
        try:
            # Ejecutamos el equipo de agentes
            # Usamos invoke() en lugar de stream() para que el servidor espere a que terminen
            resultado = agentes_app.invoke(estado_inicial, config) # type: ignore
        except Exception as e:
            return f" El equipo de agentes falló con un error interno: {str(e)}"
    
    # Comprobar si el grafo fue interrumpido
    estado = agentes_app.get_state(config) # type: ignore
    if estado.next:
        # Extraer el plan de los valores de estado actual si está disponible
        plan_propuesto = estado.values.get("plan_de_accion", "No se generó un plan.")
        return f"⏸️ El proceso está PAUSADO esperando aprobación del plan (Human in the loop).\n\nPLAN PROPUESTO:\n{plan_propuesto}\n\nPara aprobar y continuar, llama a esta herramienta con approve=True y el mismo thread_id."

    # Extraemos el reporte final para devolvérselo al editor de código
    codigo_escrito = resultado.get("codigo_escrito", "No se reportó código.")
    errores_qa = resultado.get("errores_terminal", "Sin errores.")
    
    reporte_final = (
        f"Tarea completada por el equipo AI DevTeam.\n"
        f"Resumen de cambios: {codigo_escrito}\n"
        f"Estado final de los tests (QA): {errores_qa}"
    )
    return reporte_final

# Ejecución del servidor
if __name__ == "__main__":
    mcp.run()