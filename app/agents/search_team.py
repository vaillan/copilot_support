from langchain_core.messages import AIMessage # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langchain.agents import AgentExecutor, create_tool_calling_agent # type: ignore
from langgraph.types import Command # type: ignore
from typing import Literal
from pydantic import BaseModel, Field # type: ignore
from ..utils.state import GraphState
from ..tools.list_boards_tool import list_boards
from ..tools.similarity_search_tool import similarity_search
from ..utils.model_provider import llm
import json
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from ..utils.state import GraphState

class SupervisorSearchResponse(BaseModel):
    next_agent: str = Field(description="El nombre del agente a llamar a continuación. Debe ser uno de: ['search_agent_node', 'report_agent_node', 'FINISH']")


class SearchTeam:

    def __init__(self):
        self.structured_llm = llm.with_structured_output(SupervisorSearchResponse) # type: ignore
        search_tools = [list_boards, similarity_search]
        search_prompt = ChatPromptTemplate.from_messages([
                ("system", """
                Eres un especialista en analisis de datos. Tu comunicación con el usuario debe ser clara, directa y enfocada en cumplir tu objetivo.

                **2. OBJETIVO PRINCIPAL**
                Tu única función es ayudar al usuario a encontrar información relevante utilizando la herramienta `similarity_search`. Todas las demás acciones son pasos intermedios para conseguir los parámetros necesarios para esta herramienta.

                **3. HERRAMIENTAS DISPONIBLES**
                *   `similarity_search(board_name: str, query: str)`: Busca elementos similares a la `query` dentro del tablero especificado en `board_name`.
                *   `list_boards()`: Devuelve una lista de todos los nombres de tableros disponibles.

                **4. REGLAS CRÍTICAS (Inquebrantables)**
                *   **PRECISIÓN ABSOLUTA:** NUNCA infieras, adivines, resumas o modifiques los valores que el usuario proporciona. Utiliza los términos de búsqueda (`query`) y los nombres de tablero (`board_name`) **EXACTAMENTE** como son escritos por el usuario. La distinción entre mayúsculas y minúsculas es importante.
                *   **PROHIBIDO INVENTAR:** Si no tienes un parámetro, no intentes adivinarlo. Tu única vía para obtener información faltante es usar las herramientas disponibles o preguntar al usuario.

                **5. PROCESO LÓGICO DE ACTUACIÓN (Paso a Paso)**

                **Paso A: Análisis de la Petición Inicial**
                Evalúa la petición del usuario para identificar si ha proporcionado los dos parámetros obligatorios para tu objetivo final: `board_name` y `query`.

                **Paso B: Flujo de Ejecución**
                Sigue uno de los siguientes dos escenarios, sin excepción:

                *   **ESCENARIO 1: El usuario proporciona toda la información.**
                    *   **Condición:** La petición del usuario contiene tanto un `board_name` como una `query`.
                    *   **Ejemplo de Petición:** "Busca en el tablero 'Historico Soporte - Desarrollo' un error similar a 'error al crear orden de cambio'"
                    *   **Tu Acción INMEDIATA Y ÚNICA:** Llama a la herramienta `similarity_search` con los valores exactos.
                        *   `similarity_search(board_name='Historico Soporte - Desarrollo', query='error al crear orden de cambio')`

                *   **ESCENARIO 2: Al usuario le falta especificar el `board_name`.**
                    *   **Condición:** La petición del usuario contiene una `query` pero no un `board_name`.
                    *   **Ejemplo de Petición:** "Busca un error similar a 'error al crear orden de cambio'"
                    *   **Tu SECUENCIA DE ACCIONES:**
                        1.  **PRIMERA ACCIÓN:** Llama a la herramienta `list_boards()` para obtener las opciones disponibles. No hagas nada más.
                        2.  **SEGUNDA ACCIÓN:** Una vez que `list_boards()` te devuelva la lista, preséntala al usuario de forma clara y concisa. Formula una pregunta directa.
                            *   *Ejemplo de respuesta al usuario:* "Entendido. ¿En cuál de los siguientes tableros deseas buscar 'error al crear orden de cambio'? [Lista de tableros de la herramienta]"
                        3.  **TERCERA ACCIÓN:** Cuando el usuario responda con un nombre de tablero, ejecuta `similarity_search` utilizando la `query` original y el `board_name` **exacto** que el usuario seleccionó.
                            *   *Si el usuario responde:* "En Historico Soporte - Desarrollo"
                            *   *Tu acción final será:* `similarity_search(board_name='Historico Soporte - Desarrollo', query='error al crear orden de cambio')`
                """),
                MessagesPlaceholder(variable_name="messages"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
        
        self.report_prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un asistente de productividad experto en analizar y resumir información. Tu objetivo es transformar los datos en un resumen claro y accionable. Usa formato Markdown. Si un campo no existe en el JSON, omítelo."),
            ("human", "Resume el siguiente ítem de monday.com, extrayendo la información más crítica. Datos del Ítem (JSON): {item_data}. Sigue esta estructura flexible: ### 📌 {item_name} (ID: {item_id})\n- **Tablero**: {board_name}\n- **Información Clave**: [Extrae dinámicamente 2-4 campos importantes como Estatus, Prioridad, etc.]\n\n#### Resumen Principal:\n[Describe el propósito central del ítem.]\n\n#### Última Actividad Relevante:\n[Describe la actualización más reciente.]\n\n#### Análisis y Próximos Pasos:\n[Ofrece un breve análisis y sugiere el siguiente paso lógico.]")
        ])
        self.supervisor_search_prompt = ChatPromptTemplate.from_messages([
            ("system", 
            """
            Eres el supervisor de un equipo de agentes. Tu trabajo es enrutar la consulta al agente más adecuado o finalizar la conversación.
            **Agentes disponibles para tu decisión de enrutamiento:**
            *   **search_agent_node**: Enruta aquí si la consulta del usuario requiere buscar información, listar tableros o realizar una búsqueda de similitud. Este es el agente principal para la recuperación de datos.
            *   **report_agent_node**: Enruta aquí *únicamente* si la intención del usuario es generar un reporte o resumen a partir de **resultados de búsqueda que ya han sido obtenidos y están presentes en el estado de la conversación**. No elijas este agente si no hay resultados de búsqueda previos para procesar.
            *   **FINISH**: Responde 'FINISH' si la conversación ha terminado, la consulta del usuario ha sido completamente atendida, o no hay más acciones pendientes para satisfacer la solicitud.

            **Consideraciones importantes:**
            *   Tu objetivo es guiar la conversación hacia la resolución de la consulta del usuario.
            *   Prioriza el `search_agent_node` si la intención del usuario es obtener o explorar nueva información.
            *   Si la conversación parece haber llegado a una conclusión natural o la pregunta ha sido respondida, finaliza.
            """), 
            MessagesPlaceholder(variable_name="messages")
        ])
        search_agent_runnable = create_tool_calling_agent(llm, search_tools, search_prompt)
        self.search_agent_executor = AgentExecutor(agent=search_agent_runnable, tools=search_tools, verbose=True)

    def search_agent_node(self, state: GraphState) -> Command[Literal["supervisor_search_agent_node"]]:
        # print("--- Ejecutando Nodo: Agente de Búsqueda ---")
        result_data = None
        result = self.search_agent_executor.invoke({"messages": state["messages"]})
        tool_outputs = result.get("tool_outputs")
        if tool_outputs and isinstance(tool_outputs[0], list) and len(tool_outputs[0]) > 0:
            result_data = {"search_results": tool_outputs[0], "messages": [AIMessage(content=f"He encontrado {len(tool_outputs[0])} ítem(s) relevante(s). Generando reporte...")]}
        else:
            result_data = {"messages": [AIMessage(content=result["output"])]}
        # return {"messages": [AIMessage(content=result["output"])]}
        return  Command(goto="supervisor_search_agent_node", update=result_data)

    def report_agent_node(self, state: GraphState) -> Command[Literal["supervisor_search_agent_node"]]:
        # print("--- Ejecutando Nodo: Generación de Reportes ---")
        final_report = f"Basado en tu consulta: He encontrado la siguiente información relevante:\n\n"
        for item in state['search_results']:
            report_chain = self.report_prompt | llm
            item_summary = report_chain.invoke({"item_data": json.dumps(item, indent=2, ensure_ascii=False), "item_name": item.get('item_name', 'N/A'), "item_id": item.get('item_id', 'N/A'), "board_name": item.get('board_name', 'N/A')})
            final_report += item_summary.content + "\n\n---\n\n" # type: ignore
        return Command(goto="supervisor_search_agent_node", update={"messages": [AIMessage(content=final_report)]})

    def supervisor_search_agent_node(self, state: GraphState) -> Command[Literal["search_agent_node", "report_agent_node", END]]: # type: ignore
        # print("--- Ejecutando Nodo: Orquestador ---")
        if 'search_results' in state and state["search_results"]:
            return Command(goto="report_agent_node")

        if isinstance(state["messages"][-1], AIMessage):
            return Command(goto=END) # type: ignore

        chain = self.supervisor_search_prompt | self.structured_llm
        response = chain.invoke({"messages": state["messages"]})
        return Command(goto=response.next_agent)

    @property
    def supervisor_search_graph(self):
        workflow = StateGraph(GraphState)
        workflow.add_node("supervisor_search_agent_node", self.supervisor_search_agent_node)
        workflow.add_node("search_agent_node", self.search_agent_node)
        workflow.add_node("report_agent_node", self.report_agent_node)
        workflow.add_edge("search_agent_node", "supervisor_search_agent_node")
        workflow.add_edge("report_agent_node", "supervisor_search_agent_node")
        workflow.add_edge(START, "supervisor_search_agent_node")
        return workflow.compile()