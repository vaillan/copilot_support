"""
Pruebas de regresión para los 3 defectos corregidos del servidor MCP:

1. Timeout por defecto de delegar_tarea_a_equipo_ia elevado a 1800s
   (la fase del Codificador no cabe en 300s).
2. Timeout del LLM en llm_factory corregido a 300 SEGUNDOS
   (el valor anterior 10000 equivalía a ~2.7h por llamada).
3. '.task_registry.json' excluido del índice de proyecto.
"""

from pathlib import Path

from app.utils.project_index import EXCLUDED_FILES

RAIZ = Path(__file__).resolve().parent.parent


def test_timeout_default_mcp_es_1800():
    """El default de MCP_TASK_TIMEOUT_SECONDS en mcp_server.py debe ser 1800."""
    fuente = (RAIZ / "mcp_server.py").read_text(encoding="utf-8")
    lineas = [
        linea
        for linea in fuente.splitlines()
        if "MCP_TASK_TIMEOUT_SECONDS" in linea and "os.environ.get" in linea
    ]
    assert lineas, "No se encontró la lectura de MCP_TASK_TIMEOUT_SECONDS en mcp_server.py"
    assert '"1800"' in lineas[0], f"El default de timeout debe ser 1800, se encontró: {lineas[0]}"


def test_timeout_llm_es_300_segundos():
    """El timeout base del LLM en llm_factory.py debe ser 300 segundos.

    Para openrouter se convierte a milisegundos (300_000) porque
    langchain_openrouter interpreta `timeout` en ms (mapea a SDK timeout_ms).
    """
    fuente = (RAIZ / "app" / "models" / "llm_factory.py").read_text(encoding="utf-8")
    assert "timeout_llm_segundos = 300" in fuente, "El timeout base del LLM debe ser 300 segundos"
    assert '* 1000' in fuente, "openrouter debe recibir el timeout en milisegundos"


def test_task_registry_json_excluido_del_indice():
    """El archivo de persistencia del TaskRegistry no debe indexarse."""
    assert ".task_registry.json" in EXCLUDED_FILES
