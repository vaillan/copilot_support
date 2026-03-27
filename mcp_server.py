import os
import sys

# Bloqueamos la impresión de cualquier cosa que no sea JSON
class MuteStderr:
    def write(self, x): pass
    def flush(self): pass

# Guardamos el original por si acaso, pero silenciamos stderr que es donde sale el banner rojo
sys.stderr = MuteStderr()

# Forzamos silencio en la librería
os.environ["FASTMCP_LOG_LEVEL"] = "CRITICAL"

from fastmcp import FastMCP
import hashlib
from langchain_core.messages import HumanMessage
from app.main import crear_grafo


# 1. Inicializamos el Servidor MCP
mcp = FastMCP("AIDevTeam")

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
    
    # Generamos un ID de hilo (thread_id) basado en el directorio del proyecto
    # Esto permite que cada proyecto tenga su propia memoria de sesión
    thread_id = hashlib.md5(directorio_proyecto.encode()).hexdigest()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    # Preparamos el estado inicial. 
    # Al pasar la instrucción en 'messages', LangGraph la añade al historial de la sesión.
    estado_inicial = {
        "instruccion_usuario": instruccion,
        "directorio_proyecto": directorio_proyecto,
        "messages": [HumanMessage(content=instruccion)]
    }
    
    try:
        # Ejecutamos el equipo de agentes con la configuración de memoria
        resultado = agentes_app.invoke(estado_inicial, config) # type: ignore
        
        # Extraemos el reporte final para devolvérselo al editor de código
        codigo_escrito = resultado.get("codigo_escrito", "No se reportó código.")
        errores_qa = resultado.get("errores_terminal", "Sin errores.")
        
        reporte_final = (
            f"Tarea completada por el equipo LangGraph.\n"
            f"ID de Sesión: {thread_id}\n"
            f"Resumen de cambios: {codigo_escrito}\n"
            f"Estado final de los tests (QA): {errores_qa}"
        )
        return reporte_final
        
    except Exception as e:
        return f" El equipo de agentes falló con un error interno: {str(e)}"

# 4. Punto de entrada para ejecutar el servidor
if __name__ == "__main__":
    # run() inicia el servidor escuchando por la terminal (stdio)
    mcp.run(transport="stdio")