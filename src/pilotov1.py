from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage
import operator
from langchain_core.tools import tool
from settings.settings import Settings
from pydantic import BaseModel, Field
from utils.extract_monday_data import ExtractData
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langgraph.graph import StateGraph, END
import json

settings = Settings()
extractData = ExtractData()

# DEFINICIÓN DEL ESTADO
class GraphState(TypedDict):
    """
    Representa el estado de nuestro grafo de agentes.

    Atributos:
        user_query: La consulta inicial y sin modificar del usuario.
        messages: La lista de mensajes que componen la conversación.
        next_agent: El nombre del siguiente agente que el orquestador ha decidido ejecutar.
        search_results: Los resultados de la búsqueda por similitud.
    """
    user_query: str
    messages: Annotated[List[BaseMessage], operator.add]
    next_agent: str
    search_results: List[dict]

class QueryItemPageInput(BaseModel):
    board_name: str = Field(description="Nombre del tablero")
    query: str = Field(description="Texto a buscar")

# Configuración del LLM
llm = ChatGoogleGenerativeAI(
        model= "gemini-2.5-flash-lite",
        temperature=0,
        max_retries=2,
        google_api_key=settings.GEMINI_API_KEY,
    )

# Herramientas
@tool
def list_boards():
    """
    Llama a esta herramienta para obtener una lista de todos los nombres de los tableros de monday.com disponibles.
    Es útil cuando el usuario necesita saber qué tableros existen antes de realizar una búsqueda.
    """
    print("--- Llamando a la herramienta: list_monday_boards ---")
    boards = extractData._extract_all_boards()
    return [board['name'] for board in boards]

@tool
def similarity_search(board_name: str, query: str):
    """Utiliza esta herramienta para buscar ítems por similitud DENTRO de un tablero específico."""
    initial_gql_query = """
        query($board_id: [ID!], $text_search: CompareValue!) {
            boards(ids:$board_id) {
                name
                state
                permissions
                items_page(limit: 10, query_params: {rules: [
                            {column_id: "name", compare_value: $text_search, operator:contains_text}
                        ]
                }) {
                    cursor
                    items {
                        id
                        name
                        column_values {
                            id
                            value
                            text
                            column {
                                id
                                title
                                archived
                            }
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                value
                                text
                                column {
                                    id
                                    title
                                    archived
                                }
                            }
                            updates {
                                body
                                id
                                created_at
                                creator {
                                    name
                                    id
                                }
                            }
                        }
                        updates {
                            body
                            id
                            created_at
                            creator {
                                name
                                id
                            }
                        }
                    }
                }
                views {
                    id
                    type
                    name
                }      
            }
        }
    """
    
    next_page_gql_query = """
        query($board_id: [ID!], $cursor: String!) {
            boards(ids:$board_id) {
                items_page(limit: 50, cursor: $cursor) {
                    cursor
                    items {
                        id
                        name
                        column_values {
                            id
                            value
                            text
                            column {
                                id
                                title
                                archived
                            }
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                value
                                text
                                column {
                                    id
                                    title
                                    archived
                                }
                            }
                            updates {
                                body
                                id
                                created_at
                                creator {
                                    name
                                    id
                                }
                            }
                        }
                        updates {
                            body
                            id
                            created_at
                            creator {
                                name
                                id
                            }
                        }
                    }
                }
            }
        }
    """

    all_boards = extractData._extract_all_boards()
    boarsd = extractData._get_board_id(boards=all_boards, board_name=board_name)
    print('search_similar_items_in_board: ', f"Board: {board_name}", f"Query: {query}")
    # boarsd = next((b for b in all_boards if b['name'].lower() == board_name.lower()), None)
    if not boarsd:
        board_names = ", ".join([f"'{b['name']}'" for b in all_boards])
        return f"Error: No se encontraron tableros similares a '{board_name}'. Los tableros disponibles son: {board_names}."

    data = extractData.pre_processor_cleaner_data(datos=extractData._process_board_items(
            board_ids=boarsd,
            text_search=query,
            initial_gql_query=initial_gql_query,
            next_page_gql_query=next_page_gql_query
        ))
    return data

search_tools = [list_boards, similarity_search]

search_prompt = ChatPromptTemplate.from_messages([
        ("system", """
        Eres un especialista en analisis de datos.
        Tu objetivo final es usar la herramienta 'similarity_search'.

        **Asegurate especificamente de llamar a una herramienta, DEBES usar los valores que el usuario ha proporcionado EXPLÍCITAMENTE en la conversación. NO infieras, NO adivines y NO cambies los valores que el usuario ingresa o los términos de búsqueda. Usa los valores EXACTAMENTE como los escribió el usuario.**

        Sigue este proceso lógico paso por paso:
        1.  Para usar 'similarity_search', necesitas los parámetros {{board_name}} y {{query}}.
        2.  Revisa el historial de la conversación. Si el parámetro {{board_name}} NO ha sido especificado por el usuario, tu PRIMERA ACCIÓN debe ser llamar a la herramienta 'list_boards' para obtener las opciones.
        3.  Una vez que tengas la lista de tableros, preséntasela al usuario y pregúntale en cuál de ellos desea buscar.
        4.  Cuando el usuario finalmente te proporcione un nombre de tablero, llama a la herramienta 'similarity_search' usando la consulta original y el **nombre exacto del tablero que el usuario seleccionó**.
        """),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
search_agent_runnable = create_tool_calling_agent(llm, search_tools, search_prompt)
search_agent_executor = AgentExecutor(agent=search_agent_runnable, tools=search_tools, verbose=True)

# NODOS

def search_agent_node(state: GraphState):
    print("--- Ejecutando Nodo: Agente de Búsqueda ---")
    result = search_agent_executor.invoke({"messages": state["messages"]})
    tool_outputs = result.get("tool_outputs")

    if tool_outputs and isinstance(tool_outputs[0], list) and len(tool_outputs[0]) > 0:
        return {"search_results": tool_outputs[0], "messages": [AIMessage(content=f"He encontrado {len(tool_outputs[0])} ítem(s) relevante(s). Generando reporte...")]}

    return {"messages": [AIMessage(content=result["output"])]}

def report_agent_node(state: GraphState):
    print("--- Ejecutando Nodo: Generación de Reportes ---")
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "Eres un asistente de productividad experto en analizar y resumir información de monday.com. Tu objetivo es transformar los datos de un ítem en un resumen claro y accionable. Usa formato Markdown. Si un campo no existe en el JSON, omítelo."),
        ("human", "Resume el siguiente ítem de monday.com, extrayendo la información más crítica. Datos del Ítem (JSON): {item_data}. Sigue esta estructura flexible: ### 📌 {item_name} (ID: {item_id})\n- **Tablero**: {board_name}\n- **Información Clave**: [Extrae dinámicamente 2-4 campos importantes como Estatus, Prioridad, etc.]\n\n#### Resumen Principal:\n[Describe el propósito central del ítem.]\n\n#### Última Actividad Relevante:\n[Describe la actualización más reciente.]\n\n#### Análisis y Próximos Pasos:\n[Ofrece un breve análisis y sugiere el siguiente paso lógico.]")
    ])
    final_report = f"Basado en tu consulta: '{state['user_query']}', he encontrado la siguiente información relevante:\n\n"
    for item in state['search_results']:
        report_chain = prompt_template | llm
        item_summary = report_chain.invoke({"item_data": json.dumps(item, indent=2, ensure_ascii=False), "item_name": item.get('item_name', 'N/A'), "item_id": item.get('item_id', 'N/A'), "board_name": item.get('board_name', 'N/A')})
        final_report += item_summary.content + "\n\n---\n\n" # type: ignore
    return {"messages": [AIMessage(content=final_report)]}

# ORQUESTADOR Y GRAFO
from langchain_core.pydantic_v1 import BaseModel, Field

class SupervisorResponse(BaseModel):
    next_agent: str = Field(description="El nombre del agente a llamar a continuación. Debe ser uno de: ['SearchAgent', 'ReportAgent', 'FINISH']")

structured_llm = llm.with_structured_output(SupervisorResponse) # type: ignore

def supervisor_agent_node(state: GraphState):
    print("--- Ejecutando Nodo: Orquestador ---")
    if state["search_results"]:
        print("    > Decisión: Hay resultados de búsqueda, pasando a generar el reporte.")
        return {"next_agent": "ReportAgent"}
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "Eres el supervisor de un equipo de agentes. Tu trabajo es enrutar la consulta al agente correcto o finalizar. Agentes disponibles: SearchAgent (para buscar info), ReportAgent (se activa solo). Si la conversación parece terminada, responde 'FINISH'."), 
        MessagesPlaceholder(variable_name="messages")
        ])
    chain = prompt | structured_llm
    response = chain.invoke({"messages": state["messages"]})
    # print(f"    > Decisión del LLM: {response.next_agent}") # type: ignore
    return {"next_agent": response.next_agent} # type: ignore

def router(state: GraphState):
    return state["next_agent"]

workflow = StateGraph(GraphState)
workflow.add_node("Supervisor", supervisor_agent_node)
workflow.add_node("SearchAgent", search_agent_node)
workflow.add_node("ReportAgent", report_agent_node) # No necesitamos el ActionAgent para este ejemplo
workflow.set_entry_point("Supervisor")
workflow.add_conditional_edges("Supervisor", router, {"SearchAgent": "SearchAgent", "ReportAgent": "ReportAgent", "FINISH": END})
workflow.add_edge("SearchAgent", "Supervisor")
workflow.add_edge("ReportAgent", END)
app = workflow.compile()

# --- NUEVO BLOQUE PARA GENERAR LA IMAGEN DEL GRAFO ---
print("\n--- Compilando la imagen del grafo ---")
try:
    # Obtiene el grafo en un formato dibujable
    graph = app.get_graph()
    
    # Dibuja el grafo y lo guarda como un archivo PNG
    # Puedes cambiar el nombre del archivo si lo deseas
    graph.draw_mermaid_png(output_file_path="flujo_del_agente.png")
    
    print("✅ ¡Imagen del grafo guardada en 'flujo_del_agente.png'!")

except ImportError as e:
    print(f"❌ Error al generar la imagen: {e}")
    print("Asegúrate de haber instalado Graphviz en tu sistema y la librería 'pygraphviz' de Python.")
    print("Consulta las instrucciones de instalación para tu sistema operativo.")
except Exception as e:
    print(f"❌ Ocurrió un error inesperado al generar la imagen: {e}")

# --- EJECUCIÓN DEL CASO DE USO ---

# EJECUCIÓN DEL FLUJO CONVERSACIONAL ---

# Guardaremos el historial de la conversación para mantener el contexto
# conversation_history = []

# # --- PASO A: La consulta inicial del usuario ---
# user_query = "error al crear facturas"
# print(f"==================================================")
# print(f"INICIO DE LA CONVERSACIÓN")
# print(f"Usuario: {user_query}")
# print(f"==================================================")

# # Añadimos el primer mensaje al historial
# conversation_history.append(HumanMessage(content=user_query))

# Creamos el estado inicial para el grafo
# initial_state = {
#     "messages": conversation_history,
#     "user_query": user_query,
#     "search_results": []
# }

# --- PASO B: Ejecutar el primer tramo del flujo ---
# El agente debería llamar a `list_monday_boards` y luego preguntar al usuario.
# final_response = None
# for event in app.stream(initial_state, {"recursion_limit": 15}): # type: ignore
#     for key, value in event.items():
#         print(f"\n--- Salida del Nodo: {key} ---")
#         print(value)
#         if 'messages' in value:
#             # Guardamos la última respuesta del asistente
#             final_response = value['messages'][-1]

# # Añadimos la respuesta del asistente al historial
# if final_response:
#     conversation_history.append(final_response)

# print(f"\n==================================================")
# print(f"ASISTENTE PIDE MÁS INFORMACIÓN")
# print(f"Asistente: {final_response.content if final_response else 'No hubo respuesta'}")
# print(f"==================================================")


# # --- PASO C: La respuesta del usuario ---
# user_board_selection = "En el tablero Historico Soporte - Desarrollo"
# print(f"\n==================================================")
# print(f"CONTINUACIÓN DE LA CONVERSACIÓN")
# print(f"Usuario: {user_board_selection}")
# print(f"==================================================")

# # Añadimos la respuesta del usuario al historial
# conversation_history.append(HumanMessage(content=user_board_selection))

# # Creamos el nuevo estado con el historial actualizado
# continuation_state = {
#     "messages": conversation_history,
#     "user_query": user_query, # La consulta original no cambia
#     "search_results": []
# }

# # --- PASO D: Continuar la conversación ---
# # Ahora el agente tiene toda la información y debería llamar a `search_similar_items_in_board`
# # y luego el `ReportAgent` debería generar el resumen final.
# final_report = None
# for event in app.stream(continuation_state, {"recursion_limit": 15}): # type: ignore
#     for key, value in event.items():
#         print(f"\n--- Salida del Nodo: {key} ---")
#         print(value)
#         if key == "ReportAgent" and 'messages' in value:
#             final_report = value['messages'][-1]

# print(f"\n==================================================")
# print(f"REPORTE FINAL GENERADO")
# print(f"Asistente: {final_report.content if final_report else 'No se generó el reporte final.'}")
# print(f"==================================================")