"""Pruebas unitarias de app/utils/plan_progress.py."""

from typing import Any, Dict, List, Optional

from app.utils.plan_progress import (
    avanzar_progreso,
    construir_contexto_compacto,
    construir_ledger,
    construir_plan_pruebas,
    inicializar_progreso,
    parsear_pasos_plan,
)

PLAN_MARKDOWN = """**Paso 1: Configuración inicial**
**Responsabilidad única:** primer paso.
**Descripción técnica:** cuerpo uno.
**Paso 2: Lógica central**
**Responsabilidad única:** segundo paso.
**Descripción técnica:** cuerpo dos.
**Paso 3: Integración final**
**Responsabilidad única:** tercer paso."""


def test_parsear_str_con_bloques() -> None:
    pasos = parsear_pasos_plan(PLAN_MARKDOWN)

    assert [p["numero"] for p in pasos] == [1, 2, 3]
    assert [p["titulo"] for p in pasos] == ["Configuración inicial", "Lógica central", "Integración final"]
    assert "cuerpo uno" in pasos[0]["cuerpo"]
    assert "Paso 2" not in pasos[0]["cuerpo"]
    assert "cuerpo dos" not in pasos[0]["cuerpo"]
    assert "segundo paso." in pasos[1]["cuerpo"]
    assert "Paso 3" not in pasos[1]["cuerpo"]
    assert "tercer paso." in pasos[2]["cuerpo"]


def test_parsear_dict_con_pasos() -> None:
    plan_dict: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.py", "tarea": "**Paso 1: Tarea A**\n**Descripción técnica:** cuerpo A", "requiere_test": False},
            {"archivo": "b.py", "tarea": "**Tarea B sin bloque**\ncontenido B", "requiere_test": False},
        ]
    }

    pasos = parsear_pasos_plan(plan_dict)

    assert len(pasos) == 2
    assert pasos[0]["numero"] == 1
    assert pasos[0]["titulo"] == "Tarea A"
    assert pasos[0]["cuerpo"] == "**Paso 1: Tarea A**\n**Descripción técnica:** cuerpo A"
    assert pasos[1]["numero"] == 2
    assert pasos[1]["titulo"] == "b.py"
    assert pasos[1]["cuerpo"] == "**Tarea B sin bloque**\ncontenido B"


def test_parsear_planes_malformados_retorna_lista_vacia() -> None:
    casos: List[Any] = [
        None,
        "",
        "texto sin bloques",
        {},
        {"explicacion_arquitectura": "sin pasos"},
        {"pasos": "no-lista"},
        {"pasos": [123, True]},
        42,
    ]

    for caso in casos:
        assert parsear_pasos_plan(caso) == []


def test_avanzar_progreso_desde_none() -> None:
    assert avanzar_progreso(None, 2, 4) == {"pasos_completados": [2], "paso_actual": 3, "total_pasos": 4}


def test_avanzar_progreso_idempotente() -> None:
    progreso = avanzar_progreso(None, 2, 4)
    progreso_nuevo = avanzar_progreso(progreso, 2, 4)

    assert progreso_nuevo["pasos_completados"] == [2]
    assert progreso_nuevo["paso_actual"] == 3


def test_avanzar_progreso_fuera_de_rango() -> None:
    resultado_cero = avanzar_progreso(None, 0, 4)
    resultado_mayor = avanzar_progreso(None, 5, 4)

    assert resultado_cero["pasos_completados"] == []
    assert resultado_cero["paso_actual"] == 1
    assert resultado_mayor["pasos_completados"] == []
    assert resultado_mayor["paso_actual"] == 1

    previo = {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 4}
    assert avanzar_progreso(previo, 5, 4) == {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 4}


def test_avanzar_progreso_total_no_positivo() -> None:
    assert avanzar_progreso(None, 1, 0) == {"pasos_completados": [], "paso_actual": 1, "total_pasos": 0}

    previo = {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 3}
    assert avanzar_progreso(previo, 2, 0) == previo


def test_inicializar_progreso() -> None:
    assert inicializar_progreso(5) == {"pasos_completados": [], "paso_actual": 1, "total_pasos": 5}


def test_construir_ledger_formato_exacto() -> None:
    ledger = construir_ledger({"pasos_completados": [1, 2], "paso_actual": 3, "total_pasos": 5})

    assert ledger == "Pasos completos: 1, 2 · Paso actual: 3 de 5 · Pendientes: 4, 5"

    ledger_completo = construir_ledger({"pasos_completados": [1, 2, 3], "paso_actual": 4, "total_pasos": 3})
    assert ledger_completo == "Pasos completos: 1, 2, 3 · Todos los pasos completos (3 de 3) · Pendientes: ninguno"


def test_construir_contexto_compacto_con_progreso_valido() -> None:
    progreso = {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 3}

    texto = construir_contexto_compacto(PLAN_MARKDOWN, progreso)

    assert texto is not None
    assert "Paso actual: 2 de 3" in texto
    assert "--- PASO ACTUAL (2 de 3) ---" in texto
    assert "cuerpo dos" in texto
    assert "cuerpo uno" not in texto
    assert "cuerpo tres" not in texto


def test_construir_contexto_compacto_todos_completos() -> None:
    progreso = {"pasos_completados": [1, 2, 3], "paso_actual": 4, "total_pasos": 3}

    texto = construir_contexto_compacto(PLAN_MARKDOWN, progreso)

    assert texto is not None
    assert "Todos los pasos están completos" in texto
    assert "CodigoCompletado" in texto


def test_construir_contexto_compacto_con_plan_o_progreso_invalidos() -> None:
    progreso_valido = {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 3}

    assert construir_contexto_compacto("texto sin bloques", progreso_valido) is None
    assert construir_contexto_compacto(PLAN_MARKDOWN, None) is None
    assert construir_contexto_compacto(PLAN_MARKDOWN, {"pasos_completados": "x", "paso_actual": 2, "total_pasos": 3}) is None
    assert construir_contexto_compacto(PLAN_MARKDOWN, {"pasos_completados": [1], "paso_actual": "x", "total_pasos": 3}) is None
    assert construir_contexto_compacto(PLAN_MARKDOWN, {"pasos_completados": [1], "paso_actual": 0, "total_pasos": 3}) is None


def test_construir_plan_pruebas_filtra_pasos_con_test() -> None:
    plan: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.py", "tarea": "**Paso 1: Logica**\nDetalle PASO_CON_TEST_1", "requiere_test": True},
            {"archivo": "b.md", "tarea": "**Paso 2: Docs**\nDetalle PASO_SIN_TEST", "requiere_test": False},
            {"archivo": "c.py", "tarea": "**Paso 3: Mas logica**\nDetalle PASO_CON_TEST_2", "requiere_test": True},
        ]
    }

    salida = construir_plan_pruebas(plan)

    assert "PASO_CON_TEST_1" in salida
    assert "PASO_CON_TEST_2" in salida
    assert "PASO_SIN_TEST" not in salida


def test_construir_plan_pruebas_sin_pasos_con_test() -> None:
    plan: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.md", "tarea": "**Paso 1: Docs**\nDetalle DOCS", "requiere_test": False},
        ]
    }

    assert construir_plan_pruebas(plan) == "Ningún paso del plan requiere pruebas."


def test_construir_plan_pruebas_sin_plan() -> None:
    assert construir_plan_pruebas(None) == "Sin plan."


def test_construir_plan_pruebas_con_texto_plano() -> None:
    assert construir_plan_pruebas("texto plano") == "texto plano"


def test_construir_plan_pruebas_con_pasos_mezclados() -> None:
    plan: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.py", "tarea": "**Paso 1: Logica**\nDetalle PASO_DICT", "requiere_test": True},
            "paso suelto",
        ]
    }

    salida = construir_plan_pruebas(plan)

    assert "PASO_DICT" in salida
    assert "paso suelto" not in salida


def test_construir_plan_pruebas_idioma_en() -> None:
    assert construir_plan_pruebas(None, "en") == "No plan."
    plan: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.md", "tarea": "**Paso 1: Docs**\nDetalle DOCS", "requiere_test": False},
        ]
    }
    assert construir_plan_pruebas(plan, "en") == "No plan steps require tests."


def test_construir_plan_pruebas_default_es_preservado() -> None:
    assert construir_plan_pruebas(None) == "Sin plan."
    plan: Dict[str, Any] = {
        "pasos": [
            {"archivo": "a.md", "tarea": "**Paso 1: Docs**", "requiere_test": False},
        ]
    }
    assert construir_plan_pruebas(plan) == "Ningún paso del plan requiere pruebas."


def test_construir_ledger_idioma_en() -> None:
    ledger = construir_ledger({"pasos_completados": [1, 2], "paso_actual": 3, "total_pasos": 5}, idioma="en")

    assert ledger == "Completed steps: 1, 2 · Current step: 3 of 5 · Pending: 4, 5"
    assert "Completed steps" in ledger
    assert "Pasos completos" not in ledger


def test_construir_ledger_default_es() -> None:
    ledger = construir_ledger({"pasos_completados": [1], "paso_actual": 2, "total_pasos": 3})

    assert ledger == "Pasos completos: 1 · Paso actual: 2 de 3 · Pendientes: 3"


def test_construir_ledger_en_todos_completos() -> None:
    ledger = construir_ledger({"pasos_completados": [1, 2, 3], "paso_actual": 4, "total_pasos": 3}, idioma="en")

    assert "none" in ledger
    assert "All steps completed" in ledger


def test_construir_contexto_compacto_idioma_en() -> None:
    texto = construir_contexto_compacto(
        PLAN_MARKDOWN,
        {"pasos_completados": [1], "paso_actual": 2, "total_pasos": 3},
        idioma="en",
    )

    assert texto is not None
    assert "Current step: 2 of 3" in texto
    assert "Paso actual" not in texto