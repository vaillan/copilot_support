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
from app.utils.i18n import detectar_idioma, normalizar_idioma, obtener_mensaje
from app.utils.project_index import construir_indice
from app.utils.task_registry import task_registry
from app.settings.settings import Settings


mcp = FastMCP("AIDevTeam")

agentes_app = crear_grafo()

# Mapa de tareas activas: tarea_id -> asyncio.Task en curso (para cancelación).
tareas_activas: Dict[str, asyncio.Task] = {}

# Patrones de RECHAZO EXPLICITO en español (el usuario NO quiere el plan actual).
_PATRONES_RECHAZO_ES: List[str] = [
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

# Patrones de rechazo explícito en inglés (se usan cuando detectar_idioma retorna "en").
_PATRONES_RECHAZO_EN: List[str] = [
    r"\bno\b",
    r"\bcancel\b",
    r"\bstop\b",
    r"\babort\b",
    r"\bdecline\b",
    r"\bdon'?t\b",
    r"\bwon'?t\b",
    r"\bhalt\b",
    r"\brefuse\b",
]


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


def obtener_git_diff(directorio: str, idioma: str = "es") -> str:
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
            return obtener_mensaje("git.archivos_modificados", idioma, status=stdout_clean)
    except Exception:
        pass
    return ""


def _detectar_intencion_rechazo(texto_usuario: Optional[str]) -> bool:
    """
    Detecta si el usuario expresa un rechazo explícito del plan/código.
    Retorna True si es un rechazo claro; False si es feedback constructivo o entrada vacía.
    """
    if texto_usuario is None or not texto_usuario.strip():
        return False

    texto = texto_usuario.strip().lower()
    idioma = detectar_idioma(texto_usuario)
    patrones = _PATRONES_RECHAZO_EN if idioma == "en" else _PATRONES_RECHAZO_ES

    return any(re.search(p, texto, re.IGNORECASE) for p in patrones)


def generar_markdown_pausa(
    tarea_id: str,
    tipo_pausa: str,
    titulo: str,
    explicacion: str,
    pasos: Optional[List[Dict[str, Any]]] = None,
    diff_git: str = "",
    directorio_proyecto: str = "",
    idioma: str = "es"
) -> str:
    """
    Genera un reporte estructurado en Markdown optimizado para Zoo Code, CLI y Cursor.
    Coloca en la parte superior prominente el título, metadatos, explicación y la tabla
    de pasos propuestos (y git diff si aplica), garantizando que el usuario visualice
    claramente el plan de acción antes de los avisos y las instrucciones de aprobación.
    """
    lineas = []
    
    # 1. Título principal y Metadatos de la Tarea en la parte superior prominente
    lineas.append(f"### 📌 {titulo}")
    lineas.append(obtener_mensaje("pausa.id_tarea", idioma, tarea_id=tarea_id))
    if directorio_proyecto:
        lineas.append(obtener_mensaje("pausa.directorio", idioma, directorio=directorio_proyecto))
    lineas.append(obtener_mensaje("pausa.estado_pausado", idioma, tipo_pausa=tipo_pausa) + "\n")
    
    # 2. Explicación / Resumen
    lineas.append(obtener_mensaje("pausa.explicacion_titulo", idioma))
    lineas.append(f"{explicacion}\n")

    # 3. Plan de Pasos Propuestos (Tabla Markdown)
    if pasos:
        lineas.append(obtener_mensaje("pausa.plan_titulo", idioma))
        lineas.append(obtener_mensaje("pausa.tabla_encabezado", idioma))
        lineas.append("|---|-------|---------|---------------|")
        for idx, p in enumerate(pasos, start=1):
            t = str(p.get("tarea", "")).replace("|", "\\|")
            a = str(p.get("archivo", "-")).replace("|", "\\|")
            rt = obtener_mensaje("pausa.si", idioma) if p.get("requiere_test") else obtener_mensaje("pausa.no", idioma)
            lineas.append(f"| {idx} | {t} | `{a}` | {rt} |")
        lineas.append("")

    # 4. Git Diff / Cambios en Disco (si existen)
    if diff_git:
        lineas.append(obtener_mensaje("pausa.diff_titulo", idioma))
        lineas.append("```diff")
        lineas.append(diff_git)
        lineas.append("```\n")

    # 5. Bloque de advertencia para el asistente de IA (desplazado hacia la parte inferior)
    lineas.append("================================================================================")
    lineas.append(obtener_mensaje("pausa.aviso_ia", idioma))
    lineas.append("================================================================================\n")

    # 6. Instrucciones para el usuario humano (en la parte inferior)
    lineas.append("--------------------------------------------------------------------------------")
    lineas.append(obtener_mensaje("pausa.instrucciones_titulo", idioma))
    lineas.append("--------------------------------------------------------------------------------")
    lineas.append(obtener_mensaje("pausa.instrucciones_cuerpo", idioma))
    lineas.append("================================================================================")

    return "\n".join(lineas)


async def visualizar_cambios(
    tarea_id: str = "",
    directorio_proyecto: str = "",
    ctx: Optional[Context] = None,
    idioma: str = "es"
) -> str:
    """
    Función auxiliar interna para consultar el estado actual de una tarea o los cambios en disco.
    Nota: Ya no está expuesta como herramienta MCP para los agentes LLM.
    """
    # Notificación fire-and-forget
    asyncio.create_task(notificar_progreso(ctx, obtener_mensaje("flujo.consultando_cambios", idioma, tarea_id=tarea_id, directorio=directorio_proyecto), 10, 100))
    
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
                msg_resumen = obtener_mensaje("flujo.resumen_cambios", idioma, tarea_id=tarea_id, resumen=codigo_escrito)
                partes.append(msg_resumen)
            else:
                msg_sin_resumen = obtener_mensaje("flujo.tarea_sin_resumen", idioma, tarea_id=tarea_id)
                partes.append(msg_sin_resumen)
                
            if estado.next:
                siguiente_nodo = estado.next[0]
                msg_estado = obtener_mensaje("flujo.estado_pausado_nodo", idioma, nodo=siguiente_nodo)
                partes.append(msg_estado)
            else:
                partes.append(obtener_mensaje("flujo.estado_finalizado", idioma))
        except Exception as e:
            err_msg = str(e)
            msg_err = obtener_mensaje("flujo.error_estado", idioma, tarea_id=tarea_id, error=err_msg)
            partes.append(msg_err)

    if dir_a_consultar:
        diff_git = obtener_git_diff(dir_a_consultar, idioma)
        if diff_git:
            msg_diff = obtener_mensaje("flujo.cambios_disco", idioma, directorio=dir_a_consultar, diff=diff_git)
            partes.append(msg_diff)
            
    if not partes:
        asyncio.create_task(notificar_progreso(ctx, obtener_mensaje("flujo.sin_cambios_params", idioma), 100, 100))
        return obtener_mensaje("flujo.sin_parametros_validos", idioma)
        
    asyncio.create_task(notificar_progreso(ctx, obtener_mensaje("flujo.visualizacion_completada", idioma), 100, 100))
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
        directorio_proyecto: La ruta absoluta de la carpeta actual.
        approve: Booleano para aprobar y continuar si el proceso está pausado esperando revisión humana.
        tarea_id: OBLIGATORIO SI ESTÁS APROBANDO O RECHAZANDO UNA PAUSA. Déjalo vacío para iniciar una tarea nueva.
        auto_approve: Si es True (o la variable MCP_AUTO_APPROVE=true), auto-aprueba todas las pausas (Pausa 1 y Pausa 2) sin requerir confirmación manual.
    """
    env_val_raw = os.environ.get("MCP_AUTO_APPROVE", "")
    env_val_clean = env_val_raw.strip().lower()
    env_auto_approve = env_val_clean in ("true", "1", "yes")
    effective_auto_approve = auto_approve or env_auto_approve

    # Resolver idioma de la instrucción (fallback: instrucción registrada, luego "es").
    texto_idioma: str = instruccion.strip() if isinstance(instruccion, str) else ""
    if not texto_idioma and tarea_id:
        texto_idioma = str((task_registry.get_task(tarea_id) or {}).get("instruccion", "") or "")
    idioma: str = detectar_idioma(texto_idioma) if texto_idioma else "es"

    # Si es una tarea nueva, generamos un ID único. Si estamos resumiendo, usamos el que nos pasa el LLM.
    if not tarea_id:
        if approve:
            return obtener_mensaje("flujo.aprobar_sin_id", idioma)
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
    await notificar_progreso(ctx, obtener_mensaje("flujo.iniciando", idioma, tarea_id=tarea_id), 10, 100)
    _log_stderr(f"[MCP] Iniciando tarea '{tarea_id}' con auto_approve={effective_auto_approve}")

    timeout_seconds = int(os.environ.get("MCP_TASK_TIMEOUT_SECONDS", "300"))

    async def _ejecutar_logica() -> str:
        estado_actual = await agentes_app.aget_state(config) # type: ignore
        is_paused = len(estado_actual.next) > 0

        if is_paused:
            siguiente_nodo = estado_actual.next[0]
            if approve or effective_auto_approve:
                msg_reanudando = obtener_mensaje("flujo.reanudando", idioma, tarea_id=tarea_id, nodo=siguiente_nodo)
                await notificar_progreso(ctx, msg_reanudando, 50, 100)
                _log_stderr(f"[MCP] Reanudando tarea '{tarea_id}' en nodo '{siguiente_nodo}'")
                # Reanudamos la ejecución
                resultado = await agentes_app.ainvoke(None, config) # type: ignore
                estado_post = await agentes_app.aget_state(config) # type: ignore
                
                # Bucle para procesar herramientas del nodo actual sin saltar a la siguiente pausa humana
                tool_loop_count = 0
                while estado_post.next and estado_post.next[0] == siguiente_nodo and tool_loop_count < 20:
                    tool_step = tool_loop_count + 1
                    msg_tool = obtener_mensaje("flujo.procesando_herramientas", idioma, nodo=siguiente_nodo, paso=tool_step)
                    await notificar_progreso(ctx, msg_tool, 60, 100)
                    resultado = await agentes_app.ainvoke(None, config) # type: ignore
                    estado_post = await agentes_app.aget_state(config) # type: ignore
                    tool_loop_count += 1
            else:
                msg_feedback = obtener_mensaje("flujo.procesando_feedback", idioma, nodo=siguiente_nodo)
                await notificar_progreso(ctx, msg_feedback, 30, 100)
                # RECHAZO DEL USUARIO: Regresamos con feedback y REINICIAMOS CONTADORES
                if siguiente_nodo == "agente_revisor":
                    es_rechazo_rev = _detectar_intencion_rechazo(instruccion)
                    
                    if es_rechazo_rev:
                        # RECHAZO EXPLICITO: Regresamos al codificador
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
                    else:
                        # FEEDBACK CONSTRUCTIVO: Retornamos la pausa de revisión con instrucciones claras
                        codigo_escrito = estado_actual.values.get("codigo_escrito", obtener_mensaje("flujo.sin_resumen", idioma))
                        diff_git = obtener_git_diff(directorio_proyecto, idioma)
                        markdown_feedback_rev = generar_markdown_pausa(
                            tarea_id=tarea_id,
                            tipo_pausa="PAUSA_2",
                            titulo=obtener_mensaje("flujo.titulo_feedback_codigo", idioma),
                            explicacion=f"{codigo_escrito}\n\n---\n{obtener_mensaje('flujo.nota_feedback_codigo', idioma)}",
                            diff_git=diff_git,
                            directorio_proyecto=directorio_proyecto,
                            idioma=idioma
                        )
                        await notificar_progreso(ctx, obtener_mensaje("flujo.feedback_pausa2_log", idioma), 65, 100)
                        _log_stderr(f"[MCP] PAUSA 2 (feedback re-pausa) - tarea '{tarea_id}'")
                        return markdown_feedback_rev
                    
                elif siguiente_nodo == "agente_codificador":
                    es_rechazo = _detectar_intencion_rechazo(instruccion)
                    
                    if es_rechazo:
                        # RECHAZO EXPLICITO: Regresamos al planificador
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
                        # FEEDBACK CONSTRUCTIVO: Retornamos el plan de nuevo con instrucciones claras
                        plan = estado.values.get("plan_de_accion", {})
                        if isinstance(plan, dict):
                            explicacion = plan.get("explicacion_arquitectura", obtener_mensaje("flujo.plan_default_feedback", idioma))
                            pasos_plan = plan.get("pasos", [])
                        else:
                            explicacion = str(plan)
                            pasos_plan = []
                        
                        markdown_feedback = generar_markdown_pausa(
                            tarea_id=tarea_id,
                            tipo_pausa="PAUSA_1",
                            titulo=obtener_mensaje("flujo.titulo_feedback_plan", idioma),
                            explicacion=f"{explicacion}\n\n---\n{obtener_mensaje('flujo.nota_feedback_plan', idioma)}",
                            pasos=pasos_plan,
                            directorio_proyecto=directorio_proyecto,
                            idioma=idioma
                        )
                        await notificar_progreso(ctx, obtener_mensaje("flujo.feedback_pausa1_log", idioma), 35, 100)
                        _log_stderr(f"[MCP] PAUSA 1 (feedback re-pausa) - tarea '{tarea_id}'")
                        return markdown_feedback
                else:
                    resultado = await agentes_app.ainvoke(None, config) # type: ignore
        else:
            instruccion_corta = instruccion[:50]
            msg_planificador = obtener_mensaje("flujo.iniciando_planificador", idioma, instruccion=instruccion_corta)
            await notificar_progreso(ctx, msg_planificador, 20, 100)
            _log_stderr(f"[MCP] Nueva tarea '{tarea_id}': iniciando Planificador")
            # Construir el índice del proyecto para optimizar tokens (si está habilitado)
            project_index = None
            try:
                settings_mcp = Settings()
                if getattr(settings_mcp, "PROJECT_INDEX_ENABLED", True):
                    project_index = construir_indice(directorio_proyecto, idioma=idioma)
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
            msg_auto = obtener_mensaje("flujo.auto_aprobacion", idioma, nodo=siguiente_nodo, tarea_id=tarea_id)
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
                    explicacion = plan.get("explicacion_arquitectura", obtener_mensaje("flujo.plan_default", idioma))
                    pasos = plan.get("pasos", [])
                else:
                    explicacion = str(plan)
                    pasos = []
                
                markdown_pausa = generar_markdown_pausa(
                    tarea_id=tarea_id,
                    tipo_pausa="PAUSA_1",
                    titulo=obtener_mensaje("flujo.titulo_pausa1", idioma),
                    explicacion=explicacion,
                    pasos=pasos,
                    directorio_proyecto=directorio_proyecto,
                    idioma=idioma
                )
                msg_pausa1 = obtener_mensaje("flujo.pausa1_msg", idioma, tarea_id=tarea_id, markdown=markdown_pausa)
                await notificar_progreso(ctx, msg_pausa1, 40, 100)
                _log_stderr(f"[MCP] PAUSA 1 - tarea '{tarea_id}' esperando aprobación de plan")
                try:
                    task_registry.update_status(tarea_id, "paused_planning", detalle=explicacion)
                except Exception:
                    pass
                return markdown_pausa
                
            elif siguiente_nodo == "agente_revisor":
                codigo_escrito = estado.values.get("codigo_escrito", obtener_mensaje("flujo.sin_resumen", idioma))
                diff_git = obtener_git_diff(directorio_proyecto, idioma)
                markdown_pausa = generar_markdown_pausa(
                    tarea_id=tarea_id,
                    tipo_pausa="PAUSA_2",
                    titulo=obtener_mensaje("flujo.titulo_pausa2", idioma),
                    explicacion=codigo_escrito,
                    diff_git=diff_git,
                    directorio_proyecto=directorio_proyecto,
                    idioma=idioma
                )
                msg_cambios = obtener_mensaje("flujo.pausa2_msg", idioma, tarea_id=tarea_id, markdown=markdown_pausa)
                await notificar_progreso(ctx, msg_cambios, 70, 100)
                _log_stderr(f"[MCP] PAUSA 2 - tarea '{tarea_id}' esperando aprobación de código")
                try:
                    task_registry.update_status(tarea_id, "paused_code", detalle=codigo_escrito)
                except Exception:
                    pass
                return markdown_pausa

        # Si no hay 'next', el grafo llegó a END
        values = estado.values if hasattr(estado, "values") else {}
        codigo_escrito = values.get("codigo_escrito") or (resultado.get("codigo_escrito") if isinstance(resultado, dict) else obtener_mensaje("flujo.sin_codigo", idioma))
        errores_qa = values.get("errores_terminal") or (resultado.get("errores_terminal") if isinstance(resultado, dict) else obtener_mensaje("flujo.sin_errores", idioma))
        
        diff_git = obtener_git_diff(directorio_proyecto, idioma)
        msg_fin = obtener_mensaje("flujo.completada", idioma, tarea_id=tarea_id)
        if diff_git:
            diff_msg = obtener_mensaje("flujo.cambios_finales", idioma, diff=diff_git)
            msg_fin += diff_msg
        else:
            msg_fin += obtener_mensaje("flujo.advertencia_sin_cambios", idioma)
        await notificar_progreso(ctx, msg_fin, 100, 100)
        _log_stderr(f"[MCP] Tarea '{tarea_id}' COMPLETADA")
        try:
            task_registry.update_status(tarea_id, "completed", detalle=codigo_escrito)
        except Exception:
            pass
        # Si el grafo terminó en un análisis puro (sin programación), el estado
        # contiene 'analisis_final'. Se extrae del estado o del resultado para
        # generar un reporte de análisis dedicado en lugar del reporte de tarea
        # de programación (codigo_escrito/errores_qa).
        analisis_final = values.get("analisis_final") or (resultado.get("analisis_final") if isinstance(resultado, dict) else None)

        if analisis_final:
            reporte_final = obtener_mensaje("flujo.analisis_completado", idioma, tarea_id=tarea_id, analisis=analisis_final)
        else:
            reporte_final = obtener_mensaje("flujo.reporte_final", idioma, tarea_id=tarea_id, resumen=codigo_escrito, errores=errores_qa)
            if not diff_git:
                reporte_final += obtener_mensaje("flujo.advertencia_diff_vacio", idioma, directorio=directorio_proyecto)
        return reporte_final

    try:
        return await asyncio.wait_for(_ejecutar_logica(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        msg_timeout = obtener_mensaje("flujo.timeout", idioma, tarea_id=tarea_id, segundos=timeout_seconds)
        await notificar_progreso(ctx, msg_timeout, 100, 100)
        _log_stderr(f"[MCP] TIMEOUT tarea '{tarea_id}'")
        try:
            task_registry.update_status(tarea_id, "timeout", detalle=msg_timeout)
        except Exception:
            pass
        return f"{msg_timeout}{obtener_mensaje('flujo.timeout_consejo', idioma, tarea_id=tarea_id)}"
    except BaseException as e:
        err_msg = str(e)
        msg_err = obtener_mensaje("flujo.error_interno", idioma, tarea_id=tarea_id, error=err_msg)
        _log_stderr(f"[MCP] ERROR tarea '{tarea_id}': {err_msg}")
        await notificar_progreso(ctx, msg_err, 100, 100)
        try:
            task_registry.update_status(tarea_id, "error", detalle=err_msg)
        except Exception:
            pass
        return msg_err


@mcp.tool()
async def consultar_estado_tarea(
    tarea_id: str,
    directorio_proyecto: str = "",
    idioma: str = "",
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
        idioma: Idioma de la respuesta ("es" o "en"); vacío resuelve por la instrucción registrada.
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        if idioma:
            idioma_resuelto: str = normalizar_idioma(idioma)
        else:
            instruccion_registrada = str((task_registry.get_task(tarea_id) or {}).get("instruccion", "") or "")
            idioma_resuelto = detectar_idioma(instruccion_registrada) if instruccion_registrada else "en"

        await notificar_progreso(ctx, obtener_mensaje("estado.consultando", idioma_resuelto, tarea_id=tarea_id), 10, 100)

        partes = []

        # 1. Estado registrado en el TaskRegistry
        tarea = task_registry.get_task(tarea_id)
        if tarea is not None:
            estado_registrado = tarea.get("estado", "desconocido")
            partes.append(obtener_mensaje("estado.registrado_titulo", idioma_resuelto, tarea_id=tarea_id))
            partes.append(obtener_mensaje("estado.campo_estado", idioma_resuelto, estado=estado_registrado))
            partes.append(obtener_mensaje("estado.campo_directorio", idioma_resuelto, directorio=tarea.get('directorio_proyecto', '')))
            partes.append(obtener_mensaje("estado.campo_actualizacion", idioma_resuelto, timestamp=tarea.get('timestamp_actualizacion', '')))
            if tarea.get("detalle"):
                partes.append(obtener_mensaje("estado.campo_detalle", idioma_resuelto, detalle=tarea.get('detalle')))
            partes.append("")
        else:
            partes.append(obtener_mensaje("estado.no_registrada", idioma_resuelto, tarea_id=tarea_id))

        # 2. Estado del grafo y cambios en disco (reutiliza visualizar_cambios)
        try:
            estado_grafo = await visualizar_cambios(tarea_id=tarea_id, directorio_proyecto=directorio_proyecto, ctx=ctx, idioma=idioma_resuelto)
            partes.append(estado_grafo)
        except Exception as e:
            partes.append(obtener_mensaje("estado.error_grafo", idioma_resuelto, error=e))

        await notificar_progreso(ctx, obtener_mensaje("estado.consulta_completada", idioma_resuelto), 100, 100)
        return "\n\n".join(partes)
    except Exception as e:
        return obtener_mensaje("estado.error_consulta", idioma_resuelto, tarea_id=tarea_id, error=e)


@mcp.tool()
async def listar_tareas(
    estado: str = "",
    idioma: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Lista las tareas registradas en el servidor MCP.

    Args:
        estado: Filtro opcional por estado (running, paused_planning, paused_code, completed, cancelled, timeout, error).
        idioma: Idioma de la respuesta ("es" o "en"); vacío resuelve "en".
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        idioma = normalizar_idioma(idioma)
        await notificar_progreso(ctx, obtener_mensaje("listar.listando", idioma), 10, 100)

        tareas = task_registry.list_tasks(estado=estado)

        if not tareas:
            filtro = obtener_mensaje("listar.filtro_estado", idioma, estado=estado) if estado else ""
            msg = obtener_mensaje("listar.vacio", idioma, filtro=filtro)
            await notificar_progreso(ctx, msg, 100, 100)
            return msg

        lineas = [obtener_mensaje("listar.titulo", idioma)]
        lineas.append(obtener_mensaje("listar.encabezado_tabla", idioma))
        lineas.append("|---|---|---|---|")
        for t in tareas:
            tid = str(t.get("tarea_id", "")).replace("|", "\\|")
            est = str(t.get("estado", "")).replace("|", "\\|")
            dirp = str(t.get("directorio_proyecto", "")).replace("|", "\\|")
            ts = str(t.get("timestamp_actualizacion", "")).replace("|", "\\|")
            lineas.append(f"| `{tid}` | `{est}` | `{dirp}` | `{ts}` |")
        lineas.append("")

        await notificar_progreso(ctx, obtener_mensaje("listar.encontradas", idioma, cantidad=len(tareas)), 100, 100)
        return "\n".join(lineas)
    except Exception as e:
        return obtener_mensaje("listar.error", idioma, error=e)


@mcp.tool()
async def cancelar_tarea(
    tarea_id: str,
    idioma: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Cancela una tarea en curso registrada en el TaskRegistry.

    Marca la tarea como 'cancelled' e intenta cancelar la asyncio.Task activa
    asociada si está disponible.

    Args:
        tarea_id: Identificador de la tarea a cancelar.
        idioma: Idioma de la respuesta ("es" o "en"); vacío resuelve por la instrucción registrada.
        ctx: Contexto MCP para notificaciones de progreso.
    """
    try:
        if idioma:
            idioma_resuelto: str = normalizar_idioma(idioma)
        else:
            instruccion_registrada = str((task_registry.get_task(tarea_id) or {}).get("instruccion", "") or "")
            idioma_resuelto = detectar_idioma(instruccion_registrada) if instruccion_registrada else "en"

        await notificar_progreso(ctx, obtener_mensaje("cancelar.intentando", idioma_resuelto, tarea_id=tarea_id), 10, 100)

        tarea = task_registry.get_task(tarea_id)
        if tarea is None:
            msg = obtener_mensaje("cancelar.no_encontrada", idioma_resuelto, tarea_id=tarea_id)
            await notificar_progreso(ctx, msg, 100, 100)
            return msg

        # Marcar como cancelada en el registro
        task_registry.update_status(tarea_id, "cancelled", detalle=obtener_mensaje("cancelar.detalle", idioma_resuelto))

        # Intentar cancelar la asyncio.Task activa si existe
        task_activa = tareas_activas.get(tarea_id)
        if task_activa is not None and not task_activa.done():
            try:
                task_activa.cancel()
                msg = obtener_mensaje("cancelar.interrumpida", idioma_resuelto, tarea_id=tarea_id)
            except Exception:
                msg = obtener_mensaje("cancelar.cancelada_sin_interrumpir", idioma_resuelto, tarea_id=tarea_id)
        else:
            msg = obtener_mensaje("cancelar.cancelada", idioma_resuelto, tarea_id=tarea_id)

        await notificar_progreso(ctx, msg, 100, 100)
        return msg
    except Exception as e:
        return obtener_mensaje("cancelar.error", idioma_resuelto, tarea_id=tarea_id, error=e)


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