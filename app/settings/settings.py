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
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
