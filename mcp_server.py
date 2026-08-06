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
    """
    Envía mensajes de log y progreso en tiempo real a la interfaz de Zoo Code si hay Context.
    Pasa el parámetro 'message=mensaje' a 'report_progress' e incluye un mecanismo de respaldo
    por si el progressToken es None o no es provisto por la sesión, garantizando que Zoo Code
    muestre las notificaciones de progreso con texto descriptivo.
    """
    if ctx is None:
        return
    try:
        # Detectar si existe un progressToken válido en el contexto de la petición
        has_progress_token = False
        try:
            if (
                hasattr(ctx, "request_context")
                and ctx.request_context is not None
                and hasattr(ctx.request_context, "meta")
                and ctx.request_context.meta is not None
                and getattr(ctx.request_context.meta, "progressToken", None) is not None
            ):
                has_progress_token = True
        except Exception:
            has_progress_token = False

        progreso_val = progreso if progreso is not None else 0

        # Intentar reportar progreso estructurado pasando 'message=mensaje'
        if progreso is not None and hasattr(ctx, "report_progress"):
            try:
                res = ctx.report_progress(progreso_val, total=total, message=mensaje)
                if asyncio.iscoroutine(res):
                    await res
            except TypeError:
                try:
                    res = ctx.report_progress(progreso_val, total, mensaje)
                    if asyncio.iscoroutine(res):
                        await res
                except TypeError:
                    res = ctx.report_progress(progreso_val, total)
                    if asyncio.iscoroutine(res):
                        await res

        # Mecanismo de respaldo (Fallback)
        # Si progressToken es None o la sesión no lo provee, formateamos el mensaje
        # con el avance porcentual [XX%] para asegurar que Zoo Code reciba el texto.
        if progreso is not None and not has_progress_token:
            pct = int((progreso_val / total) * 100) if total > 0 else progreso_val
            mensaje_formateado = f"[{pct}%] {mensaje}"
        else:
            mensaje_formateado = mensaje

        if hasattr(ctx, "info"):
            res = ctx.info(mensaje_formateado)
            if asyncio.iscoroutine(res):
                await res

        if not has_progress_token:
            sys.stderr.write(f"[PROGRESO] {mensaje_formateado}\n")
            sys.stderr.flush()

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
            stdout_clean = res_stat.stdout.strip()
            return f"Archivos modificados/creados (git status):\n{stdout_clean}"
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
        msg_consultando = f"🔍 Consultando cambios para tarea '{tarea_id}' en '{directorio_proyecto}'..."
        await notificar_progreso(ctx, msg_consultando, 10, 100)
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
                    msg_resumen = f"📋 RESUMEN DE CAMBIOS (Tarea '{tarea_id}'):\n{codigo_escrito}"
                    partes.append(msg_resumen)
                else:
                    msg_sin_resumen = f"ℹ️ La tarea '{tarea_id}' aún no ha registrado un resumen de cambios."
                    partes.append(msg_sin_resumen)
                    
                if estado.next:
                    siguiente_nodo = estado.next[0]
                    msg_estado = f"📌 Estado actual del flujo: Pausado antes de '{siguiente_nodo}'"
                    partes.append(msg_estado)
                else:
                    partes.append("📌 Estado actual del flujo: Finalizado")
            except Exception as e:
                err_msg = str(e)
                msg_err = f"⚠️ No se pudo obtener el estado de la tarea '{tarea_id}': {err_msg}"
                partes.append(msg_err)

        if dir_a_consultar:
            diff_git = obtener_git_diff(dir_a_consultar)
            if diff_git:
                msg_diff = f"🔍 CAMBIOS DETALLADOS EN DISCO (Git Diff / Status en '{dir_a_consultar}'):\n{diff_git}"
                partes.append(msg_diff)
                
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
    auto_approve: bool = False,
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
        auto_approve: Si es True (o la variable MCP_AUTO_APPROVE=true), auto-aprueba todas las pausas (Pausa 1 y Pausa 2) sin requerir confirmación manual.
    """
    env_val_raw = os.environ.get("MCP_AUTO_APPROVE", "")
    env_val_clean = env_val_raw.strip().lower()
    env_auto_approve = env_val_clean in ("true", "1", "yes")
    effective_auto_approve = auto_approve or env_auto_approve

    # Si es una tarea nueva, generamos un ID único. Si estamos resumiendo, usamos el que nos pasa el LLM.
    if not tarea_id:
        if approve:
            return "Error: No puedes aprobar una tarea sin proporcionar el 'tarea_id' de la sesión pausada."
        uuid_hex = uuid.uuid4().hex[:8]
        tarea_id = f"task_{uuid_hex}"
        
    config = {"configurable": {"thread_id": tarea_id}, "recursion_limit": 100}

    msg_inicio = f"🚀 Iniciando procesamiento para tarea '{tarea_id}'..."
    await notificar_progreso(ctx, msg_inicio, 10, 100)

    timeout_seconds = int(os.environ.get("MCP_TASK_TIMEOUT_SECONDS", "300"))

    async def _ejecutar_logica() -> str:
        estado_actual = await agentes_app.aget_state(config) # type: ignore
        is_paused = len(estado_actual.next) > 0

        if is_paused:
            siguiente_nodo = estado_actual.next[0]
            if approve or effective_auto_approve:
                msg_reanudando = f"▶️ Reanudando tarea '{tarea_id}' (Aprobación confirmada para nodo '{siguiente_nodo}')..."
                await notificar_progreso(ctx, msg_reanudando, 50, 100)
                # Reanudamos la ejecución
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado_post = await agentes_app.aget_state(config) # type: ignore
                
                # Bucle para saltar las interrupciones causadas por el retorno de las herramientas
                tool_loop_count = 0
                while estado_post.next and estado_post.next[0] in ["agente_codificador", "agente_revisor"] and tool_loop_count < 10:
                    msgs = estado_post.values.get("messages", []) if hasattr(estado_post, "values") else []
                    if msgs and getattr(msgs[-1], "type", None) == "tool":
                        tool_step = tool_loop_count + 1
                        msg_tool = f"⚙️ Procesando resultado de herramienta ({tool_step})..."
                        await notificar_progreso(ctx, msg_tool, 60, 100)
                        resultado = await agentes_app.ainvoke(None, config) # type: ignore
                        estado_post = await agentes_app.aget_state(config) # type: ignore
                        tool_loop_count += 1
                    else:
                        break
            else:
                msg_feedback = f"↩️ Procesando rechazo/feedback del usuario para nodo '{siguiente_nodo}'..."
                await notificar_progreso(ctx, msg_feedback, 30, 100)
                # RECHAZO DEL USUARIO: Regresamos con feedback y REINICIAMOS CONTADORES
                if siguiente_nodo == "agente_revisor":
                    msg_rechazo_cod = f"El usuario rechazó el código con este feedback: {instruccion}"
                    msg_rechazo_human = f"Rechazo de código: {instruccion}"
                    comando = Command(
                        goto="agente_codificador",
                        update={
                            "errores_terminal": msg_rechazo_cod,
                            "messages": [HumanMessage(content=msg_rechazo_human)],
                            "loop_counter": 0,
                            "revision_count": 0
                        }
                    )
                    resultado = await agentes_app.ainvoke(comando, config) # type: ignore
                    
                elif siguiente_nodo == "agente_codificador":
                    msg_rechazo_plan = f"El usuario rechazó el plan de acción: {instruccion}"
                    comando = Command(
                        goto="agente_planificador",
                        update={
                            "messages": [HumanMessage(content=msg_rechazo_plan)],
                            "loop_counter": 0 
                        }
                    )
                    resultado = await agentes_app.ainvoke(comando, config) # type: ignore
                else:
                    resultado = await agentes_app.ainvoke(None, config) # type: ignore
        else:
            instruccion_corta = instruccion[:50]
            msg_planificador = f"🏗️ Iniciando Agente Planificador (Arquitecto) para '{instruccion_corta}...'..."
            await notificar_progreso(ctx, msg_planificador, 20, 100)
            estado_inicial = {
                "instruccion_usuario": instruccion,
                "directorio_proyecto": directorio_proyecto,
                "messages": [HumanMessage(content=instruccion)],
                "revision_count": 0,
                "loop_counter": 0
            }
            resultado = await agentes_app.ainvoke(estado_inicial, config) # type: ignore

        estado = await agentes_app.aget_state(config) # type: ignore

        # Si auto-aprobación está habilitada, avanzamos automáticamente a través de cualquier pausa adicional
        if effective_auto_approve:
            auto_loop_count = 0
            max_auto_loops = 20
            while estado.next and auto_loop_count < max_auto_loops:
                siguiente_nodo = estado.next[0]
                msg_auto = f"⚡ Auto-aprobación activa: reanudando automáticamente en nodo '{siguiente_nodo}' (tarea '{tarea_id}')..."
                await notificar_progreso(
                    ctx,
                    msg_auto,
                    50,
                    100
                )
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado = await agentes_app.aget_state(config) # type: ignore

                tool_loop_count = 0
                while estado.next and estado.next[0] in ["agente_codificador", "agente_revisor"] and tool_loop_count < 10:
                    msgs = estado.values.get("messages", []) if hasattr(estado, "values") else []
                    if msgs and getattr(msgs[-1], "type", None) == "tool":
                        tool_step = tool_loop_count + 1
                        msg_tool = f"⚙️ Procesando resultado de herramienta ({tool_step})..."
                        await notificar_progreso(ctx, msg_tool, 60, 100)
                        resultado = await agentes_app.ainvoke(None, config) # type: ignore
                        estado = await agentes_app.aget_state(config) # type: ignore
                        tool_loop_count += 1
                    else:
                        break
                auto_loop_count += 1

        if estado.next:
            siguiente_nodo = estado.next[0]
            
            if siguiente_nodo == "agente_codificador":
                plan = estado.values.get("plan_de_accion", "Plan generado.")
                msg_pausa1 = f"⏸️ PAUSA 1: Plan de acción listo. Esperando revisión del usuario (tarea '{tarea_id}')."
                await notificar_progreso(ctx, msg_pausa1, 40, 100)
                return (
                    f"================================================================================\n"
                    f"🛑 INTERRUPCIÓN: PAUSA DE APROBACIÓN HUMANA REQUERIDA (PAUSA 1)\n"
                    f"================================================================================\n\n"
                    f"⏸️ PAUSA 1: El Arquitecto propone este plan:\n\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"📋 PLAN DE ACCIÓN PROPUESTO:\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"{plan}\n"
                    f"--------------------------------------------------------------------------------\n\n"
                    f"🆔 ID de Tarea: `{tarea_id}`\n\n"
                    f"⚠️ INSTRUCCIONES CRÍTICAS PARA EL CLIENTE MCP (ZOO CODE / ASISTENTE):\n"
                    f"1. DETÉN la ejecución inmediatamente. NO llames a herramientas automáticamente.\n"
                    f"2. Presenta el plan de acción anterior al usuario y solicita su aprobación explícita.\n"
                    f"3. Espera a que el usuario confirme antes de realizar cualquier otra acción.\n\n"
                    f"👉 GUÍA DE REANUDACIÓN O FEEDBACK PARA EL USUARIO:\n"
                    f"• SI APRUEBAS EL PLAN:\n"
                    f"  Llama a la herramienta con: approve=True, tarea_id='{tarea_id}', directorio_proyecto='{directorio_proyecto}'\n\n"
                    f"• SI RECHAZAS O SOLICITAS CAMBIOS EN EL PLAN:\n"
                    f"  Llama a la herramienta con: approve=False, tarea_id='{tarea_id}', instruccion='<tu feedback>', directorio_proyecto='{directorio_proyecto}'\n"
                    f"================================================================================"
                )
                
            elif siguiente_nodo == "agente_revisor":
                codigo_escrito = estado.values.get("codigo_escrito", "No se registró un resumen de cambios.")
                diff_git = obtener_git_diff(directorio_proyecto)
                msg_cambios = f"⏸️ PAUSA 2: Código escrito. Esperando aprobación antes de pruebas QA (tarea '{tarea_id}')."
                if diff_git:
                    msg_cambios += f"\n\n🔍 Cambios detectados en disco:\n{diff_git}"
                await notificar_progreso(ctx, msg_cambios, 70, 100)
                bloque_git = f"\n\n🔍 CAMBIOS EN DISCO (Git Diff / Status):\n{diff_git}" if diff_git else ""
                return (
                    f"================================================================================\n"
                    f"🛑 INTERRUPCIÓN: PAUSA DE APROBACIÓN HUMANA REQUERIDA (PAUSA 2)\n"
                    f"================================================================================\n\n"
                    f"⏸️ PAUSA 2 (REVISIÓN DE CÓDIGO): El Programador ha terminado de escribir los archivos.\n\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"📝 CAMBIOS REALIZADOS:\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"{codigo_escrito}{bloque_git}\n"
                    f"--------------------------------------------------------------------------------\n\n"
                    f"🆔 ID de Tarea: `{tarea_id}`\n\n"
                    f"⚠️ INSTRUCCIONES CRÍTICAS PARA EL CLIENTE MCP (ZOO CODE / ASISTENTE):\n"
                    f"1. DETÉN la ejecución inmediatamente. NO llames a herramientas automáticamente.\n"
                    f"2. Muestra los cambios realizados al usuario y solicita su revisión y aprobación explícita.\n"
                    f"3. Espera la confirmación del usuario antes de proceder a la fase de pruebas QA.\n\n"
                    f"👉 GUÍA DE REANUDACIÓN O FEEDBACK PARA EL USUARIO:\n"
                    f"• SI APRUEBAS LOS CAMBIOS:\n"
                    f"  Llama a la herramienta con: approve=True, tarea_id='{tarea_id}', directorio_proyecto='{directorio_proyecto}'\n\n"
                    f"• SI SOLICITAS CORRECCIONES EN EL CÓDIGO:\n"
                    f"  Llama a la herramienta con: approve=False, tarea_id='{tarea_id}', instruccion='<tu feedback>', directorio_proyecto='{directorio_proyecto}'\n"
                    f"================================================================================"
                )

        # Si no hay 'next', el grafo llegó a END
        values = estado.values if hasattr(estado, "values") else {}
        codigo_escrito = values.get("codigo_escrito") or (resultado.get("codigo_escrito") if isinstance(resultado, dict) else "No se reportó código.")
        errores_qa = values.get("errores_terminal") or (resultado.get("errores_terminal") if isinstance(resultado, dict) else "Sin errores.")
        
        diff_git = obtener_git_diff(directorio_proyecto)
        msg_fin = f"✅ Tarea '{tarea_id}' completada exitosamente."
        if diff_git:
            diff_msg = f"\n\n🔍 Cambios en disco finales:\n{diff_git}"
            msg_fin += diff_msg
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
        err_msg = str(e)
        msg_err = f"🚨 El equipo de agentes falló con un error interno en tarea '{tarea_id}': {err_msg}"
        sys.stderr.write(f"{msg_err}\n")
        await notificar_progreso(ctx, msg_err, 100, 100)
        return msg_err


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except (KeyboardInterrupt, BrokenPipeError, ConnectionResetError):
        sys.exit(0)
    except Exception as e:
        err_fatal = str(e)
        sys.stderr.write(f"Error fatal en el servidor MCP: {err_fatal}\n")
        sys.exit(1)
