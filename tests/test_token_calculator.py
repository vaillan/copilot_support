"""
Pruebas unitarias para el módulo de conteo de tokens y cálculo de costos (app/utils/token_calculator.py).
"""

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation, LLMResult

from app.utils.token_calculator import (
    DEFAULT_MODEL_PRICING,
    ModelPricing,
    ModelUsageBreakdown,
    TokenUsage,
    TokenUsageCallbackHandler,
    calculate_cost,
    get_model_pricing,
    register_model_pricing,
    track_token_usage,
)


# ==========================================
# 1. Pruebas de Tarifas y Cálculo de Costos
# ==========================================

def test_model_pricing_dataclass():
    pricing = ModelPricing(input_cost_per_1m=2.50, output_cost_per_1m=10.00)
    assert pricing.input_cost_per_token == pytest.approx(2.50 / 1_000_000)
    assert pricing.output_cost_per_token == pytest.approx(10.00 / 1_000_000)


def test_get_model_pricing_exact_and_fuzzy():
    # Coincidencia exacta
    p_gpt4o = get_model_pricing("gpt-4o")
    assert p_gpt4o is not None
    assert p_gpt4o.input_cost_per_1m == 2.50
    assert p_gpt4o.output_cost_per_1m == 10.00

    # Coincidencia case-insensitive y con espacios
    p_claude = get_model_pricing("  CLAUDE-3-5-SONNET  ")
    assert p_claude is not None
    assert p_claude.input_cost_per_1m == 3.00

    # Coincidencia por subcadena/prefijo (ej. versión de fecha o proveedor)
    p_gemini = get_model_pricing("gemini-1.5-flash-latest")
    assert p_gemini is not None
    assert p_gemini.input_cost_per_1m == 0.075

    # Modelo local / ollama
    p_ollama = get_model_pricing("llama3:8b")
    assert p_ollama is not None
    assert p_ollama.input_cost_per_1m == 0.0
    assert p_ollama.output_cost_per_1m == 0.0

    # Modelo desconocido
    p_unknown = get_model_pricing("modelo-inexistente-12345")
    assert p_unknown is None


def test_calculate_cost_standard_models():
    # GPT-4o: 1,000 prompt tokens ($0.0025) + 500 completion tokens ($0.005) = $0.0075
    cost_gpt4o = calculate_cost("gpt-4o", prompt_tokens=1_000, completion_tokens=500)
    assert cost_gpt4o == pytest.approx(0.0075, rel=1e-5)

    # GPT-4o-mini: 10,000 prompt ($0.0015) + 2,000 completion ($0.0012) = $0.0027
    cost_mini = calculate_cost("gpt-4o-mini", prompt_tokens=10_000, completion_tokens=2_000)
    assert cost_mini == pytest.approx(0.0027, rel=1e-5)

    # Local Ollama: costo cero
    cost_local = calculate_cost("mistral", prompt_tokens=5000, completion_tokens=5000)
    assert cost_local == 0.0

    # Modelo desconocido: costo 0.0
    cost_unknown = calculate_cost("nonexistent-model", prompt_tokens=1000, completion_tokens=1000)
    assert cost_unknown == 0.0


def test_register_custom_model_pricing():
    register_model_pricing("custom-llm-v1", input_cost_per_1m=5.0, output_cost_per_1m=20.0)
    
    pricing = get_model_pricing("custom-llm-v1")
    assert pricing is not None
    assert pricing.input_cost_per_1m == 5.0
    assert pricing.output_cost_per_1m == 20.0

    # 2000 prompt ($0.01) + 1000 completion ($0.02) = $0.03
    cost = calculate_cost("custom-llm-v1", prompt_tokens=2000, completion_tokens=1000)
    assert cost == pytest.approx(0.03, rel=1e-5)


# ==========================================
# 2. Pruebas de la Estructura TokenUsage
# ==========================================

def test_token_usage_aggregation_and_breakdown():
    usage = TokenUsage()
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0
    assert usage.total_cost == 0.0
    assert usage.successful_requests == 0
    assert len(usage.by_model) == 0

    # Agregar uso de GPT-4o
    usage.add_usage(model_name="gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    assert usage.total_tokens == 1500
    assert usage.successful_requests == 1
    assert usage.total_cost == pytest.approx(0.0075, rel=1e-5)
    assert "gpt-4o" in usage.by_model
    assert usage.by_model["gpt-4o"].requests_count == 1
    assert usage.by_model["gpt-4o"].prompt_tokens == 1000

    # Agregar uso de Claude 3.5 Sonnet
    usage.add_usage(model_name="claude-3-5-sonnet", prompt_tokens=1000, completion_tokens=1000)
    assert usage.prompt_tokens == 2000
    assert usage.completion_tokens == 1500
    assert usage.total_tokens == 3500
    assert usage.successful_requests == 2
    # Claude cost: 1000*3/1M + 1000*15/1M = 0.003 + 0.015 = 0.018. Total = 0.0075 + 0.018 = 0.0255
    assert usage.total_cost == pytest.approx(0.0255, rel=1e-5)
    assert len(usage.by_model) == 2

    # Verificar to_dict
    usage_dict = usage.to_dict()
    assert usage_dict["prompt_tokens"] == 2000
    assert usage_dict["completion_tokens"] == 1500
    assert usage_dict["total_tokens"] == 3500
    assert usage_dict["successful_requests"] == 2
    assert "gpt-4o" in usage_dict["by_model"]
    assert "claude-3-5-sonnet" in usage_dict["by_model"]

    # Verificar __repr__
    repr_str = repr(usage)
    assert "TokenUsage" in repr_str
    assert "requests=2" in repr_str

    # Reset
    usage.reset()
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0
    assert usage.total_cost == 0.0
    assert usage.successful_requests == 0
    assert len(usage.by_model) == 0


# ==========================================
# 3. Pruebas de TokenUsageCallbackHandler
# ==========================================

def test_callback_handler_with_llm_output_token_usage():
    """
    Formato clásico OpenAI: response.llm_output = {'token_usage': {'prompt_tokens': ..., 'completion_tokens': ...}, 'model_name': 'gpt-4o'}
    """
    handler = TokenUsageCallbackHandler()

    llm_result = LLMResult(
        generations=[[Generation(text="Hola mundo")]],
        llm_output={
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150
            },
            "model_name": "gpt-4o"
        }
    )

    handler.on_llm_end(llm_result)

    assert handler.prompt_tokens == 120
    assert handler.completion_tokens == 30
    assert handler.total_tokens == 150
    assert handler.successful_requests == 1
    # 120 * 2.50 / 1M + 30 * 10.0 / 1M = 0.0003 + 0.0003 = 0.0006
    assert handler.total_cost == pytest.approx(0.0006, rel=1e-5)


def test_callback_handler_with_modern_usage_metadata():
    """
    Formato moderno LangChain: AIMessage con atributo `usage_metadata`
    """
    handler = TokenUsageCallbackHandler()

    ai_msg = AIMessage(
        content="Respuesta de Claude",
        usage_metadata={
            "input_tokens": 500,
            "output_tokens": 200,
            "total_tokens": 700
        },
        response_metadata={"model": "claude-3-5-sonnet-20241022"}
    )
    generation = ChatGeneration(message=ai_msg)
    llm_result = LLMResult(generations=[[generation]])

    handler.on_llm_end(llm_result)

    assert handler.prompt_tokens == 500
    assert handler.completion_tokens == 200
    assert handler.total_tokens == 700
    assert handler.successful_requests == 1
    # 500 * 3.0 / 1M + 200 * 15.0 / 1M = 0.0015 + 0.003 = 0.0045
    assert handler.total_cost == pytest.approx(0.0045, rel=1e-5)


def test_callback_handler_with_response_metadata_usage():
    """
    Formato con tokens anidados en response_metadata del mensaje
    """
    handler = TokenUsageCallbackHandler()

    ai_msg = AIMessage(
        content="Respuesta de Gemini",
        response_metadata={
            "model_name": "gemini-1.5-flash",
            "usage_metadata": {
                "prompt_tokens": 1000,
                "completion_tokens": 400
            }
        }
    )
    generation = ChatGeneration(message=ai_msg)
    llm_result = LLMResult(generations=[[generation]])

    handler.on_llm_end(llm_result)

    assert handler.prompt_tokens == 1000
    assert handler.completion_tokens == 400
    assert handler.total_tokens == 1400
    # Gemini 1.5 flash: 1000*0.075/1M + 400*0.30/1M = 0.000075 + 0.000120 = 0.000195
    assert handler.total_cost == pytest.approx(0.000195, rel=1e-5)


def test_callback_handler_multiple_invocations_and_reset():
    handler = TokenUsageCallbackHandler()

    # Llamada 1: GPT-4o-mini
    res1 = LLMResult(
        generations=[[Generation(text="Resp 1")]],
        llm_output={
            "token_usage": {"prompt_tokens": 200, "completion_tokens": 100},
            "model_name": "gpt-4o-mini"
        }
    )
    handler.on_llm_end(res1)

    # Llamada 2: GPT-4o-mini
    res2 = LLMResult(
        generations=[[Generation(text="Resp 2")]],
        llm_output={
            "token_usage": {"prompt_tokens": 300, "completion_tokens": 150},
            "model_name": "gpt-4o-mini"
        }
    )
    handler.on_llm_end(res2)

    assert handler.prompt_tokens == 500
    assert handler.completion_tokens == 250
    assert handler.total_tokens == 750
    assert handler.successful_requests == 2

    # Reset
    handler.reset()
    assert handler.prompt_tokens == 0
    assert handler.total_tokens == 0
    assert handler.successful_requests == 0
    assert len(handler.by_model) == 0


def test_callback_handler_empty_or_missing_metadata():
    """
    Caso de borde: respuesta sin ningún tipo de metadata de tokens
    """
    handler = TokenUsageCallbackHandler()
    llm_result = LLMResult(generations=[[Generation(text="Sin tokens")]])

    handler.on_llm_end(llm_result)

    assert handler.prompt_tokens == 0
    assert handler.completion_tokens == 0
    assert handler.total_tokens == 0
    assert handler.successful_requests == 1
    assert handler.total_cost == 0.0


# ==========================================
# 4. Pruebas del Context Manager track_token_usage
# ==========================================

def test_track_token_usage_context_manager():
    with track_token_usage() as cb:
        assert isinstance(cb, TokenUsageCallbackHandler)
        assert cb.total_tokens == 0

        # Simular una llamada a LLM enviando resultado al callback
        res = LLMResult(
            generations=[[Generation(text="Generado en context manager")]],
            llm_output={
                "token_usage": {"prompt_tokens": 40, "completion_tokens": 20},
                "model_name": "gpt-4o"
            }
        )
        cb.on_llm_end(res)

        assert cb.prompt_tokens == 40
        assert cb.completion_tokens == 20
        assert cb.total_tokens == 60
        assert cb.successful_requests == 1

    # Verificar que el callback handler sigue conteniendo los datos tras salir del context manager
    assert cb.total_tokens == 60


def test_track_token_usage_with_existing_handler():
    custom_handler = TokenUsageCallbackHandler()
    
    with track_token_usage(handler=custom_handler) as cb:
        assert cb is custom_handler
        res = LLMResult(
            generations=[[Generation(text="Test con handler existente")]],
            llm_output={
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 10},
                "model_name": "gpt-4o"
            }
        )
        cb.on_llm_end(res)

    assert custom_handler.total_tokens == 20
