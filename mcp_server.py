import os
import sys

class MuteStderr:
    def write(self, x): pass
    def flush(self): pass

sys.stderr = MuteStderr()

os.environ["FASTMCP_LOG_LEVEL"] = "CRITICAL"

from fastmcp import FastMCP
import hashlib
from langchain_core.messages import HumanMessage
from app.main import crear_grafo



mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

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
    
    thread_id = hashlib.md5(directorio_proyecto.encode()).hexdigest()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    estado_inicial = {
        "instruccion_usuario": instruccion,
        "directorio_proyecto": directorio_proyecto,
        "messages": [HumanMessage(content=instruccion)]
    }
    
    try:
        resultado = agentes_app.invoke(estado_inicial, config) # type: ignore
        
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


if __name__ == "__main__":
    mcp.run(transport="stdio")