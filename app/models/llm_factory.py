"""
Fábrica de Modelos LLM Multi-Proveedor para Copilot Support.

Soporta OpenAI, Anthropic, Google Gemini, Ollama, Azure, AWS Bedrock y OpenRouter
con configuración desacoplada, limitador de tasa en memoria (InMemoryRateLimiter)
y soporte para fallbacks.
"""

from functools import lru_cache
from typing import Any, Dict, Optional
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_ollama import ChatOllama
from app.settings.settings import Settings

settings = Settings()

provider_map = {
    "google": "google_genai",
    "openai": "openai",
    "anthropic": "anthropic",
    "open-router": "openrouter",
    "local": "ollama",
    "azure": "azure_openai",
    "aws-bedrock": "bedrock_converse",
    "huggingface": "huggingface",
}


def _create_llm(
    provider: Optional[str],
    model_name: Optional[str],
    api_key: Optional[str],
    temperature: float = 0.0,
    **kwargs: Any
):
    """
    Instancia y retorna un modelo de lenguaje según el proveedor y parámetros especificados.
    """
    prov = (provider.lower() if provider else "google_genai").strip()
    mod = model_name.strip() if model_name else "gemini-1.5-pro"
    mapped_provider = provider_map.get(prov, prov)

    rate_limiter = None
    requests_per_second = getattr(settings, "LLM_REQUESTS_PER_SECOND", 0.0)
    if requests_per_second and requests_per_second > 0:
        checks_per_second = getattr(settings, "LLM_CHECKS_PER_SECOND", 10.0)
        check_every_n_seconds = 1.0 / checks_per_second if checks_per_second > 0 else 0.1
        rate_limiter = InMemoryRateLimiter(
            requests_per_second=requests_per_second,
            check_every_n_seconds=check_every_n_seconds
        )

    if mapped_provider == "ollama":
        ollama_kwargs: Dict[str, Any] = {
            "model": mod,
            "temperature": temperature,
        }
        if rate_limiter:
            ollama_kwargs["rate_limiter"] = rate_limiter
        ollama_kwargs.update(kwargs)
        return ChatOllama(**ollama_kwargs)
    else:
        try:
            init_kwargs: Dict[str, Any] = {
                "model": mod,
                "model_provider": mapped_provider,
                "temperature": temperature,
                "api_key": api_key,
                "max_retries": 5,
                "timeout": 10000
            }
            if rate_limiter:
                init_kwargs["rate_limiter"] = rate_limiter
            init_kwargs.update(kwargs)
            return init_chat_model(**init_kwargs)
        except (ImportError, Exception) as e:
            raise ValueError(f"Error al inicializar el modelo {mod} con proveedor {mapped_provider}: {e}")


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado en los ajustes generales de forma agnóstica al proveedor.
    """
    return _create_llm(
        settings.LLM_PROVIDER,
        settings.LLM_MODEL,
        settings.LLM_API_KEY,
        temperature
    )


@lru_cache(maxsize=2)
def get_planner_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Planificador/Arquitecto.
    """
    provider = settings.PLANNER_PROVIDER or settings.LLM_PROVIDER
    model = settings.PLANNER_MODEL or settings.LLM_MODEL
    api_key = settings.PLANNER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)


@lru_cache(maxsize=2)
def get_coder_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Programador/Codificador.
    """
    provider = settings.CODER_PROVIDER or settings.LLM_PROVIDER
    model = settings.CODER_MODEL or settings.LLM_MODEL
    api_key = settings.CODER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)


@lru_cache(maxsize=2)
def get_reviewer_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Revisor/QA.
    """
    provider = settings.REVIEWER_PROVIDER or settings.LLM_PROVIDER
    model = settings.REVIEWER_MODEL or settings.LLM_MODEL
    api_key = settings.REVIEWER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)
