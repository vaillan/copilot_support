from typing import Literal
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langgraph.types import Command # type: ignore
from pydantic import BaseModel, Field # type: ignore
from langchain_core.messages import AIMessage # type: ignore # NUEVO: Importar AIMessage para el manejo de errores

from ..utils.model_provider import llm
from .search_team import SearchTeam
from .action_team import ActionTeam

class SupervisorGeneralResponse(BaseModel):
    """La decisión del supervisor de alto nivel."""
    next_agent: Literal["SupervisorSearchAgentNode", "SupervisorActionAgentNode", "FINISH"] = Field(description="La decisión sobre a qué equipo enrutar la conversación o si finalizar.")


class Coordination:
    
    def __init__(self, tools) -> None:
        self.team_search = SearchTeam()
        self.team_action = ActionTeam(tools=tools)
    
        structured_llm = llm.with_structured_output(SupervisorGeneralResponse)
        
        # NUEVO: Prompt mejorado para forzar la salida JSON
        top_level_prompt = ChatPromptTemplate.from_messages([
            ("system", """
            Eres el supervisor de un equipo de agentes. Tu trabajo es enrutar la consulta del usuario al equipo correcto basándote en el último mensaje.
            - 'SupervisorSearchAgentNode': Úsalo para preguntas, búsquedas de información, reportes o consultas sobre datos existentes.
            - 'SupervisorActionAgentNode': Úsalo para peticiones explícitas de crear, modificar o actualizar algo (ej. "crea una tarea", "cambia el estado").
            - 'FINISH': Úsalo si la conversación parece haber terminado o si el usuario se está despidiendo.

            Responde únicamente con el objeto JSON que se ajuste al esquema 'SupervisorGeneralResponse' y nada más. No incluyas explicaciones ni texto adicional.
            """),
            MessagesPlaceholder(variable_name="messages"),
        ])
        self.supervisor_general_chain = top_level_prompt | structured_llm

    def supervisor_general_agent_node(self, state: MessagesState) -> Command[Literal["SupervisorSearchAgentNode", "SupervisorActionAgentNode", END]]: # type: ignore
        response = self.supervisor_general_chain.invoke({"messages": state["messages"]})
        
        # NUEVO: Manejo de errores por si la respuesta sigue siendo None
        if response is None:
            print("ADVERTENCIA: El supervisor principal no pudo tomar una decisión. Finalizando el turno para evitar un bucle.")
            # Añadimos un mensaje de error al estado para que sea visible
            error_message = AIMessage(content="Lo siento, he tenido un problema interno y no he podido decidir cómo proceder. Por favor, intenta reformular tu pregunta.")
            state["messages"].append(error_message)
            return Command(goto=END)

        print(f"--- Decisión del Supervisor Principal: Enrutar a {response.next_agent} ---")
        if response.next_agent == "FINISH":
            return Command(goto=END)
        
        # Usamos getattr para acceder al atributo de forma segura, aunque con Pydantic no es estrictamente necesario aquí.
        return Command(goto=response.next_agent)
    
    @property
    def supervisor_general_graph(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node("SupervisorGeneralAgentNode", self.supervisor_general_agent_node)
        workflow.add_node("SupervisorSearchAgentNode", self.team_search.supervisor_search_graph)
        workflow.add_node("SupervisorActionAgentNode", self.team_action.supervisor_action_graph)

        workflow.add_edge(START, "SupervisorGeneralAgentNode")
        workflow.add_edge("SupervisorSearchAgentNode", "SupervisorGeneralAgentNode")
        workflow.add_edge("SupervisorActionAgentNode", "SupervisorGeneralAgentNode")

        return workflow.compile()
