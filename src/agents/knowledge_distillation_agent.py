import json
from typing import List, Dict, Any, Optional
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
        temperature=0,
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
             "Eres un analista de soporte técnico senior. Tu tarea es analizar en profundidad los datos de un ticket resuelto para destilar la causa raíz y la solución, incluso si no están explícitamente declaradas. "
             "Debes actuar como un detective, conectando las pistas disponibles. "
             "Tu objetivo final es generar un objeto JSON estructurado con tu análisis."),
            ("human",
             "Analiza el siguiente ítem de datos históricos de un ticket resuelto. Sigue un proceso de razonamiento paso a paso antes de generar la salida final.\n\n"
             "**Datos del Ítem:**\n"
             "```json\n{item_data}\n```\n\n"
             "**Proceso de Razonamiento (piensa paso a paso):**\n"
             "1.  **Identifica el Problema Principal:** Lee `item_name`, `descripcion_completa` y los primeros `item_updates_details` para entender claramente cuál fue el problema reportado por el usuario.\n"
             "2.  **Busca Pistas de la Solución:** Analiza TODOS los `item_updates_details` en orden cronológico. Presta especial atención a los comentarios de los `responsable_desarrollo` o `responsable_soporte`. Busca frases como 'se corrigió', 'se ajustó', 'se implementó', 'el problema era', 'la causa fue'. Analiza también el `all_attached_files_extracted_text_summary` en busca de pistas.\n"
             "3.  **Infiere la Causa Raíz y la Solución:** Basado en tu análisis de las pistas, formula una hipótesis sobre la causa raíz (`root_cause`) y la solución aplicada (`solution_applied`).\n"
             "    -   **Ejemplo de Inferencia:** Si el problema era un 'error al guardar' y un desarrollador comenta 'se ajustó el endpoint de guardado', la causa raíz fue 'un error en el endpoint' y la solución fue 'ajuste del código del endpoint'.\n"
             "    -   **Ejemplo de Inferencia 2:** Si el problema es un error de cálculo y el `estatus` cambia a 'Terminado' después de la intervención de un desarrollador, pero no hay comentarios, puedes inferir que la solución fue una 'corrección de código no especificada'.\n"
             "4.  **Aplica la REGLA DE ORO:** Si después de tu análisis exhaustivo, no hay absolutamente ninguna pista (ni comentarios, ni cambios de estado relevantes, ni adjuntos útiles) que te permita formular una hipótesis razonable, y solo en ese caso, DEBES escribir en los campos `root_cause` y `solution_applied`: **'No es posible determinar con la información proporcionada'**.\n\n"
             "**Generación de Salida:**\n"
             "Después de tu razonamiento, genera un único objeto JSON con la información destilada. NO incluyas tu razonamiento en el JSON final.\n\n"
             "**Formato de salida JSON esperado:**\n"
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
             "```"
            )
        ])
        self.distillation_chain = self.prompt | self.llm | self.parser

    def distill_and_store_knowledge(self, raw_tickets: List[Dict[str, Any]], board_name: str) -> Dict[str, Any]:
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
                "distilled_tickets": []
            }

        distilled_tickets_for_vector_store = []

        for i, ticket in enumerate(raw_tickets):
            processed_count += 1
            print(f"\n[Agente de Destilación de Conocimiento]: Analizando y destilando ticket {i+1}/{len(raw_tickets)} (ID: {ticket.get('item_id', 'N/A')})...")
            
            # Pre-procesamiento para simplificar la entrada al LLM
            # Un resumen de los updates puede ser más útil que el texto completo si es muy largo
            updates_summary = "\n".join([f"- {update['created_at']} por {update['creator_name']}: {update['body_cleaned'][:200]}..." for update in ticket.get('item_updates_details', [])])

            ticket_with_context = {
                "item_id": ticket.get("item_id", "N/A"),
                "board_name": board_name,
                "item_name": ticket.get("item_name", "N/A"),
                "descripcion_completa": ticket.get("descripcion_completa", ""),
                "responsable_desarrollo": ticket.get("responsable_desarrollo", ""),
                "estatus": ticket.get("estatus", ""),
                "item_updates_summary": updates_summary, # Pasamos un resumen de los updates
                "all_attached_files_extracted_text_summary": ticket.get("all_attached_files_extracted_text_summary", "")[:1000], # Truncamos para no exceder el límite de tokens
                "source_date": ticket.get('fecha_real_post_servicio', datetime.date.today().isoformat())
            }

            try:
                distilled_data = self.distillation_chain.invoke({"item_data": json.dumps(ticket_with_context, indent=2, ensure_ascii=False)})
                
                if (distilled_data.get('root_cause') == 'No es posible determinar con la información proporcionada' or
                    distilled_data.get('solution_applied') == 'No es posible determinar con la información proporcionada'):
                    
                    omitted_count += 1
                    report_messages.append(f"Ticket ID {ticket.get('item_id', 'N/A')} omitido del CSV: Causa/Solución no inferida.")
                    print(f"  - Omitido: Causa/Solución no inferida para el ticket ID {ticket.get('item_id', 'N/A')}.")
                else:
                    csv_tool_result = append_to_knowledge_csv_tool.invoke({"data": distilled_data})
                    report_messages.append(f"Ticket ID {ticket.get('item_id', 'N/A')} - CSV Tool: {csv_tool_result}")
                    print(f"  - CSV Tool: {csv_tool_result}")
                    if "añadido exitosamente" in csv_tool_result or "ya existe" in csv_tool_result:
                        added_to_csv_count += 1
                        distilled_tickets_for_vector_store.append(distilled_data)
            except Exception as e:
                omitted_count += 1
                report_messages.append(f"Error al destilar/añadir ticket ID {ticket.get('item_id', 'N/A')}: {e}")
                print(f"  - Error: {e} para el ticket ID {ticket.get('item_id', 'N/A')}.")

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
            "distilled_tickets": distilled_tickets_for_vector_store
        }