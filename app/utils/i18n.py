"""Módulo ligero de internacionalización (es/en) para la capa de herramientas.

Detecta el idioma de una instrucción por heurística de stopwords y acentos,
y resuelve plantillas de mensajes desde un catálogo central (MENSAJES) con
interpolación str.format y fallback defensivo. Solo usa la stdlib.
"""

import re
from typing import Any, Dict, FrozenSet, Optional

# Palabras funcionales frecuentes del español (señal fuerte de idioma).
ES_STOPWORDS: FrozenSet[str] = frozenset(
    {
        "el", "la", "los", "las", "un", "una", "de", "del", "al", "y", "o",
        "en", "que", "con", "para", "por", "es", "son", "ser", "esta", "este",
        "esto", "como", "mas", "más", "pero", "su", "sus", "se", "lo", "le",
        "ya", "ha", "hay", "si", "sí", "muy", "todo", "todos", "todas", "cada",
        "cuando", "donde", "entre", "sobre", "desde", "hasta", "sin", "te",
        "nos", "quiero", "crea", "crear", "escribe", "escribir", "haz", "hacer",
        "archivo", "archivos", "codigo", "código", "funcion", "función",
        "proyecto", "favor",
    }
)

# Palabras funcionales frecuentes del inglés (señal fuerte de idioma).
EN_STOPWORDS: FrozenSet[str] = frozenset(
    {
        "the", "an", "of", "to", "in", "is", "are", "and", "or", "for", "with",
        "on", "at", "by", "from", "that", "this", "these", "those", "it", "its",
        "be", "been", "was", "were", "has", "have", "had", "do", "does", "did",
        "but", "if", "then", "than", "as", "so", "we", "you", "your", "i", "my",
        "our", "their", "there", "here", "what", "which", "who", "how", "when",
        "where", "all", "any", "some", "can", "will", "would", "should", "could",
        "please", "write", "create", "make", "add", "fix", "implement", "file",
        "files", "code", "function", "use", "using", "need", "must", "project",
        "config",
    }
)

# Caracteres exclusivos del español que refuerzan la detección.
_ACENTOS_ES: str = "áéíóúñü"


def detectar_idioma(texto: str) -> str:
    """Detecta el idioma de un texto por stopwords y acentos; retorna 'es' o 'en'."""
    if not texto or not texto.strip():
        return "en"
    texto_norm = texto.lower()
    tokens = re.findall(r"[a-záéíóúñü]+", texto_norm)
    score_es = 0
    score_en = 0
    for token in tokens:
        if token in ES_STOPWORDS:
            score_es += 1
        if token in EN_STOPWORDS:
            score_en += 1
        if any(c in token for c in _ACENTOS_ES):
            score_es += 2
    if "¿" in texto or "¡" in texto:
        score_es += 2
    return "es" if score_es > score_en else "en"


def normalizar_idioma(idioma: Optional[str]) -> str:
    """Normaliza un valor de idioma: 'es' (insensible a mayúsculas) o 'en'."""
    return "es" if (idioma or "").strip().lower() == "es" else "en"


# Catálogo de plantillas: clave -> {"es": plantilla, "en": plantilla}.
# La plantilla "es" reproduce VERBATIM las cadenas actuales del código para
# que la salida por defecto no cambie; "en" es su traducción fiel.
MENSAJES: Dict[str, Dict[str, str]] = {
    # ------------------------------------------------------------------ pausa
    "pausa.id_tarea": {
        "es": "- **ID Tarea:** `{tarea_id}`",
        "en": "- **Task ID:** `{tarea_id}`",
    },
    "pausa.directorio": {
        "es": "- **Directorio:** `{directorio}`",
        "en": "- **Directory:** `{directorio}`",
    },
    "pausa.estado_pausado": {
        "es": "- **Estado:** Pausado ({tipo_pausa}) - Requiere aprobación humana.",
        "en": "- **Status:** Paused ({tipo_pausa}) - Requires human approval.",
    },
    "pausa.explicacion_titulo": {
        "es": "#### 📄 Explicación / Resumen:",
        "en": "#### 📄 Explanation / Summary:",
    },
    "pausa.plan_titulo": {
        "es": "#### 📋 Plan de Pasos Propuestos:",
        "en": "#### 📋 Proposed Action Plan:",
    },
    "pausa.tabla_encabezado": {
        "es": "| # | Tarea | Archivo | Requiere Test |",
        "en": "| # | Task | File | Requires Test |",
    },
    "pausa.si": {"es": "Si", "en": "Yes"},
    "pausa.no": {"es": "No", "en": "No"},
    "pausa.diff_titulo": {
        "es": "#### 🔍 Git Diff / Cambios en Disco:",
        "en": "#### 🔍 Git Diff / On-disk Changes:",
    },
    "pausa.aviso_ia": {
        "es": (
            "🛑 ATENCIÓN ASISTENTE DE IA (ZOO CODE / COPILOT / CURSOR):\n"
            "EL FLUJO ESTÁ PAUSADO ESPERANDO CONFIRMACIÓN DEL USUARIO HUMANO.\n"
            "**DETÉN LA EJECUCIÓN AUTOMÁTICA DE HERRAMIENTAS DE INMEDIATO.**\n"
            "NO ejecutes ninguna función ni herramienta por tu cuenta.\n"
            "Muestra todo el plan de acción y/o los cambios de código anteriores "
            "directamente al usuario humano en el chat y **ESPERA** pacientemente "
            "a que el usuario escriba su decisión explícita."
        ),
        "en": (
            "🛑 AI ASSISTANT WARNING (ZOO CODE / COPILOT / CURSOR):\n"
            "THE FLOW IS PAUSED WAITING FOR HUMAN USER CONFIRMATION.\n"
            "**STOP AUTOMATIC TOOL EXECUTION IMMEDIATELY.**\n"
            "Do NOT run any function or tool on your own.\n"
            "Show the full action plan and/or the previous code changes directly "
            "to the human user in the chat and **WAIT** patiently for the user "
            "to write their explicit decision."
        ),
    },
    "pausa.instrucciones_titulo": {
        "es": "👉 **INSTRUCCIONES PARA EL USUARIO HUMANO:**",
        "en": "👉 **INSTRUCTIONS FOR THE HUMAN USER:**",
    },
    "pausa.instrucciones_cuerpo": {
        "es": (
            "Por favor, revisa detalladamente el plan o los cambios de código anteriores.\n"
            "• **PARA APROBAR:** Escribe en el chat que apruebas la tarea (ej. 'Aprobar' o 'Acepto').\n"
            "• **PARA RECHAZAR O PEDIR CAMBIOS:** Escribe en el chat 'Rechazar' junto con tus observaciones o correcciones.\n"
            "El asistente de IA debe detenerse y esperar a que tú escribas tu respuesta."
        ),
        "en": (
            "Please review the plan or the previous code changes in detail.\n"
            "• **TO APPROVE:** Write in the chat that you approve the task (e.g. 'Approve' or 'I accept').\n"
            "• **TO REJECT OR REQUEST CHANGES:** Write 'Reject' in the chat along with your observations or corrections.\n"
            "The AI assistant must stop and wait for you to write your response."
        ),
    },
    # ------------------------------------------------------------------ flujo
    "flujo.aprobar_sin_id": {
        "es": "Error: No puedes aprobar una tarea sin proporcionar el 'tarea_id' de la sesión pausada.",
        "en": "Error: You cannot approve a task without providing the 'tarea_id' of the paused session.",
    },
    "flujo.iniciando": {
        "es": "🚀 Iniciando procesamiento para tarea '{tarea_id}'...",
        "en": "🚀 Starting processing for task '{tarea_id}'...",
    },
    "flujo.reanudando": {
        "es": "▶️ Reanudando tarea '{tarea_id}' (Aprobación confirmada para nodo '{nodo}')...",
        "en": "▶️ Resuming task '{tarea_id}' (Approval confirmed for node '{nodo}')...",
    },
    "flujo.procesando_herramientas": {
        "es": "⚙️ Procesando herramientas en nodo '{nodo}' ({paso})....",
        "en": "⚙️ Processing tools in node '{nodo}' ({paso})....",
    },
    "flujo.procesando_feedback": {
        "es": "↩️ Procesando rechazo/feedback del usuario para nodo '{nodo}'...",
        "en": "↩️ Processing user rejection/feedback for node '{nodo}'...",
    },
    "flujo.nota_feedback_plan": {
        "es": (
            "⚠️ **Nota:** El usuario escribió feedback pero NO aprobó ni rechazó explícitamente.\n"
            "Por favor, revisa el plan anterior y escribe **'Aprobar'** para continuar o **'Rechazar'** junto con tus observaciones."
        ),
        "en": (
            "⚠️ **Note:** The user wrote feedback but did NOT explicitly approve or reject.\n"
            "Please review the previous plan and write **'Approve'** to continue or **'Reject'** with your observations."
        ),
    },
    "flujo.nota_feedback_codigo": {
        "es": (
            "⚠️ **Nota:** El usuario escribió feedback pero NO aprobó ni rechazó explícitamente.\n"
            "Por favor, revisa los cambios anteriores y escribe **'Aprobar'** para continuar o **'Rechazar'** junto con tus observaciones."
        ),
        "en": (
            "⚠️ **Note:** The user wrote feedback but did NOT explicitly approve or reject.\n"
            "Please review the previous changes and write **'Approve'** to continue or **'Reject'** with your observations."
        ),
    },
    "flujo.titulo_pausa1": {
        "es": "Formulario de Aprobación de Plan de Acción",
        "en": "Action Plan Approval Form",
    },
    "flujo.titulo_pausa2": {
        "es": "Revisión de Código Desarrollado (Pausa 2)",
        "en": "Developed Code Review (Pause 2)",
    },
    "flujo.titulo_feedback_plan": {
        "es": "Plan de Acción (Feedback del Usuario Recibido)",
        "en": "Action Plan (User Feedback Received)",
    },
    "flujo.titulo_feedback_codigo": {
        "es": "Revisión de Código (Feedback del Usuario Recibido)",
        "en": "Code Review (User Feedback Received)",
    },
    "flujo.plan_default": {
        "es": "Plan de acción propuesto por el equipo de IA.",
        "en": "Action plan proposed by the AI team.",
    },
    "flujo.plan_default_feedback": {
        "es": "Plan de acción propuesto.",
        "en": "Action plan proposed.",
    },
    "flujo.sin_resumen": {
        "es": "No se registró un resumen de cambios.",
        "en": "No change summary was recorded.",
    },
    "flujo.sin_codigo": {"es": "No se reportó código.", "en": "No code was reported."},
    "flujo.sin_errores": {"es": "Sin errores.", "en": "No errors."},
    "flujo.pausa1_msg": {
        "es": "⏸️ PAUSA 1: Plan de acción listo. Esperando revisión del usuario (tarea '{tarea_id}').\n\n{markdown}",
        "en": "⏸️ PAUSE 1: Action plan ready. Waiting for user review (task '{tarea_id}').\n\n{markdown}",
    },
    "flujo.pausa2_msg": {
        "es": "⏸️ PAUSA 2: Código escrito. Esperando aprobación antes de pruebas QA (tarea '{tarea_id}').\n\n{markdown}",
        "en": "⏸️ PAUSE 2: Code written. Waiting for approval before QA tests (task '{tarea_id}').\n\n{markdown}",
    },
    "flujo.feedback_pausa1_log": {
        "es": "↩️ Feedback recibido. Re-pausando con instrucciones claras para el usuario.",
        "en": "↩️ Feedback received. Re-pausing with clear instructions for the user.",
    },
    "flujo.feedback_pausa2_log": {
        "es": "↩️ Feedback recibido. Re-pausando Pausa 2 con instrucciones claras para el usuario.",
        "en": "↩️ Feedback received. Re-pausing Pause 2 with clear instructions for the user.",
    },
    "flujo.auto_aprobacion": {
        "es": "⚡ Auto-aprobación activa: reanudando automáticamente en nodo '{nodo}' (tarea '{tarea_id}')...",
        "en": "⚡ Auto-approval active: automatically resuming at node '{nodo}' (task '{tarea_id}')...",
    },
    "flujo.iniciando_planificador": {
        "es": "🏗️ Iniciando Agente Planificador (Arquitecto) para '{instruccion}...'...",
        "en": "🏗️ Starting Planner Agent (Architect) for '{instruccion}...'...",
    },
    "flujo.completada": {
        "es": "✅ Tarea '{tarea_id}' completada exitosamente.",
        "en": "✅ Task '{tarea_id}' completed successfully.",
    },
    "flujo.cambios_finales": {
        "es": "\n\n🔍 Cambios en disco finales:\n{diff}",
        "en": "\n\n🔍 Final on-disk changes:\n{diff}",
    },
    "flujo.advertencia_sin_cambios": {
        "es": "\n\n⚠️ ADVERTENCIA: No se detectaron cambios ni modificaciones en los archivos del disco (git diff / status está vacío).",
        "en": "\n\n⚠️ WARNING: No changes or modifications were detected in the on-disk files (git diff / status is empty).",
    },
    "flujo.analisis_completado": {
        "es": "✅ Análisis completado por el equipo LangGraph.\nID de Tarea: {tarea_id}\n\n📋 REPORTE DE ANÁLISIS:\n{analisis}",
        "en": "✅ Analysis completed by the LangGraph team.\nTask ID: {tarea_id}\n\n📋 ANALYSIS REPORT:\n{analisis}",
    },
    "flujo.reporte_final": {
        "es": (
            "✅ Tarea completada exitosamente por el equipo LangGraph.\n"
            "ID de Tarea: {tarea_id}\n"
            "Resumen de cambios: {resumen}\n"
            "Estado final de los tests (QA): {errores}"
        ),
        "en": (
            "✅ Task completed successfully by the LangGraph team.\n"
            "Task ID: {tarea_id}\n"
            "Change summary: {resumen}\n"
            "Final test status (QA): {errores}"
        ),
    },
    "flujo.advertencia_diff_vacio": {
        "es": "\n\n⚠️ ADVERTENCIA: La tarea finalizó pero git diff no muestra modificaciones en '{directorio}'. Comprueba si el Agente Codificador omitió la escritura de archivos.",
        "en": "\n\n⚠️ WARNING: The task finished but git diff shows no modifications in '{directorio}'. Check whether the Coder Agent skipped writing files.",
    },
    "flujo.timeout": {
        "es": "🚨 Timeout: La tarea '{tarea_id}' excedió el límite máximo de ejecución ({segundos}s).",
        "en": "🚨 Timeout: Task '{tarea_id}' exceeded the maximum execution limit ({segundos}s).",
    },
    "flujo.timeout_consejo": {
        "es": " Por favor, reintenta dividiendo la instrucción en pasos más específicos o verifica el estado de la tarea con tarea_id='{tarea_id}'.",
        "en": " Please retry by splitting the instruction into more specific steps or check the task status with tarea_id='{tarea_id}'.",
    },
    "flujo.error_interno": {
        "es": "🚨 El equipo de agentes falló con un error interno en tarea '{tarea_id}': {error}",
        "en": "🚨 The agent team failed with an internal error on task '{tarea_id}': {error}",
    },
    "flujo.consultando_cambios": {
        "es": "🔍 Consultando cambios para tarea '{tarea_id}' en '{directorio}'...",
        "en": "🔍 Checking changes for task '{tarea_id}' in '{directorio}'...",
    },
    "flujo.resumen_cambios": {
        "es": "📋 RESUMEN DE CAMBIOS (Tarea '{tarea_id}'):\n{resumen}",
        "en": "📋 CHANGE SUMMARY (Task '{tarea_id}'):\n{resumen}",
    },
    "flujo.tarea_sin_resumen": {
        "es": "ℹ️ La tarea '{tarea_id}' aún no ha registrado un resumen de cambios.",
        "en": "ℹ️ Task '{tarea_id}' has not registered a change summary yet.",
    },
    "flujo.estado_pausado_nodo": {
        "es": "📌 Estado actual del flujo: Pausado antes de '{nodo}'",
        "en": "📌 Current flow status: Paused before '{nodo}'",
    },
    "flujo.estado_finalizado": {
        "es": "📌 Estado actual del flujo: Finalizado",
        "en": "📌 Current flow status: Finished",
    },
    "flujo.error_estado": {
        "es": "⚠️ No se pudo obtener el estado de la tarea '{tarea_id}': {error}",
        "en": "⚠️ Could not get the status of task '{tarea_id}': {error}",
    },
    "flujo.cambios_disco": {
        "es": "🔍 CAMBIOS DETALLADOS EN DISCO (Git Diff / Status en '{directorio}'):\n{diff}",
        "en": "🔍 DETAILED ON-DISK CHANGES (Git Diff / Status in '{directorio}'):\n{diff}",
    },
    "flujo.sin_cambios_params": {
        "es": "⚠️ No se encontraron cambios para los parámetros proporcionados.",
        "en": "⚠️ No changes were found for the provided parameters.",
    },
    "flujo.sin_parametros_validos": {
        "es": "No se proporcionó un 'tarea_id' válido ni un 'directorio_proyecto' con cambios detectables.",
        "en": "No valid 'tarea_id' or 'directorio_proyecto' with detectable changes was provided.",
    },
    "flujo.visualizacion_completada": {
        "es": "✅ Visualización de cambios completada.",
        "en": "✅ Change visualization completed.",
    },
    # -------------------------------------------------------------------- git
    "git.archivos_modificados": {
        "es": "Archivos modificados/creados (git status):\n{status}",
        "en": "Modified/created files (git status):\n{status}",
    },
    # ----------------------------------------------------------------- estado
    "estado.consultando": {
        "es": "🔍 Consultando estado de la tarea '{tarea_id}'...",
        "en": "🔍 Checking status of task '{tarea_id}'...",
    },
    "estado.registrado_titulo": {
        "es": "### 📌 Estado registrado de la tarea '{tarea_id}'",
        "en": "### 📌 Registered status of task '{tarea_id}'",
    },
    "estado.campo_estado": {
        "es": "- **Estado:** `{estado}`",
        "en": "- **Status:** `{estado}`",
    },
    "estado.campo_directorio": {
        "es": "- **Directorio:** `{directorio}`",
        "en": "- **Directory:** `{directorio}`",
    },
    "estado.campo_actualizacion": {
        "es": "- **Última actualización:** `{timestamp}`",
        "en": "- **Last updated:** `{timestamp}`",
    },
    "estado.campo_detalle": {
        "es": "- **Detalle:** {detalle}",
        "en": "- **Detail:** {detalle}",
    },
    "estado.no_registrada": {
        "es": "ℹ️ La tarea '{tarea_id}' no está registrada en el TaskRegistry (puede que aún no se haya iniciado o que haya sido eliminada).",
        "en": "ℹ️ Task '{tarea_id}' is not registered in the TaskRegistry (it may not have started yet or may have been deleted).",
    },
    "estado.error_grafo": {
        "es": "⚠️ No se pudo obtener el estado del grafo: {error}",
        "en": "⚠️ Could not get the graph status: {error}",
    },
    "estado.consulta_completada": {
        "es": "✅ Consulta de estado completada.",
        "en": "✅ Status query completed.",
    },
    "estado.error_consulta": {
        "es": "⚠️ Error al consultar el estado de la tarea '{tarea_id}': {error}",
        "en": "⚠️ Error querying the status of task '{tarea_id}': {error}",
    },
    # ----------------------------------------------------------------- listar
    "listar.listando": {
        "es": "📋 Listando tareas registradas...",
        "en": "📋 Listing registered tasks...",
    },
    "listar.titulo": {
        "es": "### 📋 Tareas Registradas",
        "en": "### 📋 Registered Tasks",
    },
    "listar.encabezado_tabla": {
        "es": "| tarea_id | estado | directorio_proyecto | última actualización |",
        "en": "| task_id | status | project_directory | last updated |",
    },
    "listar.vacio": {
        "es": "ℹ️ No hay tareas registradas{filtro}.",
        "en": "ℹ️ There are no registered tasks{filtro}.",
    },
    "listar.filtro_estado": {
        "es": " con estado '{estado}'",
        "en": " with status '{estado}'",
    },
    "listar.encontradas": {
        "es": "✅ Se encontraron {cantidad} tareas.",
        "en": "✅ Found {cantidad} tasks.",
    },
    "listar.error": {
        "es": "⚠️ Error al listar las tareas: {error}",
        "en": "⚠️ Error listing tasks: {error}",
    },
    # ---------------------------------------------------------------- cancelar
    "cancelar.intentando": {
        "es": "🛑 Intentando cancelar la tarea '{tarea_id}'...",
        "en": "🛑 Trying to cancel task '{tarea_id}'...",
    },
    "cancelar.no_encontrada": {
        "es": "⚠️ No se encontró la tarea '{tarea_id}' en el registro. No se puede cancelar.",
        "en": "⚠️ Task '{tarea_id}' was not found in the registry. It cannot be cancelled.",
    },
    "cancelar.detalle": {
        "es": "Cancelada por el usuario",
        "en": "Cancelled by the user",
    },
    "cancelar.interrumpida": {
        "es": "✅ Tarea '{tarea_id}' marcada como cancelada y su ejecución en curso fue interrumpida.",
        "en": "✅ Task '{tarea_id}' marked as cancelled and its running execution was interrupted.",
    },
    "cancelar.cancelada_sin_interrumpir": {
        "es": "✅ Tarea '{tarea_id}' marcada como cancelada (no se pudo interrumpir la ejecución en curso).",
        "en": "✅ Task '{tarea_id}' marked as cancelled (the running execution could not be interrupted).",
    },
    "cancelar.cancelada": {
        "es": "✅ Tarea '{tarea_id}' marcada como cancelada en el registro.",
        "en": "✅ Task '{tarea_id}' marked as cancelled in the registry.",
    },
    "cancelar.error": {
        "es": "⚠️ Error al cancelar la tarea '{tarea_id}': {error}",
        "en": "⚠️ Error cancelling task '{tarea_id}': {error}",
    },
    # ------------------------------------------------------------------ index
    "index.directorio_no_existe": {
        "es": "El directorio '{directorio}' no existe.",
        "en": "The directory '{directorio}' does not exist.",
    },
    "index.ruta_directorio_propio": {
        "es": "Error: La ruta '{ruta}' apunta al propio directorio del proyecto.",
        "en": "Error: The path '{ruta}' points to the project directory itself.",
    },
    "index.ruta_fuera_proyecto": {
        "es": "Error: La ruta '{ruta}' está fuera del directorio del proyecto.",
        "en": "Error: The path '{ruta}' is outside the project directory.",
    },
    "index.archivo_no_existe": {
        "es": "Error: El archivo '{ruta}' no existe.",
        "en": "Error: The file '{ruta}' does not exist.",
    },
    # ------------------------------------------------------------------ files
    "files.ruta_requerida": {
        "es": "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path').",
        "en": "Error: You must provide a file path ('file_path' or 'path').",
    },
    "files.contenido_requerido": {
        "es": "Error: Debes proporcionar el contenido del archivo ('text' o 'content').",
        "en": "Error: You must provide the file content ('text' or 'content').",
    },
    "files.origen_requerido": {
        "es": "Error: Debes proporcionar el archivo origen ('source_path' o 'source').",
        "en": "Error: You must provide the source file ('source_path' or 'source').",
    },
    "files.destino_requerido": {
        "es": "Error: Debes proporcionar el destino ('destination_path', 'destination' o 'dest').",
        "en": "Error: You must provide the destination ('destination_path', 'destination' or 'dest').",
    },
    "files.new_text_requerido": {
        "es": "Error: Debes proporcionar 'new_text' cuando usas 'old_text'.",
        "en": "Error: You must provide 'new_text' when using 'old_text'.",
    },
    "files.modo_requerido": {
        "es": "Error: Debes proporcionar 'old_text' o 'line_start' para editar el archivo.",
        "en": "Error: You must provide 'old_text' or 'line_start' to edit the file.",
    },
    "files.no_existe": {
        "es": "Error: El archivo '{ruta}' no existe.",
        "en": "Error: The file '{ruta}' does not exist.",
    },
    "files.no_existe_ruta": {
        "es": "Error: El archivo '{ruta}' no existe en '{ruta_completa}'.",
        "en": "Error: The file '{ruta}' does not exist in '{ruta_completa}'.",
    },
    "files.directorio_no_existe": {
        "es": "Error: El directorio '{ruta}' no existe.",
        "en": "Error: The directory '{ruta}' does not exist.",
    },
    "files.no_es_directorio": {
        "es": "Error: '{ruta}' no es un directorio.",
        "en": "Error: '{ruta}' is not a directory.",
    },
    "files.es_directorio": {
        "es": "Error: '{ruta}' es un directorio, no un archivo.",
        "en": "Error: '{ruta}' is a directory, not a file.",
    },
    "files.directorio_vacio": {
        "es": "El directorio '{ruta}' esta vacio.",
        "en": "The directory '{ruta}' is empty.",
    },
    "files.texto_no_encontrado": {
        "es": "Error: No se encontró el texto a reemplazar en '{ruta}'.",
        "en": "Error: The text to replace was not found in '{ruta}'.",
    },
    "files.line_start_fuera_rango": {
        "es": "Error: 'line_start' ({line_start}) fuera de rango (1..{total}).",
        "en": "Error: 'line_start' ({line_start}) out of range (1..{total}).",
    },
    "files.line_end_fuera_rango": {
        "es": "Error: 'line_end' ({line_end}) fuera de rango (1..{total}).",
        "en": "Error: 'line_end' ({line_end}) out of range (1..{total}).",
    },
    "files.ruta_escapa": {
        "es": "Error: la ruta '{ruta}' escapa del directorio del proyecto ('{base}').",
        "en": "Error: the path '{ruta}' escapes the project directory ('{base}').",
    },
    "files.truncado": {
        "es": "\n[...truncado a {max_lines} líneas]",
        "en": "\n[...truncated to {max_lines} lines]",
    },
    "files.indice_deshabilitado": {
        "es": "Índice del proyecto deshabilitado (PROJECT_INDEX_ENABLED=False).",
        "en": "Project index disabled (PROJECT_INDEX_ENABLED=False).",
    },
    "files.escrito_ok": {
        "es": "Archivo '{ruta}' escrito exitosamente en '{ruta_completa}'.",
        "en": "File '{ruta}' written successfully to '{ruta_completa}'.",
    },
    "files.editado_ok": {
        "es": "Archivo '{ruta}' editado exitosamente.",
        "en": "File '{ruta}' edited successfully.",
    },
    "files.eliminado_ok": {
        "es": "Archivo '{ruta}' eliminado exitosamente.",
        "en": "File '{ruta}' deleted successfully.",
    },
    "files.copiado_ok": {
        "es": "Copiado de '{origen}' a '{destino}' exitosamente.",
        "en": "Copied from '{origen}' to '{destino}' successfully.",
    },
    "files.movido_ok": {
        "es": "Movido de '{origen}' a '{destino}' exitosamente.",
        "en": "Moved from '{origen}' to '{destino}' successfully.",
    },
    "files.resumen_ok": {
        "es": "RESUMEN del archivo '{ruta}':\n\n{texto_resumen}",
        "en": "SUMMARY of file '{ruta}':\n\n{texto_resumen}",
    },
    "files.error_escribir": {
        "es": "Error al escribir el archivo '{ruta}': {error}",
        "en": "Error writing file '{ruta}': {error}",
    },
    "files.error_editar": {
        "es": "Error al editar el archivo '{ruta}': {error}",
        "en": "Error editing file '{ruta}': {error}",
    },
    "files.error_leer": {
        "es": "Error al leer el archivo '{ruta}': {error}",
        "en": "Error reading file '{ruta}': {error}",
    },
    "files.error_listar": {
        "es": "Error al listar el directorio '{ruta}': {error}",
        "en": "Error listing directory '{ruta}': {error}",
    },
    "files.error_indice": {
        "es": "Error al construir el indice del proyecto: {error}",
        "en": "Error building the project index: {error}",
    },
    "files.error_resumir": {
        "es": "Error al resumir el archivo '{ruta}': {error}",
        "en": "Error summarizing file '{ruta}': {error}",
    },
    "files.error_eliminar": {
        "es": "Error al eliminar el archivo '{ruta}': {error}",
        "en": "Error deleting file '{ruta}': {error}",
    },
    "files.error_copiar": {
        "es": "Error al copiar de '{origen}' a '{destino}': {error}",
        "en": "Error copying from '{origen}' to '{destino}': {error}",
    },
    "files.error_mover": {
        "es": "Error al mover de '{origen}' a '{destino}': {error}",
        "en": "Error moving from '{origen}' to '{destino}': {error}",
    },
    # ------------------------------------------------------------------ shell
    "shell.borrado_rm_rf": {
        "es": "borrado destructivo con 'rm -rf' sobre rutas raíz o del sistema",
        "en": "destructive deletion with 'rm -rf' on root or system paths",
    },
    "shell.borrado_rd_s_q": {
        "es": "borrado destructivo de árboles de directorios con rd/rmdir /s /q",
        "en": "destructive deletion of directory trees with rd/rmdir /s /q",
    },
    "shell.borrado_del_f_s_q": {
        "es": "borrado destructivo de archivos con del /f /s /q",
        "en": "destructive file deletion with del /f /s /q",
    },
    "shell.borrado_rutas_windows": {
        "es": "borrado destructivo de rutas Windows fuera del proyecto (unidad del sistema)",
        "en": "destructive deletion of Windows paths outside the project (system drive)",
    },
    "shell.borrado_remove_item": {
        "es": "borrado destructivo con Remove-Item -Recurse (PowerShell)",
        "en": "destructive deletion with Remove-Item -Recurse (PowerShell)",
    },
    "shell.descarga_ejecucion_remota": {
        "es": "descarga y ejecución de código remoto (curl/wget redirigido a shell)",
        "en": "remote code download and execution (curl/wget piped to shell)",
    },
    "shell.descarga_powershell": {
        "es": "descarga y ejecución en PowerShell (iex/iwr)",
        "en": "download and execution in PowerShell (iex/iwr)",
    },
    "shell.git_push_force": {
        "es": "forzado de push remoto en git (--force)",
        "en": "forced push to remote in git (--force)",
    },
    "shell.git_reset_hard": {
        "es": "reset destructivo del árbol de trabajo en git (--hard)",
        "en": "destructive reset of the git working tree (--hard)",
    },
    "shell.git_clean_fdx": {
        "es": "limpieza forzada de archivos no rastreados con git clean -fdx",
        "en": "forced cleanup of untracked files with git clean -fdx",
    },
    "shell.git_checkout_hard": {
        "es": "restauración destructiva forzada con git checkout/restore --hard",
        "en": "forced destructive restore with git checkout/restore --hard",
    },
    "shell.variables_criticas": {
        "es": "modificación de variables críticas del entorno (PATH/LD_PRELOAD/PYTHONPATH...)",
        "en": "modification of critical environment variables (PATH/LD_PRELOAD/PYTHONPATH...)",
    },
    "shell.archivos_sensibles": {
        "es": "acceso a archivos sensibles de sistema (/etc/shadow, /etc/passwd, ...)",
        "en": "access to sensitive system files (/etc/shadow, /etc/passwd, ...)",
    },
    "shell.credenciales_ssh": {
        "es": "acceso a credenciales de SSH (~/.ssh)",
        "en": "access to SSH credentials (~/.ssh)",
    },
    "shell.credenciales_nube": {
        "es": "acceso a credenciales de nube o claves privadas",
        "en": "access to cloud credentials or private keys",
    },
    "shell.credenciales_api": {
        "es": "lectura o modificación de credenciales (api_key, secret, password)",
        "en": "reading or modifying credentials (api_key, secret, password)",
    },
    "shell.lectura_env": {
        "es": "lectura de archivos .env con credenciales",
        "en": "reading .env files with credentials",
    },
    "shell.fork_bomb": {
        "es": "bomba de procesos (fork bomb)",
        "en": "process bomb (fork bomb)",
    },
    "shell.apagado_sistema": {
        "es": "apagado, reinicio o suspensión del sistema",
        "en": "system shutdown, reboot or suspension",
    },
    "shell.init_nivel": {
        "es": "cambio de nivel de ejecución del sistema (init 0/6)",
        "en": "system runlevel change (init 0/6)",
    },
    "shell.comando_vacio": {
        "es": "Comando vacío.",
        "en": "Empty command.",
    },
    "shell.comando_bloqueado": {
        "es": "Comando bloqueado: {motivo}.",
        "en": "Command blocked: {motivo}.",
    },
    "shell.escape_traversal": {
        "es": "Comando bloqueado: intento de escape del directorio del proyecto con '..' (traversal).",
        "en": "Command blocked: attempt to escape the project directory with '..' (traversal).",
    },
    "shell.cwd_invalido": {
        "es": "Comando bloqueado: el directorio de trabajo del proyecto no es válido.",
        "en": "Command blocked: the project working directory is not valid.",
    },
    "shell.ruta_fuera_proyecto": {
        "es": "Comando bloqueado: la ruta absoluta '{token}' está fuera del directorio del proyecto.",
        "en": "Command blocked: the absolute path '{token}' is outside the project directory.",
    },
    # ---------------------------------------------------------------- ledger
    "ledger.pasos_completos": {
        "es": "Pasos completos: {lista}",
        "en": "Completed steps: {lista}",
    },
    "ledger.paso_actual": {
        "es": "Paso actual: {paso_actual} de {total}",
        "en": "Current step: {paso_actual} of {total}",
    },
    "ledger.todos_completos": {
        "es": "Todos los pasos completos ({total} de {total})",
        "en": "All steps completed ({total} of {total})",
    },
    "ledger.pendientes": {
        "es": "Pendientes: {lista}",
        "en": "Pending: {lista}",
    },
    "ledger.pendientes_ninguno": {
        "es": "ninguno",
        "en": "none",
    },
    "ledger.contexto_todos_completos": {
        "es": "Todos los pasos están completos y verificados. Si ya escribiste todos los archivos en disco, invoca CodigoCompletado.",
        "en": "All steps are completed and verified. If you have already written all the files to disk, invoke CodigoCompletado.",
    },
    "ledger.contexto_paso_actual": {
        "es": "--- PASO ACTUAL ({paso_actual} de {total}) ---",
        "en": "--- CURRENT STEP ({paso_actual} of {total}) ---",
    },
}


def obtener_mensaje(clave: str, idioma: str = "es", **kwargs: Any) -> str:
    """Resuelve la plantilla de MENSAJES para la clave e idioma dados.

    Si la clave no existe retorna la propia clave; si el formateo falla por
    kwargs faltantes, retorna la plantilla sin formatear.
    """
    plantillas = MENSAJES.get(clave)
    if plantillas is None:
        return clave
    plantilla = plantillas.get(normalizar_idioma(idioma)) or plantillas.get("es") or clave
    if not kwargs:
        return plantilla
    try:
        return plantilla.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return plantilla