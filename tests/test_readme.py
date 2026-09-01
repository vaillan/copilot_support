"""
Pruebas unitarias para README.md.

Verifica que la documentación refleja las implementaciones recientes:
persistencia SQLite del TaskRegistry, anti-bucle, timeouts, lista de
módulos de tests y la sección "Nota de actualización" (changelog).
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"

NUEVOS_MODULOS_TESTS = [
    "test_task_registry",
    "test_test_regenerator",
    "test_mcp_fixes",
    "test_contexto_largo",
    "test_revisor_fallback",
]


@pytest.fixture(scope="module")
def readme() -> str:
    """Contenido completo del README.md de la raíz del proyecto."""
    assert README.exists(), f"No existe {README}"
    return README.read_text(encoding="utf-8")


def test_readme_documenta_persistencia_sqlite_del_task_registry(readme):
    assert "SQLite" in readme
    assert "tasks.db" in readme
    assert "app/utils/task_registry.py" in readme
    assert "JSON" in readme  # menciona el reemplazo de la persistencia previa


def test_readme_documenta_anti_bucle(readme):
    assert "anti-bucle" in readme
    assert "umbral de reintentos anti-bucle = 4" in readme
    assert "app/utils/test_regenerator.py" in readme
    assert "errores_terminal" in readme


def test_readme_documenta_timeouts(readme):
    assert "900s" in readme
    assert "10 min" in readme
    assert "MCP_TASK_TIMEOUT_SECONDS" in readme


def test_readme_lista_los_nuevos_modulos_de_tests(readme):
    seccion_pruebas = readme.split("## Pruebas", 1)[1].split("## Nota de actualización", 1)[0]
    for modulo in NUEVOS_MODULOS_TESTS:
        assert modulo in seccion_pruebas, f"Falta {modulo} en la lista de tests"


def test_readme_incluye_nota_de_actualizacion_con_al_menos_6_entradas(readme):
    assert "## Nota de actualización" in readme
    assert "## Términos de uso" in readme
    seccion = readme.split("## Nota de actualización", 1)[1].split("## Términos de uso", 1)[0]
    entradas = re.findall(r"^- \*\*\d{4}-\d{2}-\d{2}\*\*:", seccion, flags=re.MULTILINE)
    assert len(entradas) >= 6, f"Se esperaban al menos 6 entradas, se encontraron {len(entradas)}"


def test_readme_no_menciona_persistencia_json_desactualizada(readme):
    """La persistencia previa en JSON solo debe aparecer como reemplazada, no como vigente."""
    assert "persiste en JSON" not in readme
    assert "persistencia en JSON" not in readme