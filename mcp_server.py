import os
import sys
import subprocess

class MuteStderr:
    def write(self, x): pass
    def flush(self): pass


os.environ["FASTMCP_LOG_LEVEL"] = "INFO"

from fastmcp import FastMCP
import hashlib
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from app.main import crear_grafo
import uuid


mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

def obtener_git_diff(directorio: str) -> str:
    """Intenta obtener el diff de git o los archivos modificados en el directorio especificado."""
    if not directorio or not os.path.exists(directorio):
        return ""
    try:
        res = subprocess.run(
            ["git", "diff"], 
            cwd=directorio, 
            capture_output=True, 
            text=True, 
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
            
        res_stat = subprocess.run(
            ["git", "status", "-s"], 
            cwd=directorio, 
            capture_output=True, 
            text=True, 
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if res_stat.returncode == 0 and res_stat.stdout.strip():
            return f"Archivos modificados/creados (git status):\n{res_stat.stdout.strip()}"
    except Exception:
        pass
    return ""


@mcp.tool()
async def visualizar_cambios(
    tarea_id: str = "",
    directorio_proyecto: str = ""
) -> str:
    """
    Visualiza los cambios que se van realizando en el proyecto o el resumen de cambios de una tarea específica.
    
    Args:
        tarea_id: ID de la tarea para consultar el resumen de cambios registrado por los agentes.
        directorio_proyecto: Ruta de la carpeta del proyecto para consultar diffs/archivos modificados.
    """
    partes = []
    
    dir_a_consultar = directorio_proyecto
    
    if tarea_id:
        config = {"configurable": {"thread_id": tarea_id}}
        try:
            estado = await agentes_app.aget_state(config) # type: ignore
            values = estado.values if hasattr(estado, "values") else {}
            
            if not dir_a_consultar:
                dir_a_consultar = values.get("directorio_proyecto", "")
                
            codigo_escrito = values.get("codigo_escrito")
            if codigo_escrito:
                partes.append(f"📋 RESUMEN DE CAMBIOS (Tarea '{tarea_id}'):\n{codigo_escrito}")
            else:
                partes.append(f"ℹ️ La tarea '{tarea_id}' aún no ha registrado un resumen de cambios.")
                
            if estado.next:
                partes.append(f"📌 Estado actual del flujo: Pausado antes de '{estado.next[0]}'")
            else:
                partes.append("📌 Estado actual del flujo: Finalizado")
        except Exception as e:
            partes.append(f"⚠️ No se pudo obtener el estado de la tarea '{tarea_id}': {str(e)}")

    if dir_a_consultar:
        diff_git = obtener_git_diff(dir_a_consultar)
        if diff_git:
            partes.append(f"🔍 CAMBIOS DETALLADOS EN DISCO (Git Diff / Status en '{dir_a_consultar}'):\n{diff_git}")
            
    if not partes:
        return "No se proporcionó un 'tarea_id' válido ni un 'directorio_proyecto' con cambios detectables."
        
    return "\n\n".join(partes)


@mcp.tool()
async def delegar_tarea_a_equipo_ia(
    instruccion: str, 
    directorio_proyecto: str, 
    approve: bool = False,
    tarea_id: str = ""
) -> str:
    """
    ÚSA ESTA HERRAMIENTA PARA DELEGAR TAREAS COMPLEJAS DE PROGRAMACIÓN.
    Esta herramienta invoca a un equipo de 3 agentes autónomos (Arquitecto, Programador y QA).
    
    Args:
        instruccion: Lo que el usuario quiere construir, o el feedback si se está rechazando.
        directorio_proyecto: La ruta absoluta de la carpeta actual.
        approve: Booleano para aprobar y continuar si el proceso está pausado esperando revisión humana.
        tarea_id: OBLIGATORIO SI ESTÁS APROBANDO O RECHAZANDO UNA PAUSA. Déjalo vacío para iniciar una tarea nueva.
    """
    # Si es una tarea nueva, generamos un ID único. Si estamos resumiendo, usamos el que nos pasa el LLM.
    if not tarea_id:
        if approve:
            return "Error: No puedes aprobar una tarea sin proporcionar el 'tarea_id' de la sesión pausada."
        tarea_id = f"task_{uuid.uuid4().hex[:8]}"
        
    config = {"configurable": {"thread_id": tarea_id}, "recursion_limit": 100}

    try:
        estado_actual = await agentes_app.aget_state(config) # type: ignore
        is_paused = len(estado_actual.next) > 0

        if is_paused:
            siguiente_nodo = estado_actual.next[0]
            if approve:
                # Reanudamos la ejecución
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado_post = await agentes_app.aget_state(config) # type: ignore
                
                # Bucle para saltar las interrupciones causadas por el retorno de las herramientas
                while estado_post.next and estado_post.next[0] in ["agente_codificador", "agente_revisor"]:
                    msgs = estado_post.values.get("messages", [])
                    if msgs and msgs[-1].type == "tool":
                        resultado = await agentes_app.ainvoke(None, config) # type: ignore
                        estado_post = await agentes_app.aget_state(config) # type: ignore
                    else:
                        break
            else:
                # RECHAZO DEL USUARIO: Regresamos con feedback y REINICIAMOS CONTADORES
                if siguiente_nodo == "agente_revisor":
                    comando = Command(
                        goto="agente_codificador",
                        update={
                            "errores_terminal": f"El usuario rechazó el código con este feedback: {instruccion}",
                            "messages": [HumanMessage(content=f"Rechazo de código: {instruccion}")],
                            "loop_counter": 0,
                            "revision_count": 0
                        }
                    )
                    resultado = await agentes_app.ainvoke(comando, config) # type: ignore
                    
                elif siguiente_nodo == "agente_codificador":
                    comando = Command(
                        goto="agente_planificador",
                        update={
                            "messages": [HumanMessage(content=f"El usuario rechazó el plan de acción: {instruccion}")],
                            "loop_counter": 0 
                        }
                    )
                    resultado = await agentes_app.ainvoke(comando, config) # type: ignore
                else:
                    resultado = await agentes_app.ainvoke(None, config) # type: ignore
        else:
            estado_inicial = {
                "instruccion_usuario": instruccion,
                "directorio_proyecto": directorio_proyecto,
                "messages": [HumanMessage(content=instruccion)],
                "revision_count": 0,
                "loop_counter": 0
            }
            resultado = await agentes_app.ainvoke(estado_inicial, config) # type: ignore

        estado = await agentes_app.aget_state(config) # type: ignore
        
        if estado.next:
            siguiente_nodo = estado.next[0]
            
            if siguiente_nodo == "agente_codificador":
                plan = estado.values.get("plan_de_accion", "Plan generado.")
                return (
                    f"⏸️ PAUSA 1: El Arquitecto propone este plan:\n{plan}\n\n"
                    f"Por favor, revisa el plan. Si estás de acuerdo, llama a esta herramienta con:\n"
                    f"- approve=True\n"
                    f"- tarea_id='{tarea_id}'\n"
                    f"Si no estás de acuerdo, pon approve=False y escribe tus cambios en 'instruccion'."
                )
                
            elif siguiente_nodo == "agente_revisor":
                codigo_escrito = estado.values.get("codigo_escrito", "No se registró un resumen de cambios.")
                return (
                    f"⏸️ PAUSA 2 (REVISIÓN DE CÓDIGO): El Programador ha terminado de escribir los archivos.\n\n"
                    f"📝 CAMBIOS REALIZADOS:\n{codigo_escrito}\n\n"
                    f"👀 ACCIÓN REQUERIDA:\n"
                    f"1. Revisa los cambios en el proyecto.\n"
                    f"2. Si el código es correcto, llama a esta herramienta con approve=True y tarea_id='{tarea_id}' para que el QA ejecute las pruebas.\n"
                    f"3. Si requiere cambios, pon approve=False, tarea_id='{tarea_id}' e incluye en la instrucción lo que hay que corregir."
                )

        # Si no hay 'next', el grafo llegó a END
        values = estado.values if hasattr(estado, "values") else {}
        codigo_escrito = values.get("codigo_escrito") or (resultado.get("codigo_escrito") if isinstance(resultado, dict) else "No se reportó código.")
        errores_qa = values.get("errores_terminal") or (resultado.get("errores_terminal") if isinstance(resultado, dict) else "Sin errores.")
        
        reporte_final = (
            f"✅ Tarea completada exitosamente por el equipo LangGraph.\n"
            f"ID de Tarea: {tarea_id}\n"
            f"Resumen de cambios: {codigo_escrito}\n"
            f"Estado final de los tests (QA): {errores_qa}"
        )
        return reporte_final
        
    except Exception as e:
        return f"🚨 El equipo de agentes falló con un error interno: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
