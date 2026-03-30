import os
import sys

class MuteStderr:
    def write(self, x): pass
    def flush(self): pass

# sys.stderr = MuteStderr()

os.environ["FASTMCP_LOG_LEVEL"] = "INFO"

from fastmcp import FastMCP
import hashlib
from langchain_core.messages import HumanMessage
from app.main import crear_grafo



mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

@mcp.tool()
async def delegar_tarea_a_equipo_ia(instruccion: str, directorio_proyecto: str, approve: bool = False) -> str:
    """
    ÚSA ESTA HERRAMIENTA PARA DELEGAR TAREAS COMPLEJAS DE PROGRAMACIÓN.
    Esta herramienta invoca a un equipo de 3 agentes autónomos (Arquitecto, Programador y QA).
    
    Args:
        instruccion: Lo que el usuario quiere construir.
        directorio_proyecto: La ruta absoluta de la carpeta actual.
        approve: Booleano para aprobar y continuar si el proceso está pausado esperando revisión humana.
    """
    
    # Generamos un ID de sesión único por proyecto
    thread_id = hashlib.md5(directorio_proyecto.encode()).hexdigest()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    try:
        if approve:
            # Si el usuario aprobó visualmente, reanudamos el grafo desde donde se quedó
            resultado = await agentes_app.ainvoke(None, config) # type: ignore
        else:
            # Si es una tarea nueva, iniciamos desde cero
            estado_inicial = {
                "instruccion_usuario": instruccion,
                "directorio_proyecto": directorio_proyecto,
                "messages":[HumanMessage(content=instruccion)]
            }
            resultado = await agentes_app.ainvoke(estado_inicial, config) # type: ignore

        estado = await agentes_app.aget_state(config) # type: ignore
        
        if estado.next:
            siguiente_nodo = estado.next[0]
            
            if siguiente_nodo == "agente_codificador":
                plan = estado.values.get("plan_de_accion", "Plan generado.")
                return f"⏸️ PAUSA 1: El Arquitecto propone este plan:\n{plan}\n\nPor favor, revisa el plan y, si estás de acuerdo, llama a esta herramienta con approve=True para proceder con la implementación."
                
            elif siguiente_nodo == "agente_revisor":
                return (
                    f"⏸️ PAUSA 2 (REVISIÓN DE CÓDIGO): El Programador ha terminado de escribir los archivos en el disco duro.\n\n"
                    f"👀 ACCIÓN REQUERIDA:\n"
                    f"1. Revisa los cambios realizados en el sistema de archivos (puedes usar 'git diff' o tu explorador de archivos preferido).\n"
                    f"2. Si el código es correcto, llama a esta herramienta con approve=True para que el QA ejecute las pruebas.\n"
                    f"3. Si el código requiere cambios, descarta las modificaciones y solicita al equipo que realice las correcciones necesarias."
                )

        codigo_escrito = resultado.get("codigo_escrito", "No se reportó código.")
        errores_qa = resultado.get("errores_terminal", "Sin errores.")
        
        reporte_final = (
            f"✅ Tarea completada por el equipo LangGraph.\n"
            f"ID de Sesión: {thread_id}\n"
            f"Resumen de cambios: {codigo_escrito}\n"
            f"Estado final de los tests (QA): {errores_qa}"
        )
        return reporte_final
        
    except Exception as e:
        return f"🚨 El equipo de agentes falló con un error interno: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
