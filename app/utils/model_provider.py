from ..settings.settings import Settings
from langchain_google_genai import ChatGoogleGenerativeAI # type: ignore

settings = Settings()

llm = ChatGoogleGenerativeAI(
        model= "gemini-flash-lite-latest",
        temperature=0,
        max_retries=2,
        google_api_key=settings.GEMINI_API_KEY,
        convert_system_message_to_human=True
    )

# llm_gemini_pro = ChatGoogleGenerativeAI(
#         model= "gemini-2.5-pro",
#         temperature=0,
#         max_retries=2,
#         google_api_key=settings.GEMINI_API_KEY,
#         convert_system_message_to_human=True
#     )