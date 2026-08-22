import pytest
from app.models.models import ProjectState, _ultimo_valor
from app.main import crear_grafo

def test_loop_counter_reducer_ultimo_valor():
    """Verifica que el reducer Annotated conserva el último valor ante actualizaciones concurrentes."""
    assert _ultimo_valor(1, 5) == 5
    assert _ultimo_valor(0, 3) == 3
    assert _ultimo_valor(7, 7) == 7

def test_project_state_structure():
    state: ProjectState = {
        "messages": [],
        "instruccion_usuario": "test",
        "directorio_proyecto": "./",
        "plan_de_accion": {"pasos": []},
        "codigo_escrito": "resumen",
        "errores_terminal": None,
        "revision_count": 0,
        "loop_counter": 0
    }
    assert state["instruccion_usuario"] == "test"
    assert state["directorio_proyecto"] == "./"
    assert state["revision_count"] == 0
    assert state["loop_counter"] == 0

def test_crear_grafo_compilation():
    grafo = crear_grafo(interrumpir_en_codificador=False, interrumpir_en_revisor=False)
    assert grafo is not None
    assert "agente_planificador" in grafo.nodes
    assert "agente_codificador" in grafo.nodes
    assert "agente_revisor" in grafo.nodes

def test_crear_grafo_con_interrupciones():
    grafo = crear_grafo(interrumpir_en_codificador=True, interrumpir_en_revisor=True)
    assert grafo is not None
