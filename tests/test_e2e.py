import os
import pytest
import uuid
from langchain_core.messages import HumanMessage
from app.main import crear_grafo

@pytest.mark.e2e
def test_flujo_completo_e2e():
    """
    Prueba End-to-End que verifica el flujo completo de los agentes
    utilizando el LLM real.
    """
    # 1. Crear el grafo
    graph = crear_grafo()
    
    # 2. Definir un thread_id único para la configuración
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    
    # Archivo de prueba
    test_file = "e2e_test_output.txt"
    test_content = "Hello E2E"
    
    # Asegurarse de que el archivo no exista antes de empezar
    if os.path.exists(test_file):
        os.remove(test_file)
        
    # 3. Iniciar el grafo con un estado inicial
    instruccion = f"Crea un archivo llamado '{test_file}' que contenga exactamente el texto '{test_content}'."
    estado_inicial = {
        "instruccion_usuario": instruccion,
        "directorio_proyecto": "./",
        "messages": [HumanMessage(content=instruccion)]
    }
    
    try:
        # Ejecutar hasta la primera interrupción (antes de agente_codificador)
        graph.invoke(estado_inicial, config)
        
        # 4. Verificar que el grafo se detiene antes de agente_codificador
        estado_actual = graph.get_state(config)
        assert len(estado_actual.next) > 0, "El grafo debería estar pausado"
        assert estado_actual.next[0] == "agente_codificador", "El grafo debería detenerse antes del codificador"
        
        # Verificar que el estado contiene un plan_de_accion
        assert "plan_de_accion" in estado_actual.values, "El estado debería contener un plan de acción"
        assert estado_actual.values["plan_de_accion"] is not None, "El plan de acción no debería ser None"
        
        # 5. Reanudar el grafo (el codificador debe ejecutar herramientas)
        graph.invoke(None, config)
        estado_actual = graph.get_state(config)
        
        # El agente codificador invoca a "nodo_herramientas_codificador" pero como "agente_codificador" está en "interrupt_before", 
        # en realidad, el grafo pausa ANTES de ejecutar el agente de nuevo (o pausa ANTES del revisor).
        # Vamos a reanudarlo hasta que se pause antes del revisor.
        max_intentos = 5
        intentos = 0
        while len(estado_actual.next) > 0 and estado_actual.next[0] != "agente_revisor" and intentos < max_intentos:
            graph.invoke(None, config)
            estado_actual = graph.get_state(config)
            intentos += 1
            
        assert len(estado_actual.next) > 0, "El grafo debería estar pausado"
        assert estado_actual.next[0] == "agente_revisor", f"El grafo debería detenerse antes del revisor, se detuvo en {estado_actual.next}"
        
        # 6. Reanudar el grafo nuevamente hasta que termine
        graph.invoke(None, config)
        estado_actual = graph.get_state(config)
        assert len(estado_actual.next) == 0, "El grafo debería haber terminado"
        
        # 7. Leer el archivo, verificar su contenido y luego eliminarlo
        assert os.path.exists(test_file), f"El archivo {test_file} no fue creado"
        
        with open(test_file, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
            
        assert test_content in contenido, f"El contenido del archivo no es el esperado. Esperado: '{test_content}', Obtenido: '{contenido}'"
        
    finally:
        # Limpieza: eliminar el archivo si existe
        if os.path.exists(test_file):
            os.remove(test_file)
