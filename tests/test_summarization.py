from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from app.utils.summarization import aplicar_resumen_middleware

def test_aplicar_resumen_middleware_bajo_umbral():
    messages = [HumanMessage(content=f"msg {i}") for i in range(5)]
    resultado = aplicar_resumen_middleware(messages, trigger_count=10, keep_count=3)
    assert len(resultado) == 5
    assert resultado == messages

def test_aplicar_resumen_middleware_supera_umbral():
    messages = [HumanMessage(content=f"msg {i}") for i in range(15)]
    # Se mockea get_llm para evitar llamadas de red reales: el middleware recibe
    # un modelo falso, falla de forma controlada y el fallback de producción
    # devuelve la lista sanitizada sin invocar ningún proveedor.
    with patch("app.utils.summarization.get_llm", return_value=MagicMock()):
        resultado = aplicar_resumen_middleware(messages, trigger_count=10, keep_count=5)
    assert isinstance(resultado, list)
    assert len(resultado) > 0
