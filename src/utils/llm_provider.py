from langchain_google_genai import ChatGoogleGenerativeAI
from ..settings.settings import Settings

settings = Settings()

gemini_llm = ChatGoogleGenerativeAI(
    model= "gemini-2.5-flash-lite",
    temperature=0,
    max_retries=2,
    google_api_key=settings.GEMINI_API_KEY,
)