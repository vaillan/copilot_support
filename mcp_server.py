from mcp.server.fastmcp import FastMCP
from app.main import crear_grafo

# 1. Inicializamos el Servidor MCP
mcp = FastMCP("EquipoAgentesLangGraph")

# 2. Compilamos el grafo una sola vez al iniciar el servidor
agentes_app = crear_grafo()

# 3. Exponemos nuestro Grafo como una Herramienta MCP usando el decorador @mcp.tool()
@mcp.tool()
def delegar_tarea_a_equipo_ia(instruccion: str, directorio_proyecto: str) -> str:
    """
    ÚSA ESTA HERRAMIENTA PARA DELEGAR TAREAS COMPLEJAS DE PROGRAMACIÓN.
    Esta herramienta invoca a un equipo de 3 agentes autónomos (Arquitecto, Programador y QA).
    Ellos planearán, escribirán el código y ejecutarán los tests automáticamente.
    
    Args:
        instruccion: Lo que el usuario quiere construir (ej. "Crea un sistema de login").
        directorio_proyecto: La ruta absoluta de la carpeta actual del proyecto.
    """
    
    # Preparamos el estado inicial que nuestro LangGraph espera
    estado_inicial = {
        "instruccion_usuario": instruccion,
        "directorio_proyecto": directorio_proyecto,
        "messages":[]
    }
    
    try:
        # Ejecutamos el equipo de agentes
        # Usamos invoke() en lugar de stream() para que el servidor espere a que terminen
        resultado = agentes_app.invoke(estado_inicial, {"recursion_limit": 50}) # type: ignore
        
        # Extraemos el reporte final para devolvérselo al editor de código
        codigo_escrito = resultado.get("codigo_escrito", "No se reportó código.")
        errores_qa = resultado.get("errores_terminal", "Sin errores.")
        
        reporte_final = (
            f"Tarea completada por el equipo LangGraph.\n"
            f"Resumen de cambios: {codigo_escrito}\n"
            f"Estado final de los tests (QA): {errores_qa}"
        )
        return reporte_final
        
    except Exception as e:
        return f" El equipo de agentes falló con un error interno: {str(e)}"

# 4. Punto de entrada para ejecutar el servidor
if __name__ == "__main__":
    # run() inicia el servidor escuchando por la terminal (stdio)
    mcp.run()