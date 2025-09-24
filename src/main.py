import os
from dotenv import load_dotenv
from src.agents.ui_orchestration_agent import UIOchestrationAgent

# Cargar variables de entorno desde .env
load_dotenv()

if __name__ == "__main__":
    # Asegúrate de que las claves de API necesarias estén configuradas
    monday_api_key = os.getenv("MONDAY_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY") # Verificar la clave de API de OpenAI

    if not monday_api_key:
        print("\nADVERTENCIA: La variable de entorno MONDAY_API_KEY no está configurada.")
        print("Por favor, crea un archivo .env en la raíz del proyecto con MONDAY_API_KEY=tu_clave_api_real_de_monday.")
        print("El agente de recuperación de datos no funcionará correctamente sin una clave válida.")
        # exit() # Considera salir aquí si es esencial para la demostración

    if not openai_api_key:
        print("\nADVERTENCIA: La variable de entorno OPENAI_API_KEY no está configurada.")
        print("El agente de destilación de conocimiento y el agente de retroalimentación final podrían no funcionar correctamente sin una clave válida si usan OpenAI.")
        # exit() # Considera salir aquí si es esencial para la demostración

    orchestrator = UIOchestrationAgent()
    orchestrator.run()
