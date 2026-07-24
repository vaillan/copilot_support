import os
import sys
import subprocess
import asyncio
import uuid
import hashlib
from typing import Optional
from contextlib import redirect_stdout

class MuteStderr:
    def write(self, x): pass
    def flush(self): pass


os.environ["FASTMCP_LOG_LEVEL"] = "INFO"

from fastmcp import FastMCP, Context
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from app.main import crear_grafo


mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

async def notificar_progreso(ctx: Optional[Context], mensaje: str, progreso: Optional[int] = None, total: int = 100):
    """Envía mensajes de log y progreso en tiempo real a la interfaz de Zoo Code si hay Context."""
    if ctx is None:
        return
    try:
        if hasattr(ctx, "info"):
            res = ctx.info(mensaje)
            if asyncio.iscoroutine(res):
                await res
        if progreso is not None and hasattr(ctx, "report_progress"):
            res = ctx.report_progress(progreso, total)
            if asyncio.iscoroutine(res):
                await res
    except BaseException:
        pass


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
            timeout=5,
            stdin=subprocess.DEVNULL
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
            timeout=5,
            stdin=subprocess.DEVNULL
        )
        if res_stat.returncode == 0 and res_stat.stdout.strip():
            return f"Archivos modificados/creados (git status):\n{res_stat.stdout.strip()}"
    except Exception:
        pass
    return ""


async def visualizar_cambios(
    tarea_id: str = "",
    directorio_proyecto: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Función auxiliar interna para consultar el estado actual de una tarea o los cambios en disco.
    Nota: Ya no está expuesta como herramienta MCP para los agentes LLM.
    """
    with redirect_stdout(sys.stderr):
        await notificar_progreso(ctx, f"🔍 Consultando cambios para tarea '{tarea_id}' en '{directorio_proyecto}'...", 10, 100)
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
            await notificar_progreso(ctx, "⚠️ No se encontraron cambios para los parámetros proporcionados.", 100, 100)
            return "No se proporcionó un 'tarea_id' válido ni un 'directorio_proyecto' con cambios detectables."
            
        await notificar_progreso(ctx, "✅ Visualización de cambios completada.", 100, 100)
        return "\n\n".join(partes)


@mcp.tool()
async def delegar_tarea_a_equipo_ia(
    instruccion: str, 
    directorio_proyecto: str, 
    approve: bool = False,
    tarea_id: str = "",
    ctx: Optional[Context] = None
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

    await notificar_progreso(ctx, f"🚀 Iniciando procesamiento para tarea '{tarea_id}'...", 10, 100)

    timeout_seconds = int(os.environ.get("MCP_TASK_TIMEOUT_SECONDS", "300"))

    async def _ejecutar_logica() -> str:
        estado_actual = await agentes_app.aget_state(config) # type: ignore
        is_paused = len(estado_actual.next) > 0

        if is_paused:
            siguiente_nodo = estado_actual.next[0]
            if approve:
                await notificar_progreso(ctx, f"▶️ Reanudando tarea '{tarea_id}' (Aprobación confirmada para nodo '{siguiente_nodo}')...", 50, 100)
                # Reanudamos la ejecución
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado_post = await agentes_app.aget_state(config) # type: ignore
                
                # Bucle para saltar las interrupciones causadas por el retorno de las herramientas
                tool_loop_count = 0
                while estado_post.next and estado_post.next[0] in ["agente_codificador", "agente_revisor"] and tool_loop_count < 10:
                    msgs = estado_post.values.get("messages", [])
                    if msgs and msgs[-1].type == "tool":
                        await notificar_progreso(ctx, f"⚙️ Procesando resultado de herramienta ({tool_loop_count + 1})...", 60, 100)
                        resultado = await agentes_app.ainvoke(None, config) # type: ignore
                        estado_post = await agentes_app.aget_state(config) # type: ignore
                        tool_loop_count += 1
                    else:
                        break
            else:
                await notificar_progreso(ctx, f"↩️ Procesando rechazo/feedback del usuario para nodo '{siguiente_nodo}'...", 30, 100)
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
            await notificar_progreso(ctx, f"🏗️ Iniciando Agente Planificador (Arquitecto) para '{instruccion[:50]}...'...", 20, 100)
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
                await notificar_progreso(ctx, f"⏸️ PAUSA 1: Plan de acción listo. Esperando revisión del usuario (tarea '{tarea_id}').", 40, 100)
                return (
                    f"⏸️ PAUSA 1: El Arquitecto propone este plan:\n{plan}\n\n"
                    f"Por favor, revisa el plan. Si estás de acuerdo, llama a esta herramienta con:\n"
                    f"- approve=True\n"
                    f"- tarea_id='{tarea_id}'\n"
                    f"Si no estás de acuerdo, pon approve=False y escribe tus cambios en 'instruccion'."
                )
                
            elif siguiente_nodo == "agente_revisor":
                codigo_escrito = estado.values.get("codigo_escrito", "No se registró un resumen de cambios.")
                diff_git = obtener_git_diff(directorio_proyecto)
                msg_cambios = f"⏸️ PAUSA 2: Código escrito. Esperando aprobación antes de pruebas QA (tarea '{tarea_id}')."
                if diff_git:
                    msg_cambios += f"\n\n🔍 Cambios detectados en disco:\n{diff_git}"
                await notificar_progreso(ctx, msg_cambios, 70, 100)
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
        
        diff_git = obtener_git_diff(directorio_proyecto)
        msg_fin = f"✅ Tarea '{tarea_id}' completada exitosamente."
        if diff_git:
            msg_fin += f"\n\n🔍 Cambios en disco finales:\n{diff_git}"
        await notificar_progreso(ctx, msg_fin, 100, 100)
        reporte_final = (
            f"✅ Tarea completada exitosamente por el equipo LangGraph.\n"
            f"ID de Tarea: {tarea_id}\n"
            f"Resumen de cambios: {codigo_escrito}\n"
            f"Estado final de los tests (QA): {errores_qa}"
        )
        return reporte_final

    try:
        with redirect_stdout(sys.stderr):
            return await asyncio.wait_for(_ejecutar_logica(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        msg_timeout = f"🚨 Timeout: La tarea '{tarea_id}' excedió el límite máximo de ejecución ({timeout_seconds}s)."
        await notificar_progreso(ctx, msg_timeout, 100, 100)
        return f"{msg_timeout} Por favor, reintenta dividiendo la instrucción en pasos más específicos o verifica el estado de la tarea con tarea_id='{tarea_id}'."
    except BaseException as e:
        msg_err = f"🚨 El equipo de agentes falló con un error interno en tarea '{tarea_id}': {str(e)}"
        sys.stderr.write(f"{msg_err}\n")
        await notificar_progreso(ctx, msg_err, 100, 100)
        return msg_err


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except (KeyboardInterrupt, BrokenPipeError, ConnectionResetError):
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Error fatal en el servidor MCP: {e}\n")
        sys.exit(1)
