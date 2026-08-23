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

    PLANNER_API_KEY: str = os.getenv("PLANNER_API_KEY", "")
    PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "")
    PLANNER_PROVIDER: str = os.getenv("PLANNER_PROVIDER", "")

    CODER_API_KEY: str = os.getenv("CODER_API_KEY", "")
    CODER_MODEL: str = os.getenv("CODER_MODEL", "")
    CODER_PROVIDER: str = os.getenv("CODER_PROVIDER", "")

    REVIEWER_API_KEY: str = os.getenv("REVIEWER_API_KEY", "")
    REVIEWER_MODEL: str = os.getenv("REVIEWER_MODEL", "")
    REVIEWER_PROVIDER: str = os.getenv("REVIEWER_PROVIDER", "")

    LLM_REQUESTS_PER_SECOND: float = float(os.getenv("LLM_REQUESTS_PER_SECOND", "0.0"))
    LLM_CHECKS_PER_SECOND: float = float(os.getenv("LLM_CHECKS_PER_SECOND", "10.0"))
    # Timeout en SEGUNDOS para las llamadas al LLM (init_chat_model). Default 60s.
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60"))

    # ==========================================
    # Índice de Proyecto (Optimización de Tokens)
    # ==========================================
    PROJECT_INDEX_ENABLED: bool = os.getenv("PROJECT_INDEX_ENABLED", "true").lower() in ("true", "1", "yes")
    PROJECT_INDEX_MAX_TOKENS_PER_FILE: int = int(os.getenv("PROJECT_INDEX_MAX_TOKENS_PER_FILE", "400"))
    PROJECT_INDEX_CACHE_DIR: str = os.getenv("PROJECT_INDEX_CACHE_DIR", ".project_index")
    PROJECT_INDEX_MAX_FILE_SIZE: int = int(os.getenv("PROJECT_INDEX_MAX_FILE_SIZE", "1048576"))  # 1 MB, igual al hardcode actual
    PROJECT_INDEX_MAX_DEPTH: int = int(os.getenv("PROJECT_INDEX_MAX_DEPTH", "5"))
    # Lista separada por comas de patrones de directorios/archivos a excluir
    # del índice (coincidencia case-insensitive por nombre). Vacía por defecto.
    PROJECT_INDEX_EXCLUDE_PATTERNS: str = os.getenv("PROJECT_INDEX_EXCLUDE_PATTERNS", "")

    # ==========================================
    # Terminal (Optimización de Contexto)
    # ==========================================
    TERMINAL_MAX_OUTPUT_LINES: int = int(os.getenv("TERMINAL_MAX_OUTPUT_LINES", "200"))
    TERMINAL_MAX_CHARS_PER_LINE: int = int(os.getenv("TERMINAL_MAX_CHARS_PER_LINE", "500"))

    # ==========================================
    # Git Diff (Optimización de Contexto)
    # ==========================================
    GIT_DIFF_MAX_FILE_SIZE: int = int(os.getenv("GIT_DIFF_MAX_FILE_SIZE", "1048576"))  # 1 MB
