from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.utils.summarization import aplicar_resumen_middleware


class FakeModel:
    def invoke(self, prompt: object) -> AIMessage:
        return AIMessage(content="Resumen de prueba")


class ModelQueFalla:
    def invoke(self, prompt: object) -> AIMessage:
        raise RuntimeError("boom")


def test_umbral_no_superado_devuelve_misma_lista() -> None:
    messages = [HumanMessage(content=f"msg {i}") for i in range(10)]
    resultado = aplicar_resumen_middleware(messages, model=FakeModel(), trigger_count=15, keep_count=8)
    assert resultado is messages


def test_umbral_superado_resume_y_conserva_recientes() -> None:
    messages = [HumanMessage(content=f"msg {i}") for i in range(20)]
    resultado = aplicar_resumen_middleware(messages, model=FakeModel(), trigger_count=15, keep_count=8)
    # Estructura: [instrucción original preservada] + [resumen] + [8 recientes]
    assert len(resultado) == 10
    assert resultado[0] is messages[0]
    assert resultado[1].content.startswith("[Resumen de conversación anterior]")
    assert resultado[2:] == messages[-8:]


def test_lista_vacia_devuelve_vacia() -> None:
    assert aplicar_resumen_middleware([], model=FakeModel()) == []


def test_model_none_usa_llm_por_defecto() -> None:
    messages = [HumanMessage(content=f"msg {i}") for i in range(20)]
    with patch("app.utils.summarization.get_llm", return_value=FakeModel()):
        resultado = aplicar_resumen_middleware(messages, trigger_count=15, keep_count=8)
    assert isinstance(resultado[0], HumanMessage)
    assert any("Resumen de prueba" in str(m.content) for m in resultado)


def test_modelo_que_falla_devuelve_mensajes_originales() -> None:
    messages = [HumanMessage(content=f"msg {i}") for i in range(20)]
    resultado = aplicar_resumen_middleware(messages, model=ModelQueFalla(), trigger_count=15, keep_count=8)
    assert resultado is messages


def test_keep_count_mayor_que_len_mensajes() -> None:
    messages = [HumanMessage(content=f"msg {i}") for i in range(3)]
    resultado = aplicar_resumen_middleware(messages, model=FakeModel(), trigger_count=1, keep_count=10)
    assert resultado is messages