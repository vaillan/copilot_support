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


settings = Settings()

def get_llm(temperature: float = 0.0):
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "google-genai" or provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
            top_p=0.7,
            max_retries=5,
            timeout=15,
            transport='grpc_asyncio',
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY, # type: ignore
            temperature=temperature,
            max_retries=5,
            timeout=15,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model_name=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
            max_retries=5,
            timeout=15,
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