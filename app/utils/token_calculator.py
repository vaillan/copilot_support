"""
Módulo para el conteo de tokens y cálculo de costos agnóstico a proveedores en LangChain y LangGraph.

Permite monitorear el uso de tokens (prompt, completion y total) y calcular el costo
monetario estimado para modelos de OpenAI, Anthropic, Google Gemini, Ollama y otros proveedores,
así como detectar umbrales de advertencia y límites de ventana de contexto.
"""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
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

    # Modelos locales / Ollama
    "ollama": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.1": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.2": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "llama3.3": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "mistral": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "qwen": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
    "deepseek-r1": ModelPricing(input_cost_per_1m=0.00, output_cost_per_1m=0.00),
}

# Límites de ventana de contexto estándar (número máximo de tokens)
DEFAULT_CONTEXT_WINDOWS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3-mini": 200_000,

    # Anthropic
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,

    # Google Gemini
    "gemini-1.5-pro": 2_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,

    # Ollama / Modelos abiertos
    "llama3": 8_192,
    "llama3.1": 128_000,
    "llama3.2": 128_000,
    "llama3.3": 128_000,
    "mistral": 32_768,
    "qwen": 32_768,
    "deepseek-r1": 64_000,
}

_CUSTOM_MODEL_PRICING: Dict[str, ModelPricing] = {}
_CUSTOM_CONTEXT_WINDOWS: Dict[str, int] = {}


def register_model_pricing(model_name: str, input_cost_per_1m: float, output_cost_per_1m: float) -> None:
    """
    Registra o sobreescribe la tarifa de precios para un modelo específico.
    """
    key = model_name.strip().lower()
    _CUSTOM_MODEL_PRICING[key] = ModelPricing(
        input_cost_per_1m=float(input_cost_per_1m),
        output_cost_per_1m=float(output_cost_per_1m)
    )


def register_context_window(model_name: str, max_tokens: int) -> None:
    """
    Registra o sobreescribe el límite de ventana de contexto para un modelo.
    """
    key = model_name.strip().lower()
    _CUSTOM_CONTEXT_WINDOWS[key] = int(max_tokens)


def get_model_pricing(model_name: str) -> Optional[ModelPricing]:
    """
    Obtiene la tarifa de precios asociada a un modelo dado, buscando coincidencias
    exactas o por prefijo/subcadena.
    """
    if not model_name:
        return None

    clean_name = model_name.strip().lower()

    if clean_name in _CUSTOM_MODEL_PRICING:
        return _CUSTOM_MODEL_PRICING[clean_name]

    if clean_name in DEFAULT_MODEL_PRICING:
        return DEFAULT_MODEL_PRICING[clean_name]

    for key, pricing in _CUSTOM_MODEL_PRICING.items():
        if key in clean_name or clean_name in key:
            return pricing

    for key in sorted(DEFAULT_MODEL_PRICING.keys(), key=len, reverse=True):
        if key in clean_name:
            return DEFAULT_MODEL_PRICING[key]

    return None


def get_context_window_limit(model_name: str, default_limit: int = 128_000) -> int:
    """
    Obtiene el límite máximo de tokens para la ventana de contexto del modelo.
    """
    if not model_name:
        return default_limit

    clean_name = model_name.strip().lower()

    if clean_name in _CUSTOM_CONTEXT_WINDOWS:
        return _CUSTOM_CONTEXT_WINDOWS[clean_name]

    if clean_name in DEFAULT_CONTEXT_WINDOWS:
        return DEFAULT_CONTEXT_WINDOWS[clean_name]

    for key, window in _CUSTOM_CONTEXT_WINDOWS.items():
        if key in clean_name or clean_name in key:
            return window

    for key in sorted(DEFAULT_CONTEXT_WINDOWS.keys(), key=len, reverse=True):
        if key in clean_name:
            return DEFAULT_CONTEXT_WINDOWS[key]

    return default_limit


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


def estimate_tokens_from_text(text: str) -> int:
    """
    Estima de forma heurística y robusta el conteo de tokens a partir de una cadena de texto.
    Aproximación estándar en la industria (~3.8 caracteres por token + tokens de margen).
    """
    if not text:
        return 0
    return max(1, int(len(text) / 3.8) + 1)


def count_tokens_in_messages(
    messages: List[Union[BaseMessage, Dict[str, Any], str]],
    model_name: str = "gpt-4o"
) -> int:
    """
    Calcula o estima el número total de tokens contenidos en una lista de mensajes.
    Incluye overhead de formateo por mensaje (role, delimiters).
    """
    if not messages:
        return 0

    total_tokens = 0
    message_overhead = 4

    for msg in messages:
        total_tokens += message_overhead
        content = ""
        if isinstance(msg, str):
            content = msg
        elif isinstance(msg, dict):
            content = str(msg.get("content", ""))
        elif hasattr(msg, "content"):
            c = msg.content
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                parts = []
                for item in c:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        parts.append(str(item["text"]))
                    else:
                        parts.append(str(item))
                content = " ".join(parts)
            else:
                content = str(c)

        total_tokens += estimate_tokens_from_text(content)

    total_tokens += 3
    return total_tokens


@dataclass
class ContextWindowStatus:
    """
    Estado de la ventana de contexto y umbrales de uso.
    """
    total_tokens: int
    max_tokens: int
    usage_ratio: float
    is_warning: bool
    is_overflow: bool
    remaining_tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "usage_ratio": round(self.usage_ratio, 4),
            "is_warning": self.is_warning,
            "is_overflow": self.is_overflow,
            "remaining_tokens": self.remaining_tokens,
        }


def check_context_window_threshold(
    messages: List[Union[BaseMessage, Dict[str, Any], str]],
    model_name: str = "gpt-4o",
    warning_threshold_ratio: float = 0.8,
    max_tokens_override: Optional[int] = None
) -> ContextWindowStatus:
    """
    Evalúa si el historial de mensajes actual supera los umbrales de advertencia
    o desbordamiento de la ventana de contexto del modelo seleccionado.
    """
    total_tokens = count_tokens_in_messages(messages, model_name=model_name)
    max_tokens = max_tokens_override if max_tokens_override is not None else get_context_window_limit(model_name)
    
    if max_tokens <= 0:
        max_tokens = 128_000

    usage_ratio = total_tokens / max_tokens
    is_warning = usage_ratio >= warning_threshold_ratio
    is_overflow = total_tokens >= max_tokens
    remaining = max(0, max_tokens - total_tokens)

    return ContextWindowStatus(
        total_tokens=total_tokens,
        max_tokens=max_tokens,
        usage_ratio=usage_ratio,
        is_warning=is_warning,
        is_overflow=is_overflow,
        remaining_tokens=remaining
    )


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

        # 2. Intentar extraer tokens de llm_output
        prompt_tokens = 0
        completion_tokens = 0
        extracted_from_output = False

        token_usage_dict = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(token_usage_dict, dict):
            prompt_tokens = token_usage_dict.get("prompt_tokens") or token_usage_dict.get("input_tokens") or 0
            completion_tokens = token_usage_dict.get("completion_tokens") or token_usage_dict.get("output_tokens") or 0
            extracted_from_output = True

        # 3. Extraer de las generaciones individuales
        gen_prompt_tokens = 0
        gen_completion_tokens = 0
        found_in_generations = False

        for gen_list in response.generations:
            for gen in gen_list:
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

                elif isinstance(gen_info, dict):
                    usage_sub = gen_info.get("usage") or gen_info.get("token_usage")
                    if isinstance(usage_sub, dict):
                        gen_prompt_tokens += (usage_sub.get("prompt_tokens") or usage_sub.get("input_tokens") or 0)
                        gen_completion_tokens += (usage_sub.get("completion_tokens") or usage_sub.get("output_tokens") or 0)
                        found_in_generations = True

        if found_in_generations and not extracted_from_output:
            prompt_tokens = gen_prompt_tokens
            completion_tokens = gen_completion_tokens
        elif found_in_generations and extracted_from_output and (prompt_tokens == 0 and completion_tokens == 0):
            prompt_tokens = gen_prompt_tokens
            completion_tokens = gen_completion_tokens

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
    """
    cb_handler = handler if handler is not None else TokenUsageCallbackHandler()
    try:
        yield cb_handler
    finally:
        pass
