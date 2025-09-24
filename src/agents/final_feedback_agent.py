import json
from typing import List, Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser # Usaremos un parser de cadena simple para la retroalimentación
from settings.settings import Settings
from langchain_google_genai import ChatGoogleGenerativeAI

settings = Settings()

LLM_FEEDBACK = ChatGoogleGenerativeAI(
        model= "gemini-2.5-flash-lite",
        temperature=1.0,
        max_retries=2,
        google_api_key=settings.GEMINI_API_KEY,
    )
class FinalFeedbackAgent:
    """
    Agente encargado de analizar el nuevo ticket y los tickets similares encontrados
    para generar una retroalimentación concisa y útil para el usuario.
    """
    def __init__(self):
        self.llm = LLM_FEEDBACK
        self.parser = StrOutputParser() # Queremos una cadena de texto legible, no JSON
        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Eres un asistente experto en soporte técnico. Tu tarea es generar una retroalimentación "
             "clara y útil para un nuevo ticket, basándote en cómo se resolvieron casos similares. "
             "La retroalimentación debe ser concisa, profesional y orientada a la acción. "
             "Destaca la causa raíz y la solución aplicada de los casos similares más relevantes. "
             "Si no hay tickets similares, indica que no se encontró información relevante."
             ),
            ("human",
             "Se ha ingresado un nuevo ticket con la siguiente descripción:\n"
             "**Descripción del Nuevo Ticket:** {new_ticket_description}\n\n"
             "Se han encontrado los siguientes tickets históricos resueltos que son similares:\n"
             "```json\n{similar_tickets_json}\n```\n\n"
             "Por favor, genera una retroalimentación detallada para el usuario sobre cómo se podría abordar "
             "el nuevo ticket, basándote en las soluciones de los casos similares. "
             "Si no hay tickets similares, indica que no se encontró información relevante. "
             "Formatea la respuesta de manera legible, usando viñetas o párrafos claros."
            )
        ])
        self.feedback_chain = self.prompt | self.llm | self.parser

    def generate_feedback(self, new_ticket_description: str, similar_tickets: List[Dict[str, Any]]) -> str:
        """
        Genera la retroalimentación final para el usuario.
        """
        print("\n[Agente de Retroalimentación Final]: Generando retroalimentación para el nuevo ticket...")
        
        if not similar_tickets:
            return "No se encontraron tickets resueltos similares en la base de conocimiento para proporcionar retroalimentación específica. Por favor, revisa la descripción del nuevo ticket o el tablero."

        # Formatear los tickets similares para el prompt del LLM
        # Solo incluimos los campos más relevantes para la retroalimentación
        formatted_similar_tickets = []
        for ticket in similar_tickets:
            formatted_similar_tickets.append({
                "item_id": ticket.get("item_id", "N/A"),
                "item_name": ticket.get("item_name", "Sin título"),
                "problem_summary": ticket.get("problem_summary", "Sin resumen"),
                "root_cause": ticket.get("root_cause", "No determinada"),
                "solution_applied": ticket.get("solution_applied", "No aplicada")
            })
        
        similar_tickets_json = json.dumps(formatted_similar_tickets, indent=2, ensure_ascii=False)

        try:
            feedback = self.feedback_chain.invoke({
                "new_ticket_description": new_ticket_description,
                "similar_tickets_json": similar_tickets_json
            })
            print("[Agente de Retroalimentación Final]: Retroalimentación generada exitosamente.")
            return feedback
        except Exception as e:
            print(f"[Agente de Retroalimentación Final]: Error al generar retroalimentación: {e}")
            return f"Ocurrió un error al generar la retroalimentación. Detalles: {e}"
