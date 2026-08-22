import os
import sys
import subprocess
import asyncio
import uuid
import hashlib
from typing import Optional, Dict, Any, List

# Asegurar que el directorio del script esté en sys.path.
# Esto evita el error "MCP error -32000: Connection closed" cuando el cliente
# (Zoo Code / Cursor / CLI) lanza el proceso desde un directorio de trabajo
# distinto al del proyecto, lo que provocaría que los imports relativos
# (app.main, app.utils, etc.) fallaran y el proceso se cerrara abruptamente.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

os.environ["FASTMCP_LOG_LEVEL"] = "INFO"

from fastmcp import FastMCP, Context
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from app.main import crear_grafo
from app.utils.project_index import construir_indice
from app.utils.task_registry import task_registry
from app.settings.settings import Settings


mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

# Mapa de tareas activas: tarea_id -> asyncio.Task en curso (para cancelación).
tareas_activas: Dict[str, asyncio.Task] = {}

# Helpers extraídos a la capa modular app/mcp (refactor arquitectónico):
# - _log_stderr, _safe_await, notificar_progreso  -> app.mcp.progress
# - obtener_git_diff                              -> app.mcp.git_utils
# - generar_markdown_pausa, visualizar_cambios    -> app.mcp.reporting
# visualizar_cambios accede al grafo (agentes_app) mediante import perezoso
# de este módulo dentro de la función para evitar import circular.
from app.mcp.progress import _log_stderr, _safe_await, notificar_progreso
from app.mcp.git_utils import obtener_git_diff
from app.mcp.reporting import generar_markdown_pausa, visualizar_cambios


@mcp.tool()
async def delegar_tarea_a_equipo_ia(
    instruccion: str,
    directorio_proyecto: str,
    approve: bool = False,
    tarea_id: str = "",
    auto_approve: bool = False,
    solo_analisis: bool = False,
    ctx: Optional[Context] = None
) -> str:
    """
    ÚSA ESTA HERRAMIENTA PARA DELEGAR TAREAS COMPLEJAS DE PROGRAMACIÓN.
    Esta herramienta invoca a un equipo de 3 agentes autónomos (Arquitecto, Programador y QA).
    
    IMPORTANTE SOBRE PAUSAS Y REVISIONES (PAUSA 1 Y PAUSA 2):
    Cuando el grafo se pause en Pausa 1 (Plan del Arquitecto) o Pausa 2 (Revisión de Código), esta herramienta devolverá un reporte estructurado en Markdown. 
    EL ASISTENTE LLM DEL CLIENTE (ZOO CODE / COPILOT / CURSOR) DEBE DETENERSE INMEDIATAMENTE, mostrar el plan o el diff de código completo al usuario humano, y ESPERAR su confirmación explícita (Aprobar/Rechazar) en el chat. 
    EL ASISTENTE DE IA TIENE PROHIBIDO LLAMAR A ESTA HERRAMIENTA AUTOMÁTICAMENTE PARA APROBAR SIN LA ORDEN EXPRESA DEL USUARIO.
    
    Args:
        instruccion: Lo que el usuario quiere construir, o el feedback si se está rechazando.
        directorio_proyecto: La ruta absoluta de la carpeta actual.
        approve: Booleano para aprobar y continuar si el proceso está pausado esperando revisión humana.
        tarea_id: OBLIGATORIO SI ESTÁS APROBANDO O RECHAZANDO UNA PAUSA. Déjalo vacío para iniciar una tarea nueva.
        auto_approve: Si es True (o la variable MCP_AUTO_APPROVE=true), auto-aprueba todas las pausas (Pausa 1 y Pausa 2) sin requerir confirmación manual.
        solo_analisis: Si es True, fuerza el modo de ANÁLISIS PURO (reporte/arquitectura/documentación) sin generar ni modificar código: el Planificador produce el documento y el grafo termina en END, sin pasar por el Agente Codificador ni el Revisor, independientemente de la heurística de detección.
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

    # Registrar la tarea en el TaskRegistry (si no existe aún).
    try:
        if task_registry.get_task(tarea_id) is None:
            task_registry.register_task(
                tarea_id=tarea_id,
                thread_id=config["configurable"]["thread_id"],
                directorio_proyecto=directorio_proyecto,
                instruccion=instruccion,
                estado="running",
            )
    except Exception:
        pass

    # Notificación inicial
    await notificar_progreso(ctx, f"🚀 Iniciando procesamiento para tarea '{tarea_id}'...", 10, 100)
    _log_stderr(f"[MCP] Iniciando tarea '{tarea_id}' con auto_approve={effective_auto_approve}")

    timeout_seconds = int(os.environ.get("MCP_TASK_TIMEOUT_SECONDS", "300"))

    async def _ejecutar_logica() -> str:
        estado_actual = await agentes_app.aget_state(config) # type: ignore
        is_paused = len(estado_actual.next) > 0

        if is_paused:
            siguiente_nodo = estado_actual.next[0]
            if approve or effective_auto_approve:
                msg_reanudando = f"▶️ Reanudando tarea '{tarea_id}' (Aprobación confirmada para nodo '{siguiente_nodo}')..."
                await notificar_progreso(ctx, msg_reanudando, 50, 100)
                _log_stderr(f"[MCP] Reanudando tarea '{tarea_id}' en nodo '{siguiente_nodo}'")
                # Reanudamos la ejecución
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado_post = await agentes_app.aget_state(config) # type: ignore
                
                # Bucle para procesar herramientas del nodo actual sin saltar a la siguiente pausa humana
                tool_loop_count = 0
                while estado_post.next and estado_post.next[0] == siguiente_nodo and tool_loop_count < 20:
                    tool_step = tool_loop_count + 1
                    msg_tool = f"⚙️ Procesando herramientas en nodo '{siguiente_nodo}' ({tool_step})...."
                    await notificar_progreso(ctx, msg_tool, 60, 100)
                    resultado = await agentes_app.ainvoke(None, config) # type: ignore
                    estado_post = await agentes_app.aget_state(config) # type: ignore
                    tool_loop_count += 1
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
            _log_stderr(f"[MCP] Nueva tarea '{tarea_id}': iniciando Planificador")
            # Construir el índice del proyecto para optimizar tokens (si está habilitado)
            project_index = None
            try:
                settings_mcp = Settings()
                if getattr(settings_mcp, "PROJECT_INDEX_ENABLED", True):
                    project_index = construir_indice(directorio_proyecto)
            except Exception:
                project_index = None

            estado_inicial = {
                "instruccion_usuario": instruccion,
                "directorio_proyecto": directorio_proyecto,
                "project_index": project_index,
                "messages": [HumanMessage(content=instruccion)],
                "revision_count": 0,
                "loop_counter": 0,
                "solo_analisis": solo_analisis
            }
            resultado = await agentes_app.ainvoke(estado_inicial, config) # type: ignore

        estado = await agentes_app.aget_state(config) # type: ignore

        # Si auto-aprobación está habilitada, avanzamos automáticamente a través de cualquier pausa adicional
        auto_loop_count = 0
        max_auto_loops = 50
        while estado.next and effective_auto_approve and auto_loop_count < max_auto_loops:
            siguiente_nodo = estado.next[0]
            msg_auto = f"⚡ Auto-aprobación activa: reanudando automáticamente en nodo '{siguiente_nodo}' (tarea '{tarea_id}')..."
            await notificar_progreso(ctx, msg_auto, 50, 100)
            _log_stderr(f"[MCP] Auto-aprobación: avanzando a '{siguiente_nodo}' (loop {auto_loop_count})")
            resultado = await agentes_app.ainvoke(None, config) # type: ignore
            estado = await agentes_app.aget_state(config) # type: ignore
            auto_loop_count += 1

        if estado.next:
            siguiente_nodo = estado.next[0]
            
            if siguiente_nodo == "agente_codificador":
                plan = estado.values.get("plan_de_accion", {})
                if isinstance(plan, dict):
                    explicacion = plan.get("explicacion_arquitectura", "Plan de acción propuesto por el equipo de IA.")
                    pasos = plan.get("pasos", [])
                else:
                    explicacion = str(plan)
                    pasos = []
                
                markdown_pausa = generar_markdown_pausa(
                    tarea_id=tarea_id,
                    tipo_pausa="PAUSA_1",
                    titulo="Formulario de Aprobación de Plan de Acción",
                    explicacion=explicacion,
                    pasos=pasos,
                    directorio_proyecto=directorio_proyecto
                )
                msg_pausa1 = f"⏸️ PAUSA 1: Plan de acción listo. Esperando revisión del usuario (tarea '{tarea_id}').\n\n{markdown_pausa}"
                await notificar_progreso(ctx, msg_pausa1, 40, 100)
                _log_stderr(f"[MCP] PAUSA 1 - tarea '{tarea_id}' esperando aprobación de plan")
                try:
                    task_registry.update_status(tarea_id, "paused_planning", detalle=explicacion)
                except Exception:
                    pass
                return markdown_pausa
                
            elif siguiente_nodo == "agente_revisor":
                codigo_escrito = estado.values.get("codigo_escrito", "No se registró un resumen de cambios.")
                diff_git = obtener_git_diff(directorio_proyecto)
                markdown_pausa = generar_markdown_pausa(
                    tarea_id=tarea_id,
                    tipo_pausa="PAUSA_2",
                    titulo="Revisión de Código Desarrollado (Pausa 2)",
                    explicacion=codigo_escrito,
                    diff_git=diff_git,
                    directorio_proyecto=directorio_proyecto
                )
                msg_cambios = f"⏸️ PAUSA 2: Código escrito. Esperando aprobación antes de pruebas QA (tarea '{tarea_id}').\n\n{markdown_pausa}"
                await notificar_progreso(ctx, msg_cambios, 70, 100)
                _log_stderr(f"[MCP] PAUSA 2 - tarea '{tarea_id}' esperando aprobación de código")
                try:
                    task_registry.update_status(tarea_id, "paused_code", detalle=codigo_escrito)
                except Exception:
                    pass
                return markdown_pausa

        # Si no hay 'next', el grafo llegó a END
        values = estado.values if hasattr(estado, "values") else {}
        codigo_escrito = values.get("codigo_escrito") or (resultado.get("codigo_escrito") if isinstance(resultado, dict) else None)
        errores_qa = values.get("errores_terminal") or (resultado.get("errores_terminal") if isinstance(resultado, dict) else None)
        plan_de_accion = values.get("plan_de_accion") or (resultado.get("plan_de_accion") if isinstance(resultado, dict) else None)
        
        diff_git = obtener_git_diff(directorio_proyecto)
        
        # Si el grafo terminó en un análisis puro (sin programación), el estado
        # contiene 'analisis_final'. Se extrae del estado o del resultado para
        # generar un reporte de análisis dedicado en lugar del reporte de tarea
        # de programación (codigo_escrito/errores_qa).
        analisis_final = values.get("analisis_final") or (resultado.get("analisis_final") if isinstance(resultado, dict) else None)

        if analisis_final:
            reporte_final = f"✅ Análisis completado por el equipo LangGraph.\nID de Tarea: {tarea_id}\n\n📋 REPORTE DE ANÁLISIS:\n{analisis_final}"
            await notificar_progreso(ctx, f"✅ Análisis completado para tarea '{tarea_id}'.", 100, 100)
            _log_stderr(f"[MCP] Tarea '{tarea_id}' COMPLETADA (análisis)")
            try:
                task_registry.update_status(tarea_id, "completed", detalle="Análisis completado")
            except Exception:
                pass
            return reporte_final

        # P2/P7: Detección de terminación ANÓMALA: el grafo llegó a END sin
        # producir código ni análisis (p. ej. loop_counter agotado en el
        # Planificador o Codificador, o error interno). NO reportar como éxito.
        # Nota: se ignora 'plan_de_accion' porque el plan puede existir (PAUSA_1)
        # pero el Codificador no haber escrito nada (codigo_escrito=None).
        es_terminacion_anomala = not codigo_escrito and not errores_qa
        if es_terminacion_anomala:
            mensajes = values.get("messages", [])
            ultimo_error = ""
            for m in reversed(mensajes):
                contenido = str(getattr(m, "content", ""))
                if any(kw in contenido for kw in ("Error", "excedido", "límite", "Error:")):
                    ultimo_error = contenido
                    break
            msg_error_final = (
                f"⚠️ La tarea '{tarea_id}' terminó sin producir código ni análisis.\n"
                f"Posible causa: el Agente Planificador o Codificador agotó el límite de iteraciones o falló internamente.\n"
                f"Detalle: {ultimo_error or 'Sin detalle adicional en el historial.'}\n"
                f"Directorio: {directorio_proyecto}"
            )
            await notificar_progreso(ctx, msg_error_final, 100, 100)
            _log_stderr(f"[MCP] Tarea '{tarea_id}' TERMINÓ SIN ENTREGABLES")
            try:
                task_registry.update_status(tarea_id, "error", detalle=msg_error_final)
            except Exception:
                pass
            return msg_error_final

        msg_fin = f"✅ Tarea '{tarea_id}' completada exitosamente."
        if diff_git:
            diff_msg = f"\n\n🔍 Cambios en disco finales:\n{diff_git}"
            msg_fin += diff_msg
        else:
            msg_fin += "\n\n⚠️ ADVERTENCIA: No se detectaron cambios ni modificaciones en los archivos del disco (git diff / status está vacío)."
        await notificar_progreso(ctx, msg_fin, 100, 100)
        _log_stderr(f"[MCP] Tarea '{tarea_id}' COMPLETADA")
        try:
            task_registry.update_status(tarea_id, "completed", detalle=codigo_escrito or "Sin resumen de cambios")
        except Exception:
            pass

        reporte_final = (
            f"✅ Tarea completada exitosamente por el equipo LangGraph.\n"
            f"ID de Tarea: {tarea_id}\n"
            f"Resumen de cambios: {codigo_escrito or 'No se reportó código.'}\n"
            f"Estado final de los tests (QA): {errores_qa or 'Sin errores.'}"
        )
        if not diff_git:
            reporte_final += f"\n\n⚠️ ADVERTENCIA: La tarea finalizó pero git diff no muestra modificaciones en '{directorio_proyecto}'. Comprueba si el Agente Codificador omitió la escritura de archivos."
        return reporte_final

    # Registrar la asyncio.Task activa para permitir cancelación efectiva desde
    # cancelar_tarea(). P1: NO se usa asyncio.shield: si el timeout expira, la
    # tarea subyacente se CANCELA realmente para no dejar procesos en background
    # que bloqueen el event loop del servidor MCP (bug: el cliente cortaba a los
    # 30 min pero la tarea seguía corriendo y bloqueaba listar_tareas/consultar).
    tarea_activa = asyncio.create_task(_ejecutar_logica())
    tareas_activas[tarea_id] = tarea_activa
    try:
        return await asyncio.wait_for(tarea_activa, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        msg_timeout = f"🚨 Timeout: La tarea '{tarea_id}' excedió el límite máximo de ejecución ({timeout_seconds}s)."
        await notificar_progreso(ctx, msg_timeout, 100, 100)
        _log_stderr(f"[MCP] TIMEOUT tarea '{tarea_id}'")
        # Cancelar realmente la tarea subyacente para liberar el event loop.
        if not tarea_activa.done():
            tarea_activa.cancel()
            try:
                await asyncio.wait_for(tarea_activa, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        try:
            task_registry.update_status(tarea_id, "timeout", detalle=msg_timeout)
        except Exception:
            pass
        return f"{msg_timeout} Por favor, reintenta dividiendo la instrucción en pasos más específicos o verifica el estado de la tarea con tarea_id='{tarea_id}'."
    except BaseException as e:
        err_msg = str(e)
        msg_err = f"🚨 El equipo de agentes falló con un error interno en tarea '{tarea_id}': {err_msg}"
        _log_stderr(f"[MCP] ERROR tarea '{tarea_id}': {err_msg}")
        await notificar_progreso(ctx, msg_err, 100, 100)
        try:
            task_registry.update_status(tarea_id, "error", detalle=err_msg)
        except Exception:
            pass
        return msg_err
    finally:
        # Limpiar la tarea activa del registro de cancelación.
        tareas_activas.pop(tarea_id, None)


@mcp.tool()
async def consultar_estado_tarea(
    tarea_id: str,
    directorio_proyecto: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Consulta el estado actual de una tarea delegada al equipo de IA.

    Reutiliza la lógica de visualizar_cambios() para obtener el estado del grafo
    y el git diff, y además consulta el TaskRegistry para reportar el estado
    registrado (running/paused/completed/timeout/error).

    Args:
        tarea_id: Identificador de la tarea a consultar.
        directorio_proyecto: Ruta del proyecto (opcional, se infiere del grafo si se omite).
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        await notificar_progreso(ctx, f"🔍 Consultando estado de la tarea '{tarea_id}'...", 10, 100)

        partes = []

        # 1. Estado registrado en el TaskRegistry
        tarea = task_registry.get_task(tarea_id)
        if tarea is not None:
            estado_registrado = tarea.get("estado", "desconocido")
            partes.append(f"### 📌 Estado registrado de la tarea '{tarea_id}'")
            partes.append(f"- **Estado:** `{estado_registrado}`")
            partes.append(f"- **Directorio:** `{tarea.get('directorio_proyecto', '')}`")
            partes.append(f"- **Última actualización:** `{tarea.get('timestamp_actualizacion', '')}`")
            if tarea.get("detalle"):
                partes.append(f"- **Detalle:** {tarea.get('detalle')}")
            partes.append("")
        else:
            partes.append(f"ℹ️ La tarea '{tarea_id}' no está registrada en el TaskRegistry (puede que aún no se haya iniciado o que haya sido eliminada).")

        # 2. Estado del grafo y cambios en disco (reutiliza visualizar_cambios)
        try:
            estado_grafo = await visualizar_cambios(tarea_id=tarea_id, directorio_proyecto=directorio_proyecto, ctx=ctx)
            partes.append(estado_grafo)
        except Exception as e:
            partes.append(f"⚠️ No se pudo obtener el estado del grafo: {e}")

        await notificar_progreso(ctx, "✅ Consulta de estado completada.", 100, 100)
        return "\n\n".join(partes)
    except Exception as e:
        return f"⚠️ Error al consultar el estado de la tarea '{tarea_id}': {e}"


@mcp.tool()
async def listar_tareas(
    estado: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Lista las tareas registradas en el servidor MCP.

    Args:
        estado: Filtro opcional por estado (running, paused_planning, paused_code, completed, cancelled, timeout, error).
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        await notificar_progreso(ctx, "📋 Listando tareas registradas...", 10, 100)

        tareas = task_registry.list_tasks(estado=estado)

        if not tareas:
            msg = "ℹ️ No hay tareas registradas" + (f" con estado '{estado}'" if estado else "") + "."
            await notificar_progreso(ctx, msg, 100, 100)
            return msg

        lineas = ["### 📋 Tareas Registradas"]
        lineas.append("| tarea_id | estado | directorio_proyecto | última actualización |")
        lineas.append("|---|---|---|---|")
        for t in tareas:
            tid = str(t.get("tarea_id", "")).replace("|", "\\|")
            est = str(t.get("estado", "")).replace("|", "\\|")
            dirp = str(t.get("directorio_proyecto", "")).replace("|", "\\|")
            ts = str(t.get("timestamp_actualizacion", "")).replace("|", "\\|")
            lineas.append(f"| `{tid}` | `{est}` | `{dirp}` | `{ts}` |")
        lineas.append("")

        await notificar_progreso(ctx, f"✅ Se encontraron {len(tareas)} tareas.", 100, 100)
        return "\n".join(lineas)
    except Exception as e:
        return f"⚠️ Error al listar las tareas: {e}"


@mcp.tool()
async def cancelar_tarea(
    tarea_id: str,
    ctx: Optional[Context] = None
) -> str:
    """
    Cancela una tarea en curso registrada en el TaskRegistry.

    Marca la tarea como 'cancelled' e intenta cancelar la asyncio.Task activa
    asociada si está disponible.

    Args:
        tarea_id: Identificador de la tarea a cancelar.
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        await notificar_progreso(ctx, f"🛑 Intentando cancelar la tarea '{tarea_id}'...", 10, 100)

        tarea = task_registry.get_task(tarea_id)
        if tarea is None:
            msg = f"⚠️ No se encontró la tarea '{tarea_id}' en el registro. No se puede cancelar."
            await notificar_progreso(ctx, msg, 100, 100)
            return msg

        # Marcar como cancelada en el registro
        task_registry.update_status(tarea_id, "cancelled", detalle="Cancelada por el usuario")

        # Intentar cancelar la asyncio.Task activa si existe
        task_activa = tareas_activas.get(tarea_id)
        if task_activa is not None and not task_activa.done():
            try:
                task_activa.cancel()
                # Esperar brevemente a que la cancelación se propague al grafo
                # (el ainvoke en curso debe abortarse con CancelledError).
                try:
                    await asyncio.wait_for(task_activa, timeout=5.0)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    pass
                msg = f"✅ Tarea '{tarea_id}' marcada como cancelada y su ejecución en curso fue interrumpida."
            except Exception:
                msg = f"✅ Tarea '{tarea_id}' marcada como cancelada (no se pudo interrumpir la ejecución en curso)."
        else:
            msg = f"✅ Tarea '{tarea_id}' marcada como cancelada en el registro."

        await notificar_progreso(ctx, msg, 100, 100)
        return msg
    except Exception as e:
        return f"⚠️ Error al cancelar la tarea '{tarea_id}': {e}"


if __name__ == "__main__":
    try:
        transporte = os.environ.get("FASTMCP_TRANSPORT", "stdio").lower()
        if transporte in ("sse", "streamable-http", "http"):
            host = os.environ.get("FASTMCP_HOST", "127.0.0.1")
            port = int(os.environ.get("FASTMCP_PORT", "8000"))
            _log_stderr(f"[MCP] Iniciando servidor con transporte '{transporte}' en {host}:{port}")
            mcp.run(
                transport=transporte,
                host=host,
                port=port,
            )
        else:
            _log_stderr("[MCP] Iniciando servidor con transporte 'stdio'")
            mcp.run(transport="stdio")
    except (KeyboardInterrupt, BrokenPipeError, ConnectionResetError):
        sys.exit(0)
    except Exception as e:
        err_fatal = str(e)
        sys.stderr.write(f"Error fatal en el servidor MCP: {err_fatal}\n")
        sys.exit(1)
