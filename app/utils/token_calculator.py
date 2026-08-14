"""
Módulo para el conteo de tokens y cálculo de costos agnóstico a proveedores en LangChain y LangGraph.

Permite monitorear el uso de tokens (prompt, completion y total) y calcular el costo
monetario estimado para modelos de OpenAI, Anthropic, Google Gemini, Ollama y otros proveedores.
"""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Optional
import copy

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


@dataclass
class ModelPricing:
    """
    Estructura de precios por millón de tokens (USD).
    """
    input_cost_per_1m: float
    output_cost_per_1m: float

    @property
    def input_cost_per_token(self) -> float:
        return self.input_cost_per_1m / 1_000_000.0

    @property
    def output_cost_per_token(self) -> float:
        return self.output_cost_per_1m / 1_000_000.0


# Tarifas de precios estándar de referencia (USD por 1M tokens)
# Actualizado con modelos comunes de OpenAI, Anthropic y Google
DEFAULT_MODEL_PRICING: Dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(input_cost_per_1m=2.50, output_cost_per_1m=10.00),
    "gpt-4o-2024-08-06": ModelPricing(input_cost_per_1m=2.50, output_cost_per_1m=10.00),
    "gpt-4o-2024-05-13": ModelPricing(input_cost_per_1m=5.00, output_cost_per_1m=15.00),
    "gpt-4o-mini": ModelPricing(input_cost_per_1m=0.15, output_cost_per_1m=0.60),
    "gpt-4o-mini-2024-07-18": ModelPricing(input_cost_per_1m=0.15, output_cost_per_1m=0.60),
    "gpt-4-turbo": ModelPricing(input_cost_per_1m=10.00, output_cost_per_1m=30.00),
    "gpt-4": ModelPricing(input_cost_per_1m=30.00, output_cost_per_1m=60.00),
    "gpt-3.5-turbo": ModelPricing(input_cost_per_1m=0.50, output_cost_per_1m=1.50),
    "o1": ModelPricing(input_cost_per_1m=15.00, output_cost_per_1m=60.00),
    "o1-mini": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=12.00),
    "o1-preview": ModelPricing(input_cost_per_1m=15.00, output_cost_per_1m=60.00),
    "o3-mini": ModelPricing(input_cost_per_1m=1.10, output_cost_per_1m=4.40),

    # Anthropic
    "claude-3-5-sonnet-20241022": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=15.00),
    "claude-3-5-sonnet-20240620": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=15.00),
    "claude-3-5-sonnet": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=15.00),
    "claude-3-5-haiku-20241022": ModelPricing(input_cost_per_1m=1.00, output_cost_per_1m=5.00),
    "claude-3-5-haiku": ModelPricing(input_cost_per_1m=1.00, output_cost_per_1m=5.00),
    "claude-3-opus-20240229": ModelPricing(input_cost_per_1m=15.00, output_cost_per_1m=75.00),
    "claude-3-opus": ModelPricing(input_cost_per_1m=15.00, output_cost_per_1m=75.00),
    "claude-3-sonnet-20240229": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=15.00),
    "claude-3-sonnet": ModelPricing(input_cost_per_1m=3.00, output_cost_per_1m=15.00),
    "claude-3-haiku-20240307": ModelPricing(input_cost_per_1m=0.25, output_cost_per_1m=1.25),
    "claude-3-haiku": ModelPricing(input_cost_per_1m=0.25, output_cost_per_1m=1.25),

    # Google Gemini
    "gemini-1.5-pro": ModelPricing(input_cost_per_1m=1.25, output_cost_per_1m=5.00),
    "gemini-1.5-pro-latest": ModelPricing(input_cost_per_1m=1.25, output_cost_per_1m=5.00),
    "gemini-1.5-flash": ModelPricing(input_cost_per_1m=0.075, output_cost_per_1m=0.30),
    "gemini-1.5-flash-latest": ModelPricing(input_cost_per_1m=0.075, output_cost_per_1m=0.30),
    "gemini-1.5-flash-8b": ModelPricing(input_cost_per_1m=0.0375, output_cost_per_1m=0.15),
    "gemini-2.0-flash": ModelPricing(input_cost_per_1m=0.10, output_cost_per_1m=0.40),
    "gemini-2.0-flash-exp": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),

    # Modelos locales / Ollama (costo cero por defecto)
    "ollama": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.1": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.2": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.3": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "mistral": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "qwen": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "deepseek-r1": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
}

# Diccionario dinámico de precios registrado en tiempo de ejecución
_CUSTOM_MODEL_PRICING: Dict[str, ModelPricing] = {}


def register_model_pricing(model_name: str, input_cost_per_1m: float, output_cost_per_1m: float) -> None:
    """
    Registra o sobreescribe la tarifa de precios para un modelo específico.
    """
    key = model_name.strip().lower()
    _CUSTOM_MODEL_PRICING[key] = ModelPricing(
        input_cost_per_1m=float(input_cost_per_1m),
        output_cost_per_1m=float(output_cost_per_1m)
    )


def get_model_pricing(model_name: str) -> Optional[ModelPricing]:
    """
    Obtiene la tarifa de precios asociada a un modelo dado, buscando coincidencias
    exactas o por prefijo/subcadena.
    """
    if not model_name:
        return None

    clean_name = model_name.strip().lower()

    # 1. Búsqueda exacta en custom pricing
    if clean_name in _CUSTOM_MODEL_PRICING:
        return _CUSTOM_MODEL_PRICING[clean_name]

    # 2. Búsqueda exacta en default pricing
    if clean_name in DEFAULT_MODEL_PRICING:
        return DEFAULT_MODEL_PRICING[clean_name]

    # 3. Búsqueda por subcadena / prefijo en custom pricing
    for key, pricing in _CUSTOM_MODEL_PRICING.items():
        if key in clean_name or clean_name in key:
            return pricing

    # 4. Búsqueda por subcadena / prefijo en default pricing (ordenando por longitud descendente)
    for key in sorted(DEFAULT_MODEL_PRICING.keys(), key=len, reverse=True):
        if key in clean_name:
            return DEFAULT_MODEL_PRICING[key]

    return None


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calcula el costo estimado en USD para un número de tokens de entrada y salida dado un modelo.
    Si el modelo no está registrado, se asume costo 0.0.
    """
    pricing = get_model_pricing(model_name)
    if not pricing:
        return 0.0

    prompt_cost = prompt_tokens * pricing.input_cost_per_token
    completion_cost = completion_tokens * pricing.output_cost_per_token
    return prompt_cost + completion_cost


@dataclass
class ModelUsageBreakdown:
    """
    Desglose de uso por modelo específico.
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    requests_count: int = 0

    def add(self, prompt: int, completion: int, cost: float) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += (prompt + completion)
        self.total_cost += cost
        self.requests_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 6),
            "requests_count": self.requests_count,
        }


@dataclass
class TokenUsage:
    """
    Acumulador general de consumo de tokens y costos.
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    successful_requests: int = 0
    by_model: Dict[str, ModelUsageBreakdown] = field(default_factory=dict)

    def add_usage(self, model_name: str, prompt_tokens: int, completion_tokens: int, cost: Optional[float] = None) -> None:
        """
        Registra una invocación exitosa agregando los tokens y calculando el costo correspondiente.
        """
        model_key = model_name.strip() if model_name else "unknown"
        if cost is None:
            cost = calculate_cost(model_key, prompt_tokens, completion_tokens)

        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.total_cost += cost
        self.successful_requests += 1

        if model_key not in self.by_model:
            self.by_model[model_key] = ModelUsageBreakdown()
        self.by_model[model_key].add(prompt_tokens, completion_tokens, cost)

    def reset(self) -> None:
        """
        Reinicia todos los contadores a cero.
        """
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.successful_requests = 0
        self.by_model.clear()

    def to_dict(self) -> Dict[str, Any]:
        """
        Retorna la representación serializable en diccionario.
        """
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 6),
            "successful_requests": self.successful_requests,
            "by_model": {k: v.to_dict() for k, v in self.by_model.items()},
        }

    def __repr__(self) -> str:
        return (
            f"TokenUsage(requests={self.successful_requests}, "
            f"prompt_tokens={self.prompt_tokens}, "
            f"completion_tokens={self.completion_tokens}, "
            f"total_tokens={self.total_tokens}, "
            f"total_cost=${self.total_cost:.6f})"
        )


class TokenUsageCallbackHandler(BaseCallbackHandler):
    """
    Callback Handler de LangChain que intercepta `on_llm_end` para rastrear
    el conteo de tokens y el costo monetario en ejecuciones de LLMs, Chains y Grafos LangGraph.
    """

    def __init__(self, token_usage: Optional[TokenUsage] = None) -> None:
        super().__init__()
        self.usage: TokenUsage = token_usage if token_usage is not None else TokenUsage()

    @property
    def prompt_tokens(self) -> int:
        return self.usage.prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self.usage.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.usage.total_tokens

    @property
    def total_cost(self) -> float:
        return self.usage.total_cost

    @property
    def successful_requests(self) -> int:
        return self.usage.successful_requests

    @property
    def by_model(self) -> Dict[str, ModelUsageBreakdown]:
        return self.usage.by_model

    def reset(self) -> None:
        self.usage.reset()

    def to_dict(self) -> Dict[str, Any]:
        return self.usage.to_dict()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """
        Se ejecuta al finalizar una llamada LLM. Extrae metadatos de tokens y calcula costos.
        """
        llm_output = response.llm_output or {}
        
        # 1. Intentar obtener el nombre del modelo
        model_name = (
            llm_output.get("model_name")
            or llm_output.get("model")
            or kwargs.get("invocation_params", {}).get("model_name")
            or kwargs.get("invocation_params", {}).get("model")
            or ""
        )

        # 2. Intentar extraer tokens de llm_output (estándar OpenAI / proveedores clásicos)
        prompt_tokens = 0
        completion_tokens = 0
        extracted_from_output = False

        token_usage_dict = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(token_usage_dict, dict):
            prompt_tokens = token_usage_dict.get("prompt_tokens") or token_usage_dict.get("input_tokens") or 0
            completion_tokens = token_usage_dict.get("completion_tokens") or token_usage_dict.get("output_tokens") or 0
            extracted_from_output = True

        # 3. Extraer de las generaciones individuales (estándar moderno LangChain AIMessage / usage_metadata)
        gen_prompt_tokens = 0
        gen_completion_tokens = 0
        found_in_generations = False

        for gen_list in response.generations:
            for gen in gen_list:
                # Obtener modelo de generation_info o message si aún no se tiene
                gen_info = getattr(gen, "generation_info", None) or {}
                msg = getattr(gen, "message", None)

                if not model_name:
                    if isinstance(gen_info, dict) and "model_name" in gen_info:
                        model_name = gen_info["model_name"]
                    elif msg and hasattr(msg, "response_metadata") and isinstance(msg.response_metadata, dict):
                        model_name = msg.response_metadata.get("model_name") or msg.response_metadata.get("model", "")

                # Extraer usage_metadata de AIMessage (LangChain >= 0.2)
                if msg and hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    u_meta = msg.usage_metadata
                    if isinstance(u_meta, dict):
                        gen_prompt_tokens += u_meta.get("input_tokens", 0)
                        gen_completion_tokens += u_meta.get("output_tokens", 0)
                        found_in_generations = True

                # Extraer de response_metadata de AIMessage
                elif msg and hasattr(msg, "response_metadata") and isinstance(msg.response_metadata, dict):
                    resp_meta = msg.response_metadata
                    usage_sub = resp_meta.get("usage") or resp_meta.get("token_usage") or resp_meta.get("usage_metadata")
                    if isinstance(usage_sub, dict):
                        gen_prompt_tokens += (usage_sub.get("prompt_tokens") or usage_sub.get("input_tokens") or 0)
                        gen_completion_tokens += (usage_sub.get("completion_tokens") or usage_sub.get("output_tokens") or 0)
                        found_in_generations = True
                    elif "prompt_tokens" in resp_meta or "input_tokens" in resp_meta:
                        gen_prompt_tokens += (resp_meta.get("prompt_tokens") or resp_meta.get("input_tokens") or 0)
                        gen_completion_tokens += (resp_meta.get("completion_tokens") or resp_meta.get("output_tokens") or 0)
                        found_in_generations = True

                # Extraer de generation_info
                elif isinstance(gen_info, dict):
                    usage_sub = gen_info.get("usage") or gen_info.get("token_usage")
                    if isinstance(usage_sub, dict):
                        gen_prompt_tokens += (usage_sub.get("prompt_tokens") or usage_sub.get("input_tokens") or 0)
                        gen_completion_tokens += (usage_sub.get("completion_tokens") or usage_sub.get("output_tokens") or 0)
                        found_in_generations = True

        # Priorizar la fuente encontrada
        if found_in_generations and not extracted_from_output:
            prompt_tokens = gen_prompt_tokens
            completion_tokens = gen_completion_tokens
        elif found_in_generations and extracted_from_output and (prompt_tokens == 0 and completion_tokens == 0):
            prompt_tokens = gen_prompt_tokens
            completion_tokens = gen_completion_tokens

        # Registrar el uso
        self.usage.add_usage(
            model_name=model_name or "unknown",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

    def __repr__(self) -> str:
        return f"TokenUsageCallbackHandler(usage={self.usage!r})"


@contextmanager
def track_token_usage(handler: Optional[TokenUsageCallbackHandler] = None) -> Generator[TokenUsageCallbackHandler, None, None]:
    """
    Context manager para registrar y monitorear el uso de tokens y costos en llamadas a LLMs y LangGraph.

    Uso:
        with track_token_usage() as cb:
            llm.invoke("Hola", config={"callbacks": [cb]})
            print(cb.total_tokens, cb.total_cost)
    """
    cb_handler = handler if handler is not None else TokenUsageCallbackHandler()
    try:
        yield cb_handler
    finally:
        pass
