import json
import pytest
from app.ui.approval_form import ApprovalForm

def test_approval_form_instantiation():
    form = ApprovalForm(
        tarea_id="task_123",
        tipo_pausa="PAUSA_1",
        titulo="Test Titulo",
        explicacion_arquitectura="Explicación de prueba",
        pasos=[{"tarea": "Crear archivo", "archivo": "test.py", "requiere_test": True}],
        diff_git="diff content",
        directorio_proyecto="/tmp/proj"
    )
    assert form.tarea_id == "task_123"
    assert form.tipo_pausa == "PAUSA_1"
    assert len(form.pasos) == 1
    assert form.pasos[0]["tarea"] == "Crear archivo"

def test_from_plan_dict():
    plan_dict = {
        "explicacion_arquitectura": "Arquitectura limpia y modular",
        "pasos": [
            {"tarea": "Paso 1", "archivo": "app/a.py", "requiere_test": False},
            {"tarea": "Paso 2", "archivo": "app/b.py", "requiere_test": True}
        ]
    }
    form = ApprovalForm.from_plan_dict("task_abc", plan_dict, "/dir/proyecto")
    assert form.tarea_id == "task_abc"
    assert form.tipo_pausa == "PAUSA_1"
    assert form.explicacion_arquitectura == "Arquitectura limpia y modular"
    assert len(form.pasos) == 2

def test_from_review_data():
    form = ApprovalForm.from_review_data(
        tarea_id="task_rev",
        codigo_escrito="Se modificaron 3 archivos.",
        diff_git="+ nuevo codigo",
        directorio_proyecto="./"
    )
    assert form.tarea_id == "task_rev"
    assert form.tipo_pausa == "PAUSA_2"
    assert "Se modificaron 3 archivos." in form.explicacion_arquitectura
    assert form.diff_git == "+ nuevo codigo"

def test_to_dict_and_json():
    form = ApprovalForm(
        tarea_id="task_json",
        tipo_pausa="PAUSA_1",
        titulo="Formulario JSON",
        explicacion_arquitectura="Desc JSON",
        pasos=[{"tarea": "T1", "archivo": "a.py"}]
    )
    d = form.to_dict()
    assert isinstance(d, dict)
    assert d["tarea_id"] == "task_json"
    assert len(d["acciones_disponibles"]) == 2

    js = form.to_json()
    assert isinstance(js, str)
    parsed = json.loads(js)
    assert parsed["tarea_id"] == "task_json"

def test_to_html():
    form = ApprovalForm(
        tarea_id="task_html",
        tipo_pausa="PAUSA_1",
        titulo="Formulario HTML Interactivo",
        explicacion_arquitectura="Construcción del sistema",
        pasos=[{"tarea": "Crear UI", "archivo": "ui.py", "requiere_test": True}],
        diff_git="diff git mock",
        directorio_proyecto="/app"
    )
    html_out = form.to_html()
    assert "<!DOCTYPE html>" in html_out
    assert "Formulario HTML Interactivo" in html_out
    assert "task_html" in html_out
    assert "Crear UI" in html_out
    assert "diff git mock" in html_out
    assert "ATENCIÓN ASISTENTE DE IA" in html_out
    assert "Aprobar Plan / Código" in html_out
    assert "Rechazar / Solicitar Cambios" in html_out

def test_to_markdown():
    form = ApprovalForm(
        tarea_id="task_md",
        tipo_pausa="PAUSA_2",
        titulo="Revisión de Código",
        explicacion_arquitectura="Detalles de implementación",
        diff_git="+ def test(): pass"
    )
    md_out = form.to_markdown()
    assert "ATENCIÓN ASISTENTE DE IA" in md_out
    assert "DETÉN LA EJECUCIÓN AUTOMÁTICA" in md_out
    assert "`task_md`" in md_out
    assert "+ def test(): pass" in md_out
    assert "INSTRUCCIONES PARA EL USUARIO HUMANO" in md_out

def test_to_cli():
    form = ApprovalForm(
        tarea_id="task_cli",
        tipo_pausa="PAUSA_1",
        titulo="CLI Approval",
        explicacion_arquitectura="Vista para consola terminal",
        pasos=[{"tarea": "Instalar dep", "archivo": "requirements.txt"}]
    )
    cli_out = form.to_cli()
    assert "PAUSA_1" in cli_out
    assert "CLI Approval" in cli_out
    assert "task_cli" in cli_out
    assert "Escribe en el chat" in cli_out
