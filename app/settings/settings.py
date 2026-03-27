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
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")