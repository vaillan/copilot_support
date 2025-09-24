import json
from utils.state import AgentState
from tools.monday_tools import data_extractor_board_tool
from agents.data_preprocessing_agent import DataPreprocessingAgent
from agents.knowledge_distillation_agent import KnowledgeDistillationAgent
from agents.knowledge_base_agent import KnowledgeBaseAgent
from agents.final_feedback_agent import FinalFeedbackAgent
from langgraph.graph import StateGraph, END

class UIOchestrationAgent:
    def __init__(self):
        self.workflow = StateGraph(AgentState)

        # Inicializar los agentes que se usarán en los nodos
        self.data_preprocessing_agent = DataPreprocessingAgent() # Puede ser útil para preprocesamiento inicial antes del LLM
        self.knowledge_base_agent = KnowledgeBaseAgent() # Se inicializa la base de conocimiento vectorial aquí
        self.knowledge_distillation_agent = KnowledgeDistillationAgent() # El nuevo agente LLM
        self.final_feedback_agent = FinalFeedbackAgent() # El nuevo agente de retroalimentación final

        # --- Definición de Nodos ---
        self.workflow.add_node("get_user_input", self._get_user_input_node)
        self.workflow.add_node("retrieve_monday_data", self._retrieve_monday_data_node)
        self.workflow.add_node("distill_and_store_knowledge_csv", self._distill_and_store_knowledge_csv_node)
        # Este nodo ahora se encarga de la búsqueda en la base de conocimiento vectorial Y la generación de retroalimentación final
        self.workflow.add_node("find_similar_and_generate_feedback", self._find_similar_and_generate_feedback_node)
        self.workflow.add_node("ask_user_confirmation", self._ask_user_confirmation_node)
        self.workflow.add_node("create_ticket_monday", self._placeholder_create_ticket_monday)


        # --- Definición de Transiciones ---
        self.workflow.set_entry_point("get_user_input")
        self.workflow.add_edge("get_user_input", "retrieve_monday_data")
        self.workflow.add_edge("retrieve_monday_data", "distill_and_store_knowledge_csv")
        self.workflow.add_edge("distill_and_store_knowledge_csv", "find_similar_and_generate_feedback")
        self.workflow.add_edge("find_similar_and_generate_feedback", "ask_user_confirmation")
        self.workflow.add_conditional_edges(
            "ask_user_confirmation",
            self._decide_on_ticket_creation,
            {
                "create_ticket": "create_ticket_monday",
                "end_process": END
            }
        )
        self.workflow.add_edge("create_ticket_monday", END)

        self.app = self.workflow.compile()

    # --- Nodos del Grafo ---
    def _get_user_input_node(self, state: AgentState) -> dict:
        """
        Nodo para obtener la entrada inicial del usuario.
        """
        print("\n--- Agente de Interfaz de Usuario y Orquestación ---")
        board_name = input("Por favor, introduce el nombre del tablero de monday.com: ")
        new_ticket_description = input("Describe el nuevo ticket para el que necesitas retroalimentación: ")

        return {
            "board_name": board_name,
            "new_ticket_description": new_ticket_description
        }

    def _retrieve_monday_data_node(self, state: AgentState) -> dict:
        """
        Nodo para el Agente de Recuperación de Datos de monday.com.
        Utiliza la herramienta LangChain `data_extractor_board_tool` para obtener tickets.
        """
        print(f"\n[Agente de Recuperación de Datos]: Buscando tickets relevantes para '{state['new_ticket_description']}' en el tablero '{state['board_name']}'...")
        try:
            extracted_data_json_str = data_extractor_board_tool.invoke({
                "board_name": state["board_name"],
                "text_search": state["new_ticket_description"]
            })
            
            
            if extracted_data_json_str.startswith("[") or extracted_data_json_str.startswith("{"):
                raw_resolved_items = json.loads(extracted_data_json_str)
            else:
                print(f"La herramienta de extracción de datos devolvió un mensaje: {extracted_data_json_str}")
                raw_resolved_items = []

            if not raw_resolved_items:
                print(f"No se encontraron tickets relevantes en el tablero '{state['board_name']}' para la búsqueda '{state['new_ticket_description']}'.")
                return {"error_message": f"No se encontraron tickets relevantes en el tablero '{state['board_name']}'.", "similar_tickets_found": []}

            # print('Data',raw_resolved_items)
            print(f"Se encontraron {len(raw_resolved_items)} tickets relevantes.")
            return {"similar_tickets_found": raw_resolved_items}
        except json.JSONDecodeError as e:
            print(f"Error al parsear la respuesta JSON de la herramienta: {e}")
            return {"error_message": f"Error al parsear datos de monday.com: {e}", "similar_tickets_found": []}
        except Exception as e:
            print(f"Error al recuperar datos de monday.com: {e}")
            return {"error_message": f"Error al recuperar datos de monday.com: {e}", "similar_tickets_found": []}

    def _distill_and_store_knowledge_csv_node(self, state: AgentState) -> dict:
        """
        Nodo que utiliza el Agente de Destilación de Conocimiento (LLM)
        para destilar información de los tickets y almacenarla en el CSV.
        """
        print(f"\n[Agente de Destilación LLM]: Destilando y almacenando conocimiento en CSV para {len(state['similar_tickets_found'])} tickets...")
        
        if not state["similar_tickets_found"]:
            print("No hay tickets para destilar. Saltando la destilación y almacenamiento en CSV.")
            return {"generated_feedback": "No se encontraron tickets para destilar. No se generó retroalimentación específica.", "similar_tickets_found": []}

        distillation_result = self.knowledge_distillation_agent.distill_and_store_knowledge( # Usar el nombre renombrado
            raw_tickets=state["similar_tickets_found"],
            board_name=state["board_name"]
        )
        
        return {
            "generated_feedback": distillation_result["report"], # El reporte del LLM agent
            "similar_tickets_found": distillation_result["distilled_tickets"] # Los tickets destilados y válidos
        }

    def _find_similar_and_generate_feedback_node(self, state: AgentState) -> dict:
        """
        Nodo que actualiza la base de conocimiento vectorial, busca tickets similares
        y luego genera la retroalimentación final para el usuario.
        """
        print(f"\n[Agente de Base de Conocimiento Vectorial y Retroalimentación]: Actualizando, buscando similitudes y generando retroalimentación para '{state['new_ticket_description']}'...")
        
        if not state["similar_tickets_found"]:
            print("No hay tickets destilados para construir/actualizar la base de conocimiento vectorial o buscar. Generando retroalimentación genérica.")
            final_feedback = "No se encontraron tickets resueltos similares en la base de conocimiento para proporcionar retroalimentación específica. Por favor, revisa la descripción o el tablero."
            return {"generated_feedback": final_feedback, "similar_tickets_found": []}

        # 1. Actualizar la base de conocimiento vectorial con los tickets destilados
        self.knowledge_base_agent.update_knowledge_base(state["similar_tickets_found"])

        # 2. Buscar tickets similares en la base de conocimiento vectorial
        found_similar_tickets = self.knowledge_base_agent.retrieve_similar_tickets(
            query_text=state["new_ticket_description"],
            k=3 # Buscar los 3 tickets más similares
        )

        # 3. Generar retroalimentación final usando el nuevo FinalFeedbackAgent
        final_feedback = self.final_feedback_agent.generate_feedback(
            new_ticket_description=state["new_ticket_description"],
            similar_tickets=found_similar_tickets
        )
        
        return {
            "similar_tickets_found": found_similar_tickets, # Actualizamos con los tickets realmente similares del vector store
            "generated_feedback": final_feedback
        }

    def _ask_user_confirmation_node(self, state: AgentState) -> dict:
        """
        Nodo para preguntar al usuario si desea crear el ticket.
        """
        print("\n--- Retroalimentación Generada ---")
        print(state["generated_feedback"])
        print("\n---------------------------------")
        
        while True:
            response = input("¿Deseas generar el ticket en monday.com con esta retroalimentación? (sí/no): ").lower()
            if response in ["si", "sí", "yes"]:
                return {"user_confirmation": True}
            elif response in ["no", "not"]:
                return {"user_confirmation": False}
            else:
                print("Respuesta no válida. Por favor, responde 'sí' o 'no'.")

    def _placeholder_create_ticket_monday(self, state: AgentState) -> dict:
        """
        Placeholder para el Agente de Creación de Tickets en monday.com.
        """
        print(f"\n[Orquestador]: Creando ticket en monday.com para '{state['new_ticket_description']}' con la retroalimentación...")
        # Simulación de creación exitosa
        return {"ticket_created_status": "Ticket creado exitosamente en monday.com."}

    # --- Lógica de Transición Condicional ---

    def _decide_on_ticket_creation(self, state: AgentState) -> str:
        """
        Función para decidir la siguiente transición basada en la confirmación del usuario.
        """
        if state.get("user_confirmation"):
            return "create_ticket"
        else:
            return "end_process"

    def run(self):
        """
        Ejecuta el grafo de LangGraph.
        """
        initial_state: AgentState = {
            "board_name": "",
            "new_ticket_description": "",
            "similar_tickets_found": [],
            "generated_feedback": "",
            "user_confirmation": False,
            "ticket_created_status": "",
            "error_message": ""
        }
        
        print("Iniciando el proceso de gestión de tickets...")
        final_state = self.app.invoke(initial_state)
        
        print("\n--- Proceso Finalizado ---")
        if final_state.get("ticket_created_status"):
            print(final_state["ticket_created_status"])
        elif final_state.get("user_confirmation") is False:
            print("El usuario decidió no crear el ticket. Proceso terminado.")
        elif final_state.get("error_message"):
            print(f"Error durante el proceso: {final_state['error_message']}")
        else:
            print("El proceso ha terminado sin una acción de creación de ticket explícita o con errores.")
        
        if final_state.get("error_message"):
            print(f"Detalles del error: {final_state['error_message']}")
