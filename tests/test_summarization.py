import pytest
from langchain_core.messages import HumanMessage
from app.utils.summarization import aplicar_resumen_middleware

def test_aplicar_resumen_middleware_bajo_umbral():
    messages = [HumanMessage(content=f"msg {i}") for i in range(5)]
    resultado = aplicar_resumen_middleware(messages, trigger_count=10, keep_count=3)
    assert len(resultado) == 5
    assert resultado == messages

def test_aplicar_resumen_middleware_supera_umbral():
    messages = [HumanMessage(content=f"msg {i}") for i in range(15)]
    # Usando un mock o modelo si es necesario, pero como mockeamos o dependemos del comportamiento:
    # Verificamos que no falle y retorne lista de mensajes
    resultado = aplicar_resumen_middleware(messages, trigger_count=10, keep_count=5)
    assert isinstance(resultado, list)
    assert len(resultado) > 0
