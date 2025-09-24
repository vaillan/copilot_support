import json
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
import datetime
from settings.settings import Settings
# Importar la herramienta CSV
from tools.csv_knowledge_tools import append_to_knowledge_csv_tool

settings = Settings()

LLM = ChatGoogleGenerativeAI(
        model= "gemini-2.5-flash-lite",
        temperature=1.0,
        max_retries=2,
        google_api_key=settings.GEMINI_API_KEY,
    )

class KnowledgeDistillationAgent:
    """
    Agente encargado de destilar información de tickets históricos usando un LLM
    y almacenarla en la base de conocimiento CSV.
    """
    def __init__(self):
        self.llm = LLM
        self.parser = JsonOutputParser()
        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "Eres un experto en análisis de tickets de soporte y gestión de conocimiento. "
             "Tu tarea es destilar información clave de tickets históricos de monday.com. "
             "Debes ser extremadamente fiel a los datos proporcionados y NO inventar información. "
             "Si no puedes determinar un campo con certeza, indícalo explícitamente. "
             "La salida debe ser un objeto JSON con los campos especificados."),
            ("human",
             "Procesa CADA UNO de los ítems en la lista de datos históricos proporcionada.\n"
             "**Tu principal directiva es la FIDELIDAD a los datos de entrada. NO debes inventar, suponer o inferir información que no pueda ser respaldada directamente por el texto proporcionado.**\n\n"
             "Datos del ítem:\n"
             "```json\n{item_data}\n```\n\n"
             "Para cada ítem, sigue estas reglas para destilar la información:\n"
             "1.  **Campos Directos (`item_id`, `board_name`, `item_name`, `source_date`):** Cópialos exactamente como vienen.\n"
             "2.  **`problem_summary`:** Crea un resumen conciso, pero utiliza únicamente frases y conceptos presentes en la `description` o en la `resolution` del ítem. Si no es claro, escribe 'No es posible determinar con la información proporcionada'.\n"
             "3.  **`root_cause` y `solution_applied` (Los más importantes):**\n"
             "    -   Busca evidencia explícita en la `resolution` o `description`.\n"
             "    -   Si el texto no lo declara explícitamente, puedes hacer una inferencia LÓGICA y CONSERVADORA basada en pistas fuertes (ej. si la descripción menciona 'error de configuración' y la resolución 'se ajustó la configuración', es razonable inferir una 'corrección de configuración').\n"
             "    -   **REGLA DE ORO:** Si después de analizar las pistas, la causa o la solución no son claras o requieren una suposición grande, DEBES escribir en el campo correspondiente: **'No es posible determinar con la información proporcionada'**.\n"
             "4.  **`keywords`:** Extrae términos y frases directamente de los campos `item_name`, `description`, `resolution`, `status`. No inventes palabras clave. Genera una lista de 3-5 palabras clave relevantes, separadas por comas.\n\n"
             "Formato de salida JSON esperado:\n"
             "```json\n"
             "{{\n"
             "  \"item_id\": \"string\",\n"
             "  \"board_name\": \"string\",\n"
             "  \"item_name\": \"string\",\n"
             "  \"problem_summary\": \"string\",\n"
             "  \"root_cause\": \"string\",\n"
             "  \"solution_applied\": \"string\",\n"
             "  \"keywords\": \"string, string, string\",\n"
             "  \"source_date\": \"YYYY-MM-DD\"\n"
             "}}\n"
             "```\n"
             "Asegúrate de que 'keywords' sea una cadena de texto separada por comas."
            )
        ])
        self.distillation_chain = self.prompt | self.llm | self.parser

    def distill_and_store_knowledge(self, raw_tickets: List[dict], board_name: str) -> dict:
        """
        Procesa una lista de tickets crudos, destila la información usando un LLM
        y la almacena en la base de conocimiento CSV si cumple los criterios de calidad.
        """
        processed_count = 0
        added_to_csv_count = 0
        omitted_count = 0
        
        report_messages = []

        if not raw_tickets:
            return {
                "report": "No se proporcionaron tickets para destilar.",
                "processed_count": 0,
                "added_to_csv_count": 0,
                "omitted_count": 0,
                "distilled_tickets": [] # Devolver tickets destilados para el vector store
            }

        distilled_tickets_for_vector_store = []

        for i, ticket in enumerate(raw_tickets):
            processed_count += 1
            print(f"\n[Agente de Generación de Retroalimentación]: Destilando ticket {i+1}/{len(raw_tickets)} (ID: {ticket.get('id', 'N/A')})...")
            
            # Añadir board_name y source_date al ticket para el LLM
            ticket_with_context = {
                **ticket,
                "board_name": board_name,
                "source_date": datetime.date.today().isoformat() # Usar la fecha actual como fecha de origen
            }

            try:
                # Invocar la cadena de destilación
                distilled_data = self.distillation_chain.invoke({"item_data": json.dumps(ticket_with_context, indent=2, ensure_ascii=False)})
                
                # Validar los campos clave según la REGLA DE ORO
                if (distilled_data.get('problem_summary') == 'No es posible determinar con la información proporcionada' or
                    distilled_data.get('root_cause') == 'No es posible determinar con la información proporcionada' or
                    distilled_data.get('solution_applied') == 'No es posible determinar con la información proporcionada'):
                    
                    omitted_count += 1
                    report_messages.append(f"Ticket ID {ticket.get('id', 'N/A')} omitido del CSV: Campos clave no determinados.")
                    print(f"  - Omitido: Campos clave no determinados para el ticket ID {ticket.get('id', 'N/A')}.")
                else:
                    # Si los campos clave son válidos, intentar añadir al CSV
                    csv_tool_result = append_to_knowledge_csv_tool.invoke({"data": distilled_data})
                    report_messages.append(f"Ticket ID {ticket.get('id', 'N/A')} - CSV Tool: {csv_tool_result}")
                    print(f"  - CSV Tool: {csv_tool_result}")
                    if "añadido exitosamente" in csv_tool_result or "ya existe" in csv_tool_result:
                        added_to_csv_count += 1
                        distilled_tickets_for_vector_store.append(distilled_data) # Añadir a la lista para el vector store
            except Exception as e:
                omitted_count += 1
                report_messages.append(f"Error al destilar/añadir ticket ID {ticket.get('id', 'N/A')}: {e}")
                print(f"  - Error: {e} para el ticket ID {ticket.get('id', 'N/A')}.")

        final_report = (
            f"Informe de Destilación de Conocimiento:\n"
            f"  - Ítems procesados: {processed_count}\n"
            f"  - Ítems añadidos/existentes en CSV: {added_to_csv_count}\n"
            f"  - Ítems omitidos (por falta de información o error): {omitted_count}\n"
            f"Detalles:\n" + "\n".join(report_messages)
        )
        print(final_report)

        return {
            "report": final_report,
            "processed_count": processed_count,
            "added_to_csv_count": added_to_csv_count,
            "omitted_count": omitted_count,
            "distilled_tickets": distilled_tickets_for_vector_store # Pasar tickets destilados para el vector store
        }
