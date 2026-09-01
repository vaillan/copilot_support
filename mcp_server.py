import os
import sys
import subprocess
import asyncio
import uuid
import hashlib
import re
from typing import Optional, Dict, Any, List

# Asegurar que el directorio del script esté en sys.path.
# Esto evita el error "MCP error -32000: Connection closed" cuando el cliente
# (Zoo Code / Cursor / CLI) lanza el proceso desde un directorio de trabajo
# distinto al del proyecto, lo que provocaría que los imports relativos
# (app.main, app.utils, etc.) fallaran y el proceso se cerrara abruptamente.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

class MuteStderr:
    def write(self, x): pass
    def flush(self): pass


os.environ["FASTMCP_LOG_LEVEL"] = "INFO"

from fastmcp import FastMCP, Context
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from app.main import crear_grafo
from app.utils.project_index import construir_indice
from app.mcp.task_store import task_store
from app.settings.settings import Settings


mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

# Mapa de tareas activas: tarea_id -> asyncio.Task en curso (para cancelación).
tareas_activas: Dict[str, asyncio.Task] = {}

# Longitud máxima de cada celda 'tarea' en la tabla de pasos del formulario
# de pausa. La explicación del plan (sección 📄) nunca se trunca.
_MAX_CELDA_TABLA = 300


def _log_stderr(msg: str):
    """Escribe mensaje a stderr de forma segura (fire-and-forget)."""
    try:
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


async def notificar_progreso(ctx: Optional[Context], mensaje: str, progreso: Optional[int] = None, total: int = 100):
    """
    Envía mensajes de log y progreso en tiempo real de forma segura y directa.
    Captura y maneja cualquier excepción para nunca bloquear la ejecución principal.
    """
    if ctx is None:
        return

    try:
        mensaje_resumido = mensaje.splitlines()[0][:200] if mensaje else ""

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

        if progreso is not None and hasattr(ctx, "report_progress"):
            try:
                res = ctx.report_progress(progreso_val, total=total, message=mensaje_resumido)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass

        if progreso is not None and not has_progress_token:
            pct = int((progreso_val / total) * 100) if total > 0 else progreso_val
            mensaje_formateado = f"[{pct}%] {mensaje_resumido}"
        else:
            mensaje_formateado = mensaje_resumido

        # Enviar mensaje de log al cliente MCP (Zoo Code).
        # FastMCP 3.2.4: ctx.info existe y envía 'notifications/message' de nivel INFO.
        # ctx.log(level, message) es el método genérico equivalente a report_log_message.
        if hasattr(ctx, "info"):
            try:
                res = ctx.info(mensaje_formateado)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass
        elif hasattr(ctx, "log"):
            try:
                res = ctx.log(level="info", message=mensaje_formateado)
                if asyncio.iscoroutine(res):
                    await _safe_await(res, timeout=1.0)
            except Exception:
                pass

        _log_stderr(f"[PROGRESO] {mensaje_formateado}")

    except Exception:
        pass


async def _safe_await(coro, timeout: float = 1.0):
    """Await seguro con timeout que nunca propaga excepciones."""
    try:
        await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
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


def _detectar_intencion_rechazo(texto_usuario: str) -> bool:
    """
    Detecta si el usuario esta expresando un RECHAZO EXPLICITO del plan/codigo.
    
    Retorna True si es un rechazo claro (el usuario NO quiere continuar con lo propuesto).
    Retorna False si es feedback constructivo (el usuario SI quiere continuar pero con cambios).
    """
    texto = texto_usuario.strip().lower()
    
    # Patrones de RECHAZO EXPLICITO (el usuario NO quiere el plan actual)
    patrones_rechazo = [
        r'\brechaz\w*\b',          # rechazo, rechazar, rechazado
        r'\bno\s+aprueb\w*\b',    # no apruebo, no aprobado
        r'\bno\s+acept\w*\b',     # no acepto, no aceptado
        r'\bcancel\w*\b',         # cancelar, cancela, cancelado
        r'\bdescart\w*\b',        # descartar, descarta, descartado
        r'\bno\s+me\s+gusta\b',   # no me gusta
        r'\bno\s+es\s+lo\s+que\b',  # no es lo que queria
        r'\bno\s+quiero\b',       # no quiero
        r'\bno\s+funcion\w*\b',   # no funciona
        r'\beliminar\w*\b',       # eliminar, eliminado
        r'\bborrar\w*\b',         # borrar, borrado
        r'\breset\w*\b',          # reset, resetear
    ]
    
    for patron in patrones_rechazo:
        if re.search(patron, texto):
            return True
    
    return False


def generar_markdown_pausa(
    tarea_id: str,
    tipo_pausa: str,
    titulo: str,
    explicacion: str,
    pasos: Optional[List[Dict[str, Any]]] = None,
    diff_git: str = "",
    directorio_proyecto: str = ""
) -> str:
    """
    Genera un reporte estructurado en Markdown optimizado para Zoo Code, CLI y Cursor.
    Coloca en la parte superior prominente el título, metadatos, explicación y la tabla
    de pasos propuestos (y git diff si aplica), garantizando que el usuario visualice
    claramente el plan de acción antes de los avisos y las instrucciones de aprobación.
    """
    lineas = []
    
    # 1. Título principal y Metadatos de la Tarea
    lineas.append(f"### 📌 {titulo}")
    lineas.append(f"- **ID:** `{tarea_id}`")
    if directorio_proyecto:
        lineas.append(f"- **Dir:** `{directorio_proyecto}`")
    lineas.append(f"- **Estado/Status:** ⏸️ {tipo_pausa}\n")
    
    # 2. Explicación / Resumen (contenido dinámico, sin encabezado textual)
    lineas.append("#### 📄")
    lineas.append(f"{explicacion}\n")

    # 3. Plan de Pasos (Tabla Markdown con iconos)
    # Las celdas de la tabla se truncan a _MAX_CELDA_TABLA caracteres para que
    # el formulario sea legible; la explicación completa (sección 📄) nunca se
    # trunca, de modo que el plan íntegro siempre llega al usuario.
    if pasos:
        lineas.append("#### 📋")
        lineas.append("| # | 📝 | 📄 | 🧪 |")
        lineas.append("|---|---|---|---|")
        for idx, p in enumerate(pasos, start=1):
            t = str(p.get("tarea", "")).replace("|", "\\|")
            if len(t) > _MAX_CELDA_TABLA:
                t = t[:_MAX_CELDA_TABLA].rstrip() + "…"
            a = str(p.get("archivo", "-")).replace("|", "\\|")
            rt = "✅" if p.get("requiere_test") else "—"
            lineas.append(f"| {idx} | {t} | `{a}` | {rt} |")
        lineas.append("")

    # 4. Git Diff / Cambios en Disco (contenido dinámico, sin encabezado textual)
    if diff_git:
        lineas.append("#### 🔍")
        lineas.append("```diff")
        lineas.append(diff_git)
        lineas.append("```\n")

    # 5. Bloque de advertencia para el asistente de IA (inglés neutro compacto)
    lineas.append("---")
    lineas.append("🛑 AI ASSISTANT: FLOW PAUSED. STOP TOOL EXECUTION. SHOW THE PLAN/CHANGES ABOVE TO THE HUMAN USER AND WAIT FOR THEIR EXPLICIT DECISION (APPROVE/REJECT) IN THE CHAT.")
    lineas.append("---\n")

    # 6. Instrucciones para el usuario humano (iconos compactos, sin prosa)
    lineas.append("👉 ✅ = approve / ❌ = reject + feedback")

    return "\n".join(lineas)


async def visualizar_cambios(
    tarea_id: str = "",
    directorio_proyecto: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Función auxiliar interna para consultar el estado actual de una tarea o los cambios en disco.
    Nota: Ya no está expuesta como herramienta MCP para los agentes LLM.
    """
    # Notificación fire-and-forget
    asyncio.create_task(notificar_progreso(ctx, f"🔍 Consultando cambios para tarea '{tarea_id}' en '{directorio_proyecto}'...", 10, 100))
    
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
        asyncio.create_task(notificar_progreso(ctx, "⚠️ No se encontraron cambios para los parámetros proporcionados.", 100, 100))
        return "No se proporcionó un 'tarea_id' válido ni un 'directorio_proyecto' con cambios detectables."
        
    asyncio.create_task(notificar_progreso(ctx, "✅ Visualización de cambios completada.", 100, 100))
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
    
    IMPORTANTE SOBRE PAUSAS Y REVISIONES (PAUSA 1 Y PAUSA 2):
    Cuando el grafo se pause en Pausa 1 (Plan del Arquitecto) o Pausa 2 (Revisión de Código), esta herramienta devolverá un reporte estructurado en Markdown. 
    EL ASISTENTE LLM DEL CLIENTE (ZOO CODE / COPILOT / CURSOR) DEBE DETENERSE INMEDIATAMENTE, mostrar el plan o el diff de código completo al usuario humano, y ESPERAR su confirmación explícita (Aprobar/Rechazar) en el chat. 
    EL ASISTENTE DE IA TIENE PROHIBIDO LLAMAR A ESTA HERRAMIENTA AUTOMÁTICAMENTE PARA APROBAR SIN LA ORDEN EXPRESA DEL USUARIO.
    
    Args:
        instruccion: Lo que el usuario quiere construir, o el feedback si se está rechazando.
            Mantén la instrucción CONCISA (objetivo, alcance y restricciones esenciales):
            el texto completo se registra y se reutiliza en cada iteración del grafo,
            por lo que las instrucciones muy largas desperdician tokens de contexto.
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
            return "🚨 approve: tarea_id required"
        uuid_hex = uuid.uuid4().hex[:8]
        tarea_id = f"task_{uuid_hex}"
        
    config = {"configurable": {"thread_id": tarea_id}, "recursion_limit": 100}

    # Registrar la tarea en el TaskRegistry (si no existe aún).
    try:
        if task_store.get_task(tarea_id) is None:
            task_store.register_task(
                tarea_id=tarea_id,
                thread_id=config["configurable"]["thread_id"],
                directorio_proyecto=directorio_proyecto,
                instruccion=instruccion,
                estado="running",
            )
    except Exception as e:
        _log_stderr(f"[MCP] ERROR al registrar tarea '{tarea_id}': {e}")

    # Notificación inicial
    await notificar_progreso(ctx, f"🚀 Iniciando procesamiento para tarea '{tarea_id}'...", 10, 100)
    _log_stderr(f"[MCP] Iniciando tarea '{tarea_id}' con auto_approve={effective_auto_approve}")

    # Default elevado a 1800s: la fase del Codificador (múltiples llamadas LLM
    # + escritura de archivos) no cabe en 300s y provocaba TIMEOUT prematuros
    # que cancelaban el grafo a mitad de superstep.
    timeout_seconds = int(os.environ.get("MCP_TASK_TIMEOUT_SECONDS", "1800"))

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
                    es_rechazo_rev = _detectar_intencion_rechazo(instruccion)
                    
                    if es_rechazo_rev:
                        # RECHAZO EXPLICITO: Regresamos al codificador
                        msg_rechazo_cod = f"El usuario rechazó el código con este feedback: {instruccion}"
                        msg_rechazo_human = f"Rechazo de código: {instruccion}"
                        # aupdate_state reemplaza los writes pendientes del nodo interrumpido
                        # (incluido loop_counter) evitando INVALID_CONCURRENT_GRAPH_UPDATE;
                        # el Command solo redirige el goto sin update para no colisionar en el superstep.
                        # NO se resetea revision_count: el tope global de 3 revisiones
                        # del Revisor debe acumularse across sesiones para frenar bucles.
                        await agentes_app.aupdate_state(
                            config,
                            {
                                "errores_terminal": msg_rechazo_cod,
                                "messages": [HumanMessage(content=msg_rechazo_human)],
                                "loop_counter": 0
                            },
                            as_node=str(siguiente_nodo)
                        )
                        resultado = await agentes_app.ainvoke(Command(goto="agente_codificador"), config) # type: ignore
                    else:
                        # FEEDBACK CONSTRUCTIVO: Retornamos la pausa de revisión con instrucciones claras
                        codigo_escrito = estado_actual.values.get("codigo_escrito", "No se registró un resumen de cambios.")
                        diff_git = obtener_git_diff(directorio_proyecto)
                        markdown_feedback_rev = generar_markdown_pausa(
                            tarea_id=tarea_id,
                            tipo_pausa="PAUSA_2",
                            titulo="Revisión de Código (Feedback del Usuario Recibido)",
                            explicacion=f"{codigo_escrito}\n\n---\n⚠️ **Nota:** El usuario escribió feedback pero NO aprobó ni rechazó explícitamente.\nPor favor, revisa los cambios anteriores y escribe **'Aprobar'** para continuar o **'Rechazar'** junto con tus observaciones.",
                            diff_git=diff_git,
                            directorio_proyecto=directorio_proyecto
                        )
                        await notificar_progreso(ctx, "↩️ Feedback recibido. Re-pausando Pausa 2 con instrucciones claras para el usuario.", 65, 100)
                        _log_stderr(f"[MCP] PAUSA 2 (feedback re-pausa) - tarea '{tarea_id}'")
                        return markdown_feedback_rev
                    
                elif siguiente_nodo == "agente_codificador":
                    es_rechazo = _detectar_intencion_rechazo(instruccion)
                    
                    if es_rechazo:
                        # RECHAZO EXPLICITO: Regresamos al planificador
                        msg_rechazo_plan = f"El usuario rechazó el plan de acción: {instruccion}"
                        # aupdate_state reemplaza los writes pendientes del nodo interrumpido
                        # (incluido loop_counter) evitando INVALID_CONCURRENT_GRAPH_UPDATE;
                        # el Command solo redirige el goto sin update para no colisionar en el superstep.
                        await agentes_app.aupdate_state(
                            config,
                            {
                                "messages": [HumanMessage(content=msg_rechazo_plan)],
                                "loop_counter": 0
                            },
                            as_node=str(siguiente_nodo)
                        )
                        resultado = await agentes_app.ainvoke(Command(goto="agente_planificador"), config) # type: ignore
                    else:
                        # FEEDBACK CONSTRUCTIVO: Retornamos el plan de nuevo con instrucciones claras
                        plan = estado_actual.values.get("plan_de_accion", {})
                        if isinstance(plan, dict):
                            explicacion = plan.get("explicacion_arquitectura", "Plan de acción propuesto.")
                            pasos_plan = plan.get("pasos", [])
                        else:
                            explicacion = str(plan)
                            pasos_plan = []
                        
                        markdown_feedback = generar_markdown_pausa(
                            tarea_id=tarea_id,
                            tipo_pausa="PAUSA_1",
                            titulo="Plan de Acción (Feedback del Usuario Recibido)",
                            explicacion=f"{explicacion}\n\n---\n⚠️ **Nota:** El usuario escribió feedback pero NO aprobó ni rechazó explícitamente.\nPor favor, revisa el plan anterior y escribe **'Aprobar'** para continuar o **'Rechazar'** junto con tus observaciones.",
                            pasos=pasos_plan,
                            directorio_proyecto=directorio_proyecto
                        )
                        await notificar_progreso(ctx, "↩️ Feedback recibido. Re-pausando con instrucciones claras para el usuario.", 35, 100)
                        _log_stderr(f"[MCP] PAUSA 1 (feedback re-pausa) - tarea '{tarea_id}'")
                        return markdown_feedback
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
                "loop_counter": 0
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
                    task_store.update_status(tarea_id, "paused_planning", detalle=explicacion)
                except Exception as e:
                    _log_stderr(f"[MCP] ERROR al marcar PAUSA_1 en tarea '{tarea_id}': {e}")
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
                    task_store.update_status(tarea_id, "paused_code", detalle=codigo_escrito)
                except Exception as e:
                    _log_stderr(f"[MCP] ERROR al marcar PAUSA_2 en tarea '{tarea_id}': {e}")
                return markdown_pausa

        # Si no hay 'next', el grafo llegó a END
        values = estado.values if hasattr(estado, "values") else {}
        codigo_escrito = values.get("codigo_escrito") or (resultado.get("codigo_escrito") if isinstance(resultado, dict) else "-")
        errores_qa = values.get("errores_terminal") or (resultado.get("errores_terminal") if isinstance(resultado, dict) else "-")
        
        diff_git = obtener_git_diff(directorio_proyecto)
        msg_fin = f"✅ task: {tarea_id}"
        if diff_git:
            msg_fin += f"\n\n🔍 {diff_git}"
        else:
            msg_fin += "\n\n⚠️ git diff: 0 changes"
        await notificar_progreso(ctx, msg_fin, 100, 100)
        _log_stderr(f"[MCP] Tarea '{tarea_id}' COMPLETADA")
        try:
            task_store.update_status(tarea_id, "completed", detalle=codigo_escrito)
        except Exception as e:
            _log_stderr(f"[MCP] ERROR al marcar COMPLETADA la tarea '{tarea_id}': {e}")
        # Si el grafo terminó en un análisis puro (sin programación), el estado
        # contiene 'analisis_final'. Se extrae del estado o del resultado para
        # generar un reporte de análisis dedicado en lugar del reporte de tarea
        # de programación (codigo_escrito/errores_qa).
        analisis_final = values.get("analisis_final") or (resultado.get("analisis_final") if isinstance(resultado, dict) else None)

        if analisis_final:
            reporte_final = f"✅ task: {tarea_id}\n\n📋 {analisis_final}"
        else:
            reporte_final = (
                f"✅ task: {tarea_id}\n"
                f"📝 {codigo_escrito}\n"
                f"🧪 {errores_qa}"
            )
            if not diff_git:
                reporte_final += f"\n\n⚠️ git diff: 0 changes ({directorio_proyecto})"
        return reporte_final

    try:
        return await asyncio.wait_for(_ejecutar_logica(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        msg_timeout = f"🚨 ⏱️ TIMEOUT ({timeout_seconds}s) — task: {tarea_id}"
        await notificar_progreso(ctx, msg_timeout, 100, 100)
        _log_stderr(f"[MCP] TIMEOUT tarea '{tarea_id}'")
        try:
            task_store.update_status(tarea_id, "timeout", detalle=msg_timeout)
        except Exception as e:
            _log_stderr(f"[MCP] ERROR al marcar TIMEOUT en tarea '{tarea_id}': {e}")
        return msg_timeout
    except BaseException as e:
        err_msg = str(e)
        msg_err = f"🚨 task: {tarea_id}: {err_msg}"
        _log_stderr(f"[MCP] ERROR tarea '{tarea_id}': {err_msg}")
        await notificar_progreso(ctx, msg_err, 100, 100)
        try:
            task_store.update_status(tarea_id, "error", detalle=err_msg)
        except Exception as e:
            _log_stderr(f"[MCP] ERROR al marcar ERROR en tarea '{tarea_id}': {e}")
        return msg_err


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
        tarea = task_store.get_task(tarea_id)
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

        tareas = task_store.list_tasks(estado=estado)

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

        tarea = task_store.get_task(tarea_id)
        if tarea is None:
            msg = f"⚠️ No se encontró la tarea '{tarea_id}' en el registro. No se puede cancelar."
            await notificar_progreso(ctx, msg, 100, 100)
            return msg

        # Marcar como cancelada en el registro
        task_store.update_status(tarea_id, "cancelled", detalle="Cancelada por el usuario")

        # Intentar cancelar la asyncio.Task activa si existe
        task_activa = tareas_activas.get(tarea_id)
        if task_activa is not None and not task_activa.done():
            try:
                task_activa.cancel()
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
