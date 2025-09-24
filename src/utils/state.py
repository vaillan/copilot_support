from typing import List, TypedDict

# Re-definición del estado para asegurar que esté disponible en este bloque
class AgentState(TypedDict):
    board_name: str
    new_ticket_description: str
    similar_tickets_found: List[dict] # Ahora almacenará los datos reales recuperados
    generated_feedback: str
    user_confirmation: bool
    ticket_created_status: str
    error_message: str