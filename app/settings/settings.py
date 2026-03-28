from pydantic import BaseModel
from pydantic_settings import BaseSettings # type: ignore
import os
from tempfile import TemporaryDirectory
from pathlib import Path

from dotenv import load_dotenv # type: ignore

load_dotenv()

_TEMP_DIRECTORY = TemporaryDirectory()
WORKING_DIRECTORY = Path(_TEMP_DIRECTORY.name)
class Settings(BaseSettings):
    """
    Configuración global de la aplicación.
    
    Gestiona las variables de entorno para el proveedor del LLM, el modelo
    específico y la clave de API necesaria para la autenticación.
    """
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
