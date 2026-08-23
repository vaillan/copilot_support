import os
import pytest
import uuid
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from app.main import crear_grafo

@pytest.mark.e2e
def test_flujo_completo_e2e():
    """
    Prueba End-to-End que verifica el flujo completo de los agentes
    utilizando el LLM real.
    """
    graph = crear_grafo(checkpointer=InMemorySaver())
    
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
        
        max_intentos = 5
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
        if os.path.exists(test_file):
            os.remove(test_file)
