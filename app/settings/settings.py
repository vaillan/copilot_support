from pydantic import BaseModel
from pydantic_settings import BaseSettings # type: ignore
import os
from pathlib import Path

from dotenv import load_dotenv # type: ignore

load_dotenv()

WORKING_DIRECTORY = Path(os.getenv('WORKING_DIRECTORY', os.getcwd()))

class Settings(BaseSettings):
    """
    Configuración global de la aplicación.
    
    Gestiona las variables de entorno para el proveedor del LLM, el modelo
    específico y la clave de API necesaria para la autenticación.
    """
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
