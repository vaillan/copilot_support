import gc
import os
import sqlite3
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test requiring LLM API keys"
    )


def pytest_sessionstart(session):
    """
    Elimina el checkpointer persistido ANTES de la recolección de tests,
    cuando ninguna conexión sqlite lo bloquea todavía.
    """
    _eliminar_checkpoints_sqlite()


@pytest.fixture(autouse=True)
def _limpiar_checkpoints_sqlite():
    """Elimina checkpoints.sqlite antes y después de cada test."""
    _eliminar_checkpoints_sqlite()
    yield
    _eliminar_checkpoints_sqlite()


def _eliminar_checkpoints_sqlite():
    # Cerrar cualquier conexión sqlite abierta que pueda bloquear el archivo
    # en Windows (el checkpointer SqliteSaver crea conexiones que no se cierran).
    for obj in gc.get_objects():
        try:
            if isinstance(obj, sqlite3.Connection):
                obj.close()
        except Exception:
            pass
    try:
        os.remove("checkpoints.sqlite")
    except OSError:
        # No existe, o está bloqueado por una conexión abierta (Windows).
        pass
