from pydantic_settings import BaseSettings # type: ignore
import os

# Carga automática del archivo .env
from dotenv import load_dotenv # type: ignore
load_dotenv()

class Settings(BaseSettings):
    _MONDAY_API_KEY: str = os.getenv("MONDAY_API_KEY", "")
    _MONDAY_API_URL: str = os.getenv("MONDAY_API_URL", "")
    _GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    @property
    def MONDAY_API_KEY(self):
        return self._MONDAY_API_KEY

    @property
    def MONDAY_API_URL(self):
        return self._MONDAY_API_URL

    @property
    def GEMINI_API_KEY(self):
        return self._GEMINI_API_KEY