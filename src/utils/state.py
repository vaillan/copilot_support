from typing import Any, Dict, List, Optional, TypedDict

# Estado para el Flujo 1: Análisis en Tiempo Real
class AnalysisState(TypedDict):
    item_id: str                 # Input inicial
    raw_data_json: str           # Output del Ingeniero
    diagnostic_report: str       # Output del Super Analista
    action_plan: str             # Output del Analista de Negocio
    error: str                   # Para manejar fallos

# Estado para el Flujo 2: Destilación de Conocimiento
class ArchivingState(TypedDict):
    item_id: str                 # Input inicial
    raw_data_json: str           # Output del Ingeniero
    distilled_csv_row: str       # Output del Archivista
    save_confirmation: str       # Confirmación de guardado
    error: str

# Re-definición del estado para asegurar que esté disponible en este bloque
class AgentState(TypedDict):
    board_name: str
    new_ticket_description: str
    similar_tickets_found: List[Dict[str, Any]] # Ahora almacenará los datos reales recuperados
    generated_feedback: Optional[str]
    user_confirmation: Optional[bool]
    ticket_created_status: Optional[str]
    error_message: Optional[str]