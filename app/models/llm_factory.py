from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from app.settings.settings import Settings
from functools import lru_cache
from langchain_ollama import ChatOllama

settings = Settings()

provider_map = {
    "google": "google_genai",
    "openai": "openai",
    "anthropic": "anthropic",
    # OpenRouter se enruta vía ChatOpenAI (API compatible con OpenAI) en lugar
    # de ChatOpenRouter: el paquete langchain-openrouter se cuelga indefinidamente
    # en algunas configuraciones Windows/httpx (httpx.ReadTimeout en cada intento),
    # lo que bloqueaba al Planificador ~9 min (4 intentos x 120s) hasta fallar.
    # ChatOpenAI + base_url responde en ~1-2s con tool-binding verificado.
    "open-router": "openai",
    "openrouter": "openai",
    "local": "ollama",
    "azure":"azure_openai",
    "aws-bedrock":"bedrock_converse",
    "huggingface":"huggingface",
}

# Endpoint OpenAI-compatible de OpenRouter (usado cuando el proveedor es open-router).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

def _create_llm(provider: str, model_name: str, api_key: str, temperature: float = 0.0):
    prov = provider.lower() if provider else "google_genai"
    mod = model_name if model_name else "gemini-1.5-pro"
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
        kwargs = {
            "model": mod,
            "temperature": temperature,
        }
        if rate_limiter:
            kwargs["rate_limiter"] = rate_limiter
        return ChatOllama(**kwargs)
    else:
        try:
            kwargs = {
                "model": mod,
                "model_provider": mapped_provider,
                "temperature": temperature,
                "api_key": api_key,
                "max_retries": 3,
                # Timeout HTTP en segundos. Antes era 10000 (interpretado como
                # ~2.8 horas por proveedores que lo leen en segundos), lo que
                # provocaba llamadas colgadas que solo morían con el timeout
                # global de la tarea MCP. 120s es suficiente incluso para
                # modelos lentos y evita bloquear el event loop del servidor.
                "timeout": 120
            }
            # OpenRouter expone una API compatible con OpenAI: basta con apuntar
            # base_url a su endpoint. NO usar langchain-openrouter (ChatOpenRouter),
            # que se cuelga en este entorno (ver comentario en provider_map).
            if prov in ("open-router", "openrouter"):
                kwargs["base_url"] = OPENROUTER_BASE_URL
            if rate_limiter:
                kwargs["rate_limiter"] = rate_limiter
            return init_chat_model(**kwargs)
        except (ImportError, Exception) as e:
            raise ValueError(f"Error al inicializar el modelo {mod} con proveedor {mapped_provider}: {e}")

@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado en los ajustes generales de forma agnóstica al proveedor.
    """
    return _create_llm(settings.LLM_PROVIDER, settings.LLM_MODEL, settings.LLM_API_KEY, temperature)

@lru_cache(maxsize=2)
def get_planner_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Planificador.
    """
    provider = settings.PLANNER_PROVIDER or settings.LLM_PROVIDER
    model = settings.PLANNER_MODEL or settings.LLM_MODEL
    api_key = settings.PLANNER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)

@lru_cache(maxsize=2)
def get_coder_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Codificador.
    """
    provider = settings.CODER_PROVIDER or settings.LLM_PROVIDER
    model = settings.CODER_MODEL or settings.LLM_MODEL
    api_key = settings.CODER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)

@lru_cache(maxsize=2)
def get_reviewer_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado específicamente para el Revisor.
    """
    provider = settings.REVIEWER_PROVIDER or settings.LLM_PROVIDER
    model = settings.REVIEWER_MODEL or settings.LLM_MODEL
    api_key = settings.REVIEWER_API_KEY or settings.LLM_API_KEY
    return _create_llm(provider, model, api_key, temperature)
