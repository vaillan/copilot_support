import os
import pytest
import uuid
from unittest.mock import patch
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from app.main import crear_grafo


@pytest.fixture(autouse=True)
def _sin_regeneracion_tests():
    """Neutraliza el hook de regeneración de tests en este E2E.

    El hook es comportamiento válido (el archivo creado es un cambio real), pero
    este test valida el flujo planificador->codificador->revisor sin la fase
    extra de regeneración de pruebas. El hook se valida en tests/test_test_regenerator.py.
    """
    with patch('app.agents.agente_codificador.evaluar_regeneracion_tests',
               return_value={"disparar": False, "archivos_modificados": [], "razon": "test",
                             "hashes_actualizados": {}, "last_ts": 0.0}):
        yield


@pytest.mark.e2e
def test_flujo_completo_e2e():
    """
    Prueba End-to-End que verifica el flujo completo de los agentes
    utilizando el LLM real.
    """
    # MemorySaver: aísla el test de la persistencia en disco (validada en tests/test_checkpointer.py)
    graph = crear_grafo(checkpointer=MemorySaver())
    
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    
    test_file = "e2e_test_output.txt"
    test_content = "Hello E2E"
    
    if os.path.exists(test_file):
        os.remove(test_file)
        
    instruccion = f"Crea un archivo llamado '{test_file}' que contenga exactamente el texto '{test_content}'."
    estado_inicial = {
        "instruccion_usuario": instruccion,
        "directorio_proyecto": "./",
        "messages": [HumanMessage(content=instruccion)]
    }
    
    try:
        graph.invoke(estado_inicial, config)
        
        estado_actual = graph.get_state(config)
        assert len(estado_actual.next) > 0, "El grafo debería estar pausado"
        assert estado_actual.next[0] == "agente_codificador", "El grafo debería detenerse antes del codificador"
        
        assert "plan_de_accion" in estado_actual.values, "El estado debería contener un plan de acción"
        assert estado_actual.values["plan_de_accion"] is not None, "El plan de acción no debería ser None"
        
        graph.invoke(None, config)
        estado_actual = graph.get_state(config)
        
        # Margen ampliado: el Codificador ahora puede verificar su código con la
        # tool `terminal` (pytest, py_compile, imports) antes de entregar, por lo
        # que el flujo hasta el Revisor puede requerir más iteraciones.
        max_intentos = 10
        intentos = 0
        while len(estado_actual.next) > 0 and estado_actual.next[0] != "agente_revisor" and intentos < max_intentos:
            graph.invoke(None, config)
            estado_actual = graph.get_state(config)
            intentos += 1
            
        assert len(estado_actual.next) > 0, "El grafo deberia estar pausado"
        assert estado_actual.next[0] == "agente_revisor", f"El grafo deberia detenerse antes del revisor, se detuvo en {estado_actual.next}"
        
        while len(estado_actual.next) > 0 and intentos < max_intentos * 4:
            graph.invoke(None, config)
            estado_actual = graph.get_state(config)
            intentos += 1

        assert len(estado_actual.next) == 0, f"El grafo deberia haber terminado, pero se detuvo en {estado_actual.next}"
        
        assert os.path.exists(test_file), f"El archivo {test_file} no fue creado"
        
        with open(test_file, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
            
        assert test_content in contenido, f"El contenido del archivo no es el esperado. Esperado: '{test_content}', Obtenido: '{contenido}'"

    finally:
        # NOTA: el artefacto NO se elimina aquí: tests/test_e2e_output.py lo verifica
        # y lo limpia al final de su ejecución (se ejecuta después por orden alfabético).
        pass
