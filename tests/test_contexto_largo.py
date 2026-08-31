"""Pruebas de preservación de contexto en conversaciones largas y no duplicación del hook de regeneración."""

from langchain_core.messages import AIMessage, HumanMessage

from app.utils.prompt_utils import construir_prompt_template_cacheado
from app.utils.summarization import aplicar_resumen_middleware
from app.utils.test_regenerator import evaluar_regeneracion_tests


class _LLMFalso:
    """Doble de prueba de BaseChatModel: devuelve un resumen fijo sin red ni LLM real."""

    def invoke(self, _prompt):
        class _Respuesta:
            content = (
                "Instrucción: crear modulo X. Plan: pasos 1-3. Archivos modificados: app/main.py. "
                "Errores previos: ninguno."
            )
        return _Respuesta()


def _conversacion_larga(n: int = 25) -> list:
    """Construye un historial largo: instrucción original + n mensajes de trabajo."""
    mensajes = [HumanMessage(content="Instrucción original: implementa el módulo X con pruebas")]
    for i in range(n):
        mensajes.append(AIMessage(content=f"Iteración de trabajo {i}"))
        mensajes.append(HumanMessage(content=f"Resultado de herramienta {i}"))
    return mensajes


def test_resumen_preserva_instruccion_original() -> None:
    """Tras resumir una conversación larga, la instrucción original del usuario se conserva íntegra."""
    mensajes = _conversacion_larga()
    resultado = aplicar_resumen_middleware(mensajes, model=_LLMFalso())
    assert resultado[0].content == mensajes[0].content
    assert any("Resumen de conversación anterior" in str(m.content) for m in resultado)


def test_resumen_preserva_mensajes_recientes() -> None:
    """Los últimos mensajes (errores y resultados recientes) se conservan íntegros."""
    mensajes = _conversacion_larga()
    resultado = aplicar_resumen_middleware(mensajes, model=_LLMFalso(), keep_count=8)
    assert resultado[-1].content == mensajes[-1].content
    assert resultado[-2].content == mensajes[-2].content


def test_resumen_conserva_plan_y_archivos_en_texto() -> None:
    """El resumen generado debe contener plan, archivos modificados y errores (garantía documentada)."""
    mensajes = _conversacion_larga()
    resultado = aplicar_resumen_middleware(mensajes, model=_LLMFalso())
    resumen = next(str(m.content) for m in resultado if "Resumen de conversación anterior" in str(m.content))
    assert "Plan" in resumen
    assert "app/main.py" in resumen
    assert "Errores" in resumen


def test_conversacion_corta_no_se_modifica() -> None:
    """Por debajo del umbral, el historial se devuelve intacto (ahorro de tokens: sin llamadas extra)."""
    mensajes = _conversacion_larga(3)
    resultado = aplicar_resumen_middleware(mensajes, model=_LLMFalso())
    assert resultado is mensajes


def test_mensaje_regeneracion_no_se_duplica(tmp_path) -> None:
    """El hook de regeneración inyecta el mensaje UNA sola vez: la segunda evaluación no re-dispara."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v1')", encoding="utf-8")
    msgs = [AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "app/main.py"}, "id": "c1"}])]

    primera = evaluar_regeneracion_tests(str(tmp_path), msgs, AIMessage(content=""), {})
    assert primera["disparar"] is True

    # Estado tras la primera regeneración: hashes actualizados + contador incrementado.
    estado_tras_primera = {
        "test_regeneration_count": 1,
        "test_regeneration_hashes": primera["hashes_actualizados"],
        "test_regeneration_last_ts": primera["last_ts"],
    }
    segunda = evaluar_regeneracion_tests(str(tmp_path), msgs, AIMessage(content=""), estado_tras_primera)
    assert segunda["disparar"] is False
    # El mensaje de regeneración solo corresponde a la primera evaluación (no hay duplicación).


def test_template_cacheado_reutiliza_instancia() -> None:
    """El mismo prompt de sistema reutiliza la instancia compilada (sin reconstrucción redundante)."""
    prompt = "SYSTEM PROMPT DE PRUEBA {directorio}"
    t1 = construir_prompt_template_cacheado(prompt)
    t2 = construir_prompt_template_cacheado(prompt)
    assert t1 is t2
    otro = construir_prompt_template_cacheado(prompt + " v2")
    assert otro is not t1
