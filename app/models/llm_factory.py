from langchain.chat_models import init_chat_model
from app.settings.settings import Settings

settings = Settings()

def get_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado en los ajustes de forma agnóstica al proveedor.
    Utiliza init_chat_model, la mejor práctica en LangChain v1.0 para inicialización dinámica.
    """
    provider = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "google_genai"
    model_name = settings.LLM_MODEL if settings.LLM_MODEL else "gemini-3.1-pro-preview"
    api_key = settings.LLM_API_KEY
    
    # Mapeo de proveedores para init_chat_model
    provider_map = {
        "google": "google_genai",
        "openai": "openai",
        "anthropic": "anthropic",
        "open-router": "openrouter"
    }
    
    mapped_provider = provider_map.get(provider, provider)
    
    if mapped_provider == "openrouter":
        from langchain_openrouter import ChatOpenRouter
        return ChatOpenRouter(
            model=model_name, # type: ignore
            api_key=api_key, # type: ignore
            temperature=temperature,
            max_retries=2,
            timeout=30,
        )
        
    try:
        return init_chat_model(
            model=model_name, 
            model_provider=mapped_provider, 
            temperature=temperature, 
            api_key=api_key,
            max_retries=2,
            timeout=30
        )
    except (ImportError, Exception) as e:
        raise ValueError(f"Error al inicializar el modelo {model_name} con proveedor {mapped_provider}: {e}")
