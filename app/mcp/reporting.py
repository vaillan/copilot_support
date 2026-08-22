"""Reporting en Markdown para el servidor MCP.

Este módulo contiene los helpers puros (con dependencia únicamente de
app.mcp.progress y app.mcp.git_utils) encargados de generar reportes Markdown
de pausa (generar_markdown_pausa) y de visualizar el estado de una tarea o los
cambios en disco (visualizar_cambios).

Nota: visualizar_cambios accede al grafo LangGraph (agentes_app) mediante IMPORT
PEREZOSO dentro de la función para evitar un import circular con mcp_server.py
y preservar los targets de patch de los tests existentes.
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastmcp import Context

from app.mcp.progress import notificar_progreso
from app.mcp.git_utils import obtener_git_diff


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

    # 1. Título principal y Metadatos de la Tarea en la parte superior prominente
    lineas.append(f"### 📌 {titulo}")
    lineas.append(f"- **ID Tarea:** `{tarea_id}`")
    if directorio_proyecto:
        lineas.append(f"- **Directorio:** `{directorio_proyecto}`")
    lineas.append(f"- **Estado:** Pausado ({tipo_pausa}) - Requiere aprobación humana.\n")

    # 2. Explicación / Resumen
    lineas.append("#### 📄 Explicación / Resumen:")
    lineas.append(f"{explicacion}\n")

    # 3. Plan de Pasos Propuestos (Tabla Markdown)
    if pasos:
        lineas.append("#### 📋 Plan de Pasos Propuestos:")
        lineas.append("| # | Tarea | Archivo | Requiere Test |")
        lineas.append("|---|-------|---------|---------------|")
        for idx, p in enumerate(pasos, start=1):
            t = str(p.get("tarea", "")).replace("|", "\\|")
            a = str(p.get("archivo", "-")).replace("|", "\\|")
            rt = "Si" if p.get("requiere_test") else "No"
            lineas.append(f"| {idx} | {t} | `{a}` | {rt} |")
        lineas.append("")

    # 4. Git Diff / Cambios en Disco (si existen)
    if diff_git:
        lineas.append("#### 🔍 Git Diff / Cambios en Disco:")
        lineas.append("```diff")
        lineas.append(diff_git)
        lineas.append("```\n")

    # 5. Bloque de advertencia para el asistente de IA (desplazado hacia la parte inferior)
    lineas.append("================================================================================")
    lineas.append("🛑 ATENCIÓN ASISTENTE DE IA (ZOO CODE / COPILOT / CURSOR):")
    lineas.append("EL FLUJO ESTÁ PAUSADO ESPERANDO CONFIRMACIÓN DEL USUARIO HUMANO.")
    lineas.append("**DETÉN LA EJECUCIÓN AUTOMÁTICA DE HERRAMIENTAS DE INMEDIATO.**")
    lineas.append("NO ejecutes ninguna función ni herramienta por tu cuenta.")
    lineas.append("Muestra todo el plan de acción y/o los cambios de código anteriores directamente al usuario humano en el chat y **ESPERA** pacientemente a que el usuario escriba su decisión explícita.")
    lineas.append("================================================================================\n")

    # 6. Instrucciones para el usuario humano (en la parte inferior)
    lineas.append("--------------------------------------------------------------------------------")
    lineas.append("👉 **INSTRUCCIONES PARA EL USUARIO HUMANO:**")
    lineas.append("--------------------------------------------------------------------------------")
    lineas.append("Por favor, revisa detalladamente el plan o los cambios de código anteriores.")
    lineas.append("• **PARA APROBAR:** Escribe en el chat que apruebas la tarea (ej. 'Aprobar' o 'Acepto').")
    lineas.append("• **PARA RECHAZAR O PEDIR CAMBIOS:** Escribe en el chat 'Rechazar' junto con tus observaciones o correcciones.")
    lineas.append("El asistente de IA debe detenerse y esperar a que tú escribas tu respuesta.")
    lineas.append("================================================================================")

    return "\n".join(lineas)


async def visualizar_cambios(
    tarea_id: str = "",
    directorio_proyecto: str = "",
    ctx: Optional[Context] = None
) -> str:
    """
    Función auxiliar interna para consultar el estado actual de una tarea o los cambios en disco.
    Nota: Ya no está expuesta como herramienta MCP para los agentes LLM.
    Accede al grafo mediante import perezoso de mcp_server.agentes_app para evitar
    import circular con mcp_server.py y preservar los targets de patch de los tests.
    """
    # Notificación fire-and-forget
    asyncio.create_task(
        notificar_progreso(
            ctx,
            f"🔍 Consultando cambios para tarea '{tarea_id}' en '{directorio_proyecto}'...",
            10,
            100,
        )
    )

    partes = []

    dir_a_consultar = directorio_proyecto

    if tarea_id:
        config = {"configurable": {"thread_id": tarea_id}}
        try:
            # Import perezoso para evitar import circular con mcp_server.py
            import mcp_server

            estado = await mcp_server.agentes_app.aget_state(config)  # type: ignore
            values = estado.values if hasattr(estado, "values") else {}

            if not dir_a_consultar:
                dir_a_consultar = values.get("directorio_proyecto", "")

            # Reporte de análisis (modo solo-análisis / reporte / arquitectura)
            analisis_final = values.get("analisis_final")
            if analisis_final:
                partes.append(
                    f"📋 REPORTE DE ANÁLISIS:\n{analisis_final}".strip()
                )

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
        asyncio.create_task(
            notificar_progreso(
                ctx, "⚠️ No se encontraron cambios para los parámetros proporcionados.", 100, 100
            )
        )
        return "No se proporcionó un 'tarea_id' válido ni un 'directorio_proyecto' con cambios detectables."

    asyncio.create_task(
        notificar_progreso(ctx, "✅ Visualización de cambios completada.", 100, 100)
    )
    return "\n\n".join(partes)