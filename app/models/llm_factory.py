from langchain_google_genai import ChatGoogleGenerativeAI
from app.settings.settings import Settings

settings = Settings()

def get_llm(temperature: float = 0.0):
    """
    Retorna una instancia del LLM configurado en los ajustes de forma agnóstica al proveedor.
    """
    provider = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "google"
    model_name = settings.LLM_MODEL if settings.LLM_MODEL else "gemini-3.1-pro-preview"
    api_key = settings.LLM_API_KEY
    
    if provider == "google":
        return ChatGoogleGenerativeAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            top_p=0.7,
            max_retries=5,
            timeout=15,
        )
    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name,
                api_key=api_key, # type: ignore
                temperature=temperature,
                max_retries=5,
                timeout=15,
            )
        except ImportError:
            raise ImportError("Debe instalar 'langchain-openai' para usar modelos de OpenAI.")
    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name, # type: ignore
                api_key=api_key,
                temperature=temperature,
                max_retries=5,
                timeout=15,
            )
        except ImportError:
            raise ImportError("Debe instalar 'langchain-anthropic' para usar modelos de Anthropic.")
    else:
        # Intento de instanciación genérica si el proveedor no está mapeado explícitamente
        # pero existe en langchain (requiere langchain >= 0.2.13 para init_chat_model)
        try:
            from langchain.chat_models import init_chat_model
            return init_chat_model(model_name, model_provider=provider, temperature=temperature, api_key=api_key)
        except (ImportError, Exception):
            raise ValueError(f"Proveedor de LLM no soportado o no instalado: {provider}")
