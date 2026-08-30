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

    # ==========================================
    # Terminal del agente revisor (seguridad)
    # ==========================================
    # Timeout en segundos para cada comando ejecutado por la tool terminal().
    # Configurable vía variable de entorno TERMINAL_TIMEOUT_SECONDS.
    TERMINAL_TIMEOUT_SECONDS: int = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", "30"))

    # ==========================================
    # Servidor MCP (bucle de herramientas)
    # ==========================================
    # Tope de ciclos agente->herramientas que el servidor procesa sin saltar a
    # la siguiente pausa humana al reanudar una tarea. Antes era un cap duro de
    # 20 que dejaba tareas a medio hacer y provocaba re-pausas fantasma con el
    # plan viejo. Configurable vía variable de entorno MCP_TOOL_LOOP_MAX.
    MCP_TOOL_LOOP_MAX: int = int(os.getenv("MCP_TOOL_LOOP_MAX", "50"))

    # ==========================================
    # Terminal del agente codificador
    # ==========================================
    # Si es True, el Agente Codificador recibe la tool terminal() para ejecutar
    # los tests (p. ej. pytest) y auto-validarlos ANTES de entregar el código.
    # Esto elimina la causa del bucle QA-rechaza → codificador por tests sin
    # validar. Configurable vía variable de entorno CODIFICADOR_TERMINAL_ENABLED.
    CODIFICADOR_TERMINAL_ENABLED: bool = os.getenv("CODIFICADOR_TERMINAL_ENABLED", "true").lower() in ("true", "1", "yes")

    # ==========================================
    # Índice de Proyecto (Optimización de Tokens)
    # ==========================================
    PROJECT_INDEX_ENABLED: bool = os.getenv("PROJECT_INDEX_ENABLED", "true").lower() in ("true", "1", "yes")
    PROJECT_INDEX_MAX_TOKENS_PER_FILE: int = int(os.getenv("PROJECT_INDEX_MAX_TOKENS_PER_FILE", "400"))
    PROJECT_INDEX_CACHE_DIR: str = os.getenv("PROJECT_INDEX_CACHE_DIR", ".project_index")

    # ==========================================
    # Búsqueda web del planificador (DuckDuckGo)
    # ==========================================
    # Desactivada por defecto: DuckDuckGo aplica rate-limits con reintentos
    # estériles que degradan la latencia del planificador. Activar solo si el
    # plan la necesita explícitamente.
    ENABLE_WEB_SEARCH: bool = os.getenv("ENABLE_WEB_SEARCH", "false").lower() in ("true", "1", "yes")
