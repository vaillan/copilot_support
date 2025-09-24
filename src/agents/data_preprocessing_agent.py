from typing import List, Dict, Any
import datetime

class DataPreprocessingAgent:
    """
    Agente encargado de limpiar y estructurar los datos crudos de monday.com.
    """
    def preprocess_tickets(self, raw_tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Limpia y estandariza los datos de los tickets.
        Asegura que los campos clave existan y sean cadenas.
        """
        processed_tickets = []
        for ticket in raw_tickets:
            processed_ticket = {
                "id": ticket.get("id", "N/A"),
                "name": ticket.get("name", "Sin título"),
                "description": ticket.get("description", "Sin descripción").strip(),
                "resolution": ticket.get("resolution", "Sin resolución").strip(),
                "status": ticket.get("status", "Desconocido").strip()
            }
            if not processed_ticket["description"]:
                processed_ticket["description"] = processed_ticket["name"]
            if not processed_ticket["resolution"]:
                processed_ticket["resolution"] = "No se proporcionó una resolución explícita."
            
            processed_tickets.append(processed_ticket)
        return processed_tickets

    def map_to_csv_format(self, ticket_data: Dict[str, Any], board_name: str) -> Dict[str, Any]:
        """
        Mapea un ticket preprocesado al formato esperado por la herramienta CSV.
        
        Args:
            ticket_data: Un diccionario de ticket preprocesado.
            board_name: El nombre del tablero de monday.com de donde proviene el ticket.
        
        Returns:
            Dict[str, Any]: Un diccionario con los campos para el CSV.
        """
        # Aquí se realiza el mapeo de los campos del ticket a los campos del CSV.
        # Puedes ajustar la lógica para 'problem_summary', 'root_cause', 'keywords'
        # En un escenario real, un LLM podría destilar esta información.
        # Por ahora, usaremos los campos existentes de forma directa o simple.
        
        # Para 'keywords', podríamos extraer palabras clave de la descripción/resolución
        # o simplemente usar una cadena vacía o un placeholder.
        keywords = f"{ticket_data['name'].lower()}, {ticket_data['status'].lower()}"
        if ticket_data['description']:
            keywords += f", {ticket_data['description'].lower().split(' ')[0]}" # Primera palabra de la descripción
        
        return {
            'item_id': ticket_data['id'],
            'board_name': board_name,
            'item_name': ticket_data['name'],
            'problem_summary': ticket_data['description'], # Usamos la descripción como resumen del problema
            'root_cause': ticket_data['resolution'],      # Usamos la resolución como causa raíz (simplificado)
            'solution_applied': ticket_data['resolution'], # La solución aplicada es la resolución
            'keywords': keywords,
            'source_date': datetime.date.today().isoformat() # Fecha actual como fecha de origen
        }
