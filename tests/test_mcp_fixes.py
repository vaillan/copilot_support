"""
Pruebas de regresión para los 3 defectos corregidos del servidor MCP:

1. Timeout por defecto de delegar_tarea_a_equipo_ia elevado a 1800s
   (la fase del Codificador no cabe en 300s).
2. Timeout del LLM en llm_factory fijado en 900 segundos
   (10 minutos por llamada LLM; openrouter lo recibe en milisegundos).
3. 'tasks.db' excluido del índice de proyecto (la persistencia del
   TaskRegistry migró de '.task_registry.json' a SQLite).
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


def test_timeout_llm_es_900_segundos():
    """El timeout base del LLM en llm_factory.py debe ser 900 segundos.

    Para openrouter se convierte a milisegundos (900_000) porque
    langchain_openrouter interpreta `timeout` en ms (mapea a SDK timeout_ms).
    """
    fuente = (RAIZ / "app" / "models" / "llm_factory.py").read_text(encoding="utf-8")
    assert "timeout_llm_segundos = 900" in fuente, "El timeout base del LLM debe ser 900 segundos"
    assert '* 1000' in fuente, "openrouter debe recibir el timeout en milisegundos"


def test_task_registry_db_excluido_del_indice():
    """La base SQLite del TaskRegistry no debe indexarse."""
    assert "tasks.db" in EXCLUDED_FILES
    assert ".task_registry.json" not in EXCLUDED_FILES