from pydantic import BaseModel
from pydantic_settings import BaseSettings # type: ignore
import os
from tempfile import TemporaryDirectory
from pathlib import Path

# Carga automática del archivo .env
from dotenv import load_dotenv # type: ignore

load_dotenv()

# Crear un único directorio temporal para toda la aplicación
_TEMP_DIRECTORY = TemporaryDirectory()
WORKING_DIRECTORY = Path(_TEMP_DIRECTORY.name)

class Settings(BaseSettings):
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.1-pro-preview")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "google-genai")
    LLM_THINKING: bool = os.getenv("LLM_THINKING", "false").lower() == "true"
    LLM_THINKING_BUDGET: int = int(os.getenv("LLM_THINKING_BUDGET", "1024"))
    SEARXNG_HOST: str = os.getenv("SEARXNG_HOST", "http://127.0.0.1:8888")
    HITL_ASK_FOR_READ: bool = os.getenv("HITL_ASK_FOR_READ", "false").lower() == "true"


settings = Settings()

def get_llm(temperature: float = 0.0):
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "google-genai" or provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Para Gemini 2.0 Flash Thinking o similares, el modelo se define en LLM_MODEL
        return ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
            top_p=0.7,
            max_retries=5,
            timeout=15,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        # Los modelos o1/o3-mini manejan el razonamiento internamente.
        # En versiones recientes se usa reasoning_effort o max_completion_tokens.
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY, # type: ignore
            temperature=temperature if "o1" not in settings.LLM_MODEL and "o3" not in settings.LLM_MODEL else 1, # o1 suele requerir temp 1 o no soportarla
            max_retries=5,
            timeout=15,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        
        extra_kwargs = {}
        if settings.LLM_THINKING and "claude-3-7" in settings.LLM_MODEL:
            extra_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": settings.LLM_THINKING_BUDGET
            }
            # Claude con thinking requiere temperature=1 y no soporta max_tokens normal si no es budget
            temperature = 1.0

        return ChatAnthropic(
            model_name=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY, # type: ignore
            temperature=temperature,
            max_retries=5,
            timeout=15,
            **extra_kwargs
        ) # type: ignore
    else:
        # Fallback to init_chat_model if available or just raise error
        try:
            from langchain.chat_models import init_chat_model
            return init_chat_model(
                model=settings.LLM_MODEL,
                model_provider=provider,
                temperature=temperature,
                api_key=settings.LLM_API_KEY,
            )
        except ImportError:
            raise ValueError(f"Proveedor de LLM no soportado o falta instalar su librería: {provider}")