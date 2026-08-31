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

    # NOTA (alineación prompt-modelo): el Planificador consume el prompt más
    # complejo del sistema (contrato estricto de tool-calls). Configure
    # PLANNER_MODEL con un modelo con tool-calling fiable; los modelos
    # "flash"/económicos tienden a responder con texto plano y provocar
    # bucles de reintento en el grafo.
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

    # ==========================================
    # Terminal del agente revisor (seguridad)
    # ==========================================
    # Timeout en segundos para cada comando ejecutado por la tool terminal().
    # Configurable vía variable de entorno TERMINAL_TIMEOUT_SECONDS.
    TERMINAL_TIMEOUT_SECONDS: int = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", "30"))

    # ==========================================
    # Índice de Proyecto (Optimización de Tokens)
    # ==========================================
    PROJECT_INDEX_ENABLED: bool = os.getenv("PROJECT_INDEX_ENABLED", "true").lower() in ("true", "1", "yes")
    PROJECT_INDEX_MAX_TOKENS_PER_FILE: int = int(os.getenv("PROJECT_INDEX_MAX_TOKENS_PER_FILE", "400"))
    PROJECT_INDEX_CACHE_DIR: str = os.getenv("PROJECT_INDEX_CACHE_DIR", ".project_index")

    # ==========================================
    # Regeneración de Tests (anti-bucle)
    # ==========================================
    # Activa/desactiva el mecanismo que exige actualizar pruebas tras un cambio completado en disco.
    TEST_REGENERATION_ENABLED: bool = os.getenv("TEST_REGENERATION_ENABLED", "true").lower() in ("true", "1", "yes")
    # Tope máximo de regeneraciones de tests por tarea; al alcanzarlo el mecanismo se detiene (evita bucles infinitos).
    TEST_REGENERATION_MAX_ITERATIONS: int = int(os.getenv("TEST_REGENERATION_MAX_ITERATIONS", "3"))
    # Segundos mínimos entre dos regeneraciones consecutivas (debounce para escrituras múltiples).
    TEST_REGENERATION_COOLDOWN_SECONDS: float = float(os.getenv("TEST_REGENERATION_COOLDOWN_SECONDS", "2.0"))
    # Directorios (separados por coma) cuyos archivos nunca disparan la regeneración (salidas del propio mecanismo).
    TEST_REGENERATION_EXCLUDED_DIRS: str = os.getenv("TEST_REGENERATION_EXCLUDED_DIRS", "tests")
