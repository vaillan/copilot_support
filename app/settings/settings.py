from pydantic import BaseModel
from pydantic_settings import BaseSettings # type: ignore
import os

# Carga automática del archivo .env
from dotenv import load_dotenv # type: ignore

load_dotenv()

class DBCONFIG(BaseModel):
    host: str
    user: str
    port: int
    password: str
    database: str

class Settings(BaseSettings):
    MONDAY_API_KEY: str = os.getenv("MONDAY_API_KEY", "")
    MONDAY_API_URL: str = os.getenv("MONDAY_API_URL", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    HF_API_KEY: str = os.getenv("HF_API_KEY", "")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: float | str  = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30.0)
    
    DB_CONFIG: DBCONFIG = DBCONFIG(
        user=os.getenv("DB_USER", "valentin"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        password=os.getenv("DB_PASSWORD", "admin002210"),
        database=os.getenv("DB_NAME", "copilot")
    )
