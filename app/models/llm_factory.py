from langchain.chat_models import init_chat_model
from app.settings.settings import Settings
from functools import lru_cache
from langchain_ollama import ChatOllama

settings = Settings()

@lru_cache(maxsize=2)
def get_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado en los ajustes de forma agnóstica al proveedor.
    Utiliza init_chat_model, la mejor práctica en LangChain v1.0 para inicialización dinámica.
    Documentación oficial de LangChain: https://docs.langchain.com/oss/python/langchain/models#azure 
    """
    provider = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "google_genai"
    model_name = settings.LLM_MODEL if settings.LLM_MODEL else "gemini-1.5-pro"
    api_key = settings.LLM_API_KEY
    
    provider_map = {
        "google": "google_genai",
        "openai": "openai",
        "anthropic": "anthropic",
        "open-router": "openrouter",
        "local": "ollama",
        "azure":"azure_openai",
        "aws-bedrock":"bedrock_converse",
        "huggingface":"huggingface",
    }
    
    mapped_provider = provider_map.get(provider, provider)
    
    if mapped_provider == "ollama":
        return ChatOllama(
            model=model_name,
            temperature=temperature,
        )
    else:
        try:
            return init_chat_model(
                model=model_name, 
                model_provider=mapped_provider, 
                temperature=temperature, 
                api_key=api_key,
                max_retries=5,
                timeout=10000
            )
        except (ImportError, Exception) as e:
            raise ValueError(f"Error al inicializar el modelo {model_name} con proveedor {mapped_provider}: {e}")
