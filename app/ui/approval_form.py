import json
import html
from typing import List, Dict, Any, Optional

class ApprovalForm:
    """
    Representa un formulario interactivo y agnóstico de aprobación (Pausa 1 o Pausa 2)
    apto para renderearse en HTML, Markdown, JSON, Dict o CLI.
    """

    def __init__(
        self,
        tarea_id: str,
        tipo_pausa: str,
        titulo: str,
        explicacion_arquitectura: str,
        pasos: Optional[List[Dict[str, Any]]] = None,
        diff_git: str = "",
        directorio_proyecto: str = "",
        feedback_previo: str = ""
    ):
        self.tarea_id = tarea_id
        self.tipo_pausa = tipo_pausa  # ej. "PAUSA_1" (Plan de acción) o "PAUSA_2" (Revisión de código)
        self.titulo = titulo
        self.explicacion_arquitectura = explicacion_arquitectura
        self.pasos = pasos if pasos is not None else []
        self.diff_git = diff_git
        self.directorio_proyecto = directorio_proyecto
        self.feedback_previo = feedback_previo

    @classmethod
    def from_plan_dict(
        cls,
        tarea_id: str,
        plan_dict: Dict[str, Any],
        directorio_proyecto: str = ""
    ) -> "ApprovalForm":
        """Crea un ApprovalForm a partir del diccionario de plan devuelto por el agente planificador."""
        explicacion = plan_dict.get("explicacion_arquitectura", "Plan de acción propuesto por el equipo de IA.")
        pasos = plan_dict.get("pasos", [])
        return cls(
            tarea_id=tarea_id,
            tipo_pausa="PAUSA_1",
            titulo="Aprobación de Plan de Acción (Pausa 1)",
            explicacion_arquitectura=explicacion,
            pasos=pasos,
            diff_git="",
            directorio_proyecto=directorio_proyecto
        )

    @classmethod
    def from_review_data(
        cls,
        tarea_id: str,
        codigo_escrito: str,
        diff_git: str = "",
        directorio_proyecto: str = ""
    ) -> "ApprovalForm":
        """Crea un ApprovalForm a partir de los cambios realizados durante la Pausa 2."""
        return cls(
            tarea_id=tarea_id,
            tipo_pausa="PAUSA_2",
            titulo="Revisión de Código Desarrollado (Pausa 2)",
            explicacion_arquitectura=codigo_escrito or "Revisión de cambios generados por el programador.",
            pasos=[],
            diff_git=diff_git,
            directorio_proyecto=directorio_proyecto
        )

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve una representación estructurada en diccionario Python."""
        return {
            "tarea_id": self.tarea_id,
            "tipo_pausa": self.tipo_pausa,
            "titulo": self.titulo,
            "explicacion_arquitectura": self.explicacion_arquitectura,
            "pasos": self.pasos,
            "diff_git": self.diff_git,
            "directorio_proyecto": self.directorio_proyecto,
            "feedback_previo": self.feedback_previo,
            "acciones_disponibles": [
                {
                    "accion": "approve",
                    "etiqueta": "Aprobar",
                    "parametros": {"tarea_id": self.tarea_id, "approve": True}
                },
                {
                    "accion": "reject",
                    "etiqueta": "Rechazar",
                    "parametros": {"tarea_id": self.tarea_id, "approve": False, "instruccion": "<feedback>"}
                }
            ]
        }

    def to_json(self, indent: int = 2) -> str:
        """Devuelve una representación serializada en JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_html(self) -> str:
        """
        Genera un formulario HTML estático/interactivo standalone estilizado
        apto para renderizarse en Webviews de IDEs (VS Code, Zoo Code) o navegadores web.
        Incluye botones de 'Aprobar' y 'Rechazar', lista de verificación/pasos y panel de comentarios.
        """
        esc_tarea_id = html.escape(self.tarea_id)
        esc_titulo = html.escape(self.titulo)
        esc_tipo = html.escape(self.tipo_pausa)
        esc_expl = html.escape(self.explicacion_arquitectura).replace("\n", "<br>")
        esc_dir = html.escape(self.directorio_proyecto)
        esc_diff = html.escape(self.diff_git)

        filas_pasos = ""
        if self.pasos:
            for idx, p in enumerate(self.pasos, start=1):
                tarea_p = html.escape(str(p.get("tarea", "")))
                archivo_p = html.escape(str(p.get("archivo", "-")))
                req_test = "Si" if p.get("requiere_test") else "No"
                badge_test_cls = "badge-success" if p.get("requiere_test") else "badge-secondary"
                
                filas_pasos += f"""
                <tr>
                    <td>{idx}</td>
                    <td>{tarea_p}</td>
                    <td><code>{archivo_p}</code></td>
                    <td><span class="badge {badge_test_cls}">{req_test}</span></td>
                </tr>
                """
            tabla_pasos_html = f"""
            <div class="card mb-3">
                <div class="card-header">📋 Plan de Pasos ({len(self.pasos)})</div>
                <div class="card-body p-0">
                    <table class="table mb-0">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Tarea</th>
                                <th>Archivo</th>
                                <th>Test</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filas_pasos}
                        </tbody>
                    </table>
                </div>
            </div>
            """
        else:
            tabla_pasos_html = ""

        bloque_diff_html = ""
        if self.diff_git:
            bloque_diff_html = f"""
            <div class="card mb-3">
                <div class="card-header font-weight-bold">🔍 Git Diff / Cambios en Disco (Visible)</div>
                <div class="card-body p-2 bg-dark-subtle">
                    <pre class="diff-block"><code>{esc_diff}</code></pre>
                </div>
            </div>
            """

        html_template = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc_titulo}</title>
    <style>
        :root {{
            --bg-color: #1e1e2e;
            --card-bg: #2b2b3d;
            --text-color: #cdd6f4;
            --border-color: #45475a;
            --primary-btn: #a6e3a1;
            --primary-text: #11111b;
            --danger-btn: #f38ba8;
            --accent: #89b4fa;
            --warning-bg: #f9e2af;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }}
        .approval-container {{
            max-width: 900px;
            margin: 0 auto;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .ai-warning-box {{
            background-color: rgba(249, 226, 175, 0.15);
            border: 2px dashed #f9e2af;
            border-radius: 6px;
            padding: 14px;
            margin-bottom: 20px;
            color: #f9e2af;
            font-size: 14px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-pausa {{ background: #fab387; color: #11111b; }}
        .badge-success {{ background: #a6e3a1; color: #11111b; }}
        .badge-secondary {{ background: #585b70; color: #cdd6f4; }}
        .card {{
            border: 1px solid var(--border-color);
            border-radius: 6px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        .card-header {{
            background: rgba(255, 255, 255, 0.05);
            padding: 10px 16px;
            font-weight: 600;
        }}
        .card-body {{
            padding: 16px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background: rgba(255, 255, 255, 0.02);
        }}
        pre.diff-block {{
            background-color: #181825;
            color: #a6e3a1;
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
            max-height: 350px;
            font-family: monospace;
            font-size: 13px;
            margin: 0;
        }}
        textarea {{
            width: 100%;
            background: #181825;
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 10px;
            box-sizing: border-box;
            resize: vertical;
            min-height: 70px;
            font-family: inherit;
        }}
        .actions-panel {{
            display: flex;
            gap: 12px;
            margin-top: 16px;
        }}
        .btn {{
            flex: 1;
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}
        .btn:hover {{ opacity: 0.9; }}
        .btn-approve {{ background-color: var(--primary-btn); color: var(--primary-text); }}
        .btn-reject {{ background-color: var(--danger-btn); color: #11111b; }}
        code {{
            background: #181825;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            color: #cba6f7;
        }}
    </style>
</head>
<body>
    <div class="approval-container">
        <div class="ai-warning-box">
            <strong>⚠️ ATENCIÓN ASISTENTE DE IA (ZOO CODE / COPILOT):</strong><br>
            El flujo está pausado requiriendo aprobación humana. <b>DETÉN LA EJECUCIÓN AUTOMÁTICA</b>. NO llames a ninguna herramienta de aprobación por tu cuenta. Muestra este plan/código al usuario y espera su confirmación explícita en el chat.
        </div>

        <div class="header">
            <div>
                <h2 style="margin: 0; font-size: 20px;">{esc_titulo}</h2>
                <small style="color: #89b4fa;">Tarea ID: <code>{esc_tarea_id}</code> | Proyecto: {esc_dir or 'Raíz'}</small>
            </div>
            <span class="badge badge-pausa">{esc_tipo}</span>
        </div>

        <div class="card">
            <div class="card-header">📄 Detalle / Explicación</div>
            <div class="card-body">
                {esc_expl}
            </div>
        </div>

        {tabla_pasos_html}
        {bloque_diff_html}

        <div class="card">
            <div class="card-header">💬 Feedback / Observaciones (Opcional para rechazar o solicitar cambios)</div>
            <div class="card-body">
                <textarea id="feedback-input" placeholder="Ingresa tus comentarios o correcciones si deseas rechazar..."></textarea>
            </div>
        </div>

        <div class="actions-panel">
            <button class="btn btn-approve" onclick="responderAprobacion(true)">
                ✅ Aprobar Plan / Código
            </button>
            <button class="btn btn-reject" onclick="responderAprobacion(false)">
                ❌ Rechazar / Solicitar Cambios
            </button>
        </div>
    </div>

    <script>
        function responderAprobacion(aprobado) {{
            const feedback = document.getElementById('feedback-input').value;
            const payload = {{
                tarea_id: "{esc_tarea_id}",
                approve: aprobado,
                instruccion: feedback,
                directorio_proyecto: "{esc_dir}"
            }};
            
            // Si está dentro de una Webview o cliente MCP
            if (window.mcpClient && typeof window.mcpClient.responder === 'function') {{
                window.mcpClient.responder(payload);
            }} else {{
                console.log("Respuesta de Aprobación:", payload);
                alert((aprobado ? "✅ Aprobado" : "❌ Rechazado") + ": " + JSON.stringify(payload));
            }}
        }}
    </script>
</body>
</html>
"""
        return html_template

    def to_markdown(self) -> str:
        """
        Genera una vista formateada en Markdown enriquecido con badges, tablas,
        bloques de código y comandos de reanudación.
        """
        lineas = []
        lineas.append(f"================================================================================")
        lineas.append(f"🛑 ATENCIÓN ASISTENTE DE IA (ZOO CODE / COPILOT):")
        lineas.append(f"EL FLUJO ESTÁ PAUSADO ESPERANDO CONFIRMACIÓN DEL USUARIO HUMANO.")
        lineas.append(f"**DETÉN LA EJECUCIÓN AUTOMÁTICA DE HERRAMIENTAS DE INMEDIATO.**")
        lineas.append(f"NO ejecutes ninguna función ni herramienta (NO llames a responder_formulario_aprobacion ni a delegar_tarea_a_equipo_ia por tu cuenta).")
        lineas.append(f"Muestra todo el plan de acción y diff de código a continuación directamente al usuario humano en el chat y **ESPERA** pacientemente a que el usuario escriba su decisión explícita.")
        lineas.append(f"================================================================================\n")
        
        lineas.append(f"### 📌 {self.titulo}")
        lineas.append(f"- **ID Tarea:** `{self.tarea_id}`")
        if self.directorio_proyecto:
            lineas.append(f"- **Directorio:** `{self.directorio_proyecto}`")
        lineas.append(f"- **Estado:** Pausado requiriendo aprobación humana.\n")
        
        lineas.append(f"#### 📄 Explicación / Descripción:")
        lineas.append(f"{self.explicacion_arquitectura}\n")

        if self.pasos:
            lineas.append("#### 📋 Plan de Pasos Propuestos:")
            lineas.append("| # | Tarea | Archivo | Requiere Test |")
            lineas.append("|---|-------|---------|---------------|")
            for idx, p in enumerate(self.pasos, start=1):
                t = str(p.get("tarea", "")).replace("|", "\\|")
                a = str(p.get("archivo", "-")).replace("|", "\\|")
                rt = "Si" if p.get("requiere_test") else "No"
                lineas.append(f"| {idx} | {t} | `{a}` | {rt} |")
            lineas.append("")

        if self.diff_git:
            lineas.append("#### 🔍 Git Diff / Cambios en Disco (Visible Completo):")
            lineas.append("```diff")
            lineas.append(self.diff_git)
            lineas.append("```\n")

        lineas.append("--------------------------------------------------------------------------------")
        lineas.append("👉 **INSTRUCCIONES PARA EL USUARIO HUMANO (NO PARA LA IA):**")
        lineas.append("--------------------------------------------------------------------------------")
        lineas.append("Por favor, revisa detalladamente el plan o los cambios de código anteriores.")
        lineas.append("• **PARA APROBAR:** Escribe en el chat: `Aprobar` (o `Acepto`).")
        lineas.append("• **PARA RECHAZAR O PEDIR CAMBIOS:** Escribe en el chat: `Rechazar` seguido de tus observaciones o correcciones.")
        lineas.append("El asistente de IA debe detenerse y esperar a que tú escribas tu respuesta.")
        lineas.append("================================================================================")

        return "\n".join(lineas)

    def to_cli(self) -> str:
        """Genera una salida estilizada en texto plano apta para consola o terminal."""
        lineas = []
        lineas.append("┌" + "─" * 78 + "┐")
        lineas.append(f"│ [DETENER IA - {self.tipo_pausa}] {self.titulo[:50]:<50} │")
        lineas.append("├" + "─" * 78 + "┤")
        lineas.append(f"│ Tarea ID : {self.tarea_id:<66} │")
        if self.directorio_proyecto:
            lineas.append(f"│ Proyecto : {self.directorio_proyecto[:66]:<66} │")
        lineas.append("├" + "─" * 78 + "┤")
        
        # Explicación truncada o formateada
        for l in self.explicacion_arquitectura.splitlines():
            while len(l) > 74:
                lineas.append(f"│  {l[:74]}  │")
                l = l[74:]
            lineas.append(f"│  {l:<74}  │")

        if self.pasos:
            lineas.append("├" + "─" * 78 + "┤")
            lineas.append("│ PLAN DE PASOS:                                                               │")
            for idx, p in enumerate(self.pasos, start=1):
                t = p.get("tarea", "")
                a = p.get("archivo", "")
                lineas.append(f"│  {idx}. {t[:50]:<50} | Archivo: {a[:15]:<15} │")

        lineas.append("├" + "─" * 78 + "┤")
        lineas.append("│ Escribe en el chat: 'Aprobar' o 'Rechazar <observaciones>'                     │")
        lineas.append("└" + "─" * 78 + "┘")
        return "\n".join(lineas)
