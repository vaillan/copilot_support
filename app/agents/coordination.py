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
    next_agent: Literal["supervisor_search_agent", "supervisor_action_agent", "FINISH"] = Field(description="La decisión sobre a qué equipo enrutar la conversación o si finalizar.")


class Coordination:
    
    def __init__(self, tools) -> None:
        self.team_search = SearchTeam()
        self.team_action = ActionTeam(tools=tools)

        top_level_prompt = ChatPromptTemplate.from_messages([
            ("system", """
            Eres el supervisor de un equipo de agentes. Tu trabajo es enrutar la consulta del usuario al equipo correcto basándote en el último mensaje.
            Las únicas opciones válidas para el siguiente agente son: 'supervisor_search_agent', 'supervisor_action_agent', o 'FINISH'.

            - 'supervisor_search_agent': Úsalo para preguntas, búsquedas de información, reportes o consultas sobre datos existentes.
            - 'supervisor_action_agent': Úsalo para peticiones explícitas de crear, modificar o actualizar algo (ej. "crea una tarea", "cambia el estado").
            - 'FINISH': Úsalo si la conversación parece haber terminado o si el usuario se está despidiendo.

            Responde únicamente con el objeto JSON que se ajuste al esquema 'SupervisorGeneralResponse' y nada más. No incluyas explicaciones ni texto adicional.
            """),
            MessagesPlaceholder(variable_name="messages"),
        ])
        structured_llm = llm.with_structured_output(SupervisorGeneralResponse)
        self.supervisor_general_chain = top_level_prompt | structured_llm

    def supervisor_general_agent_node(self, state: MessagesState) -> Command[Literal["supervisor_search_agent", "supervisor_action_agent", END]]: # type: ignore

        if isinstance(state["messages"][len(state["messages"]) - 1], AIMessage):
            return Command(goto=END) # type: ignore

        response = self.supervisor_general_chain.invoke({"messages": state["messages"]})

        if response.next_agent == "FINISH": # type: ignore
            return Command(goto=END)

        # Usamos getattr para acceder al atributo de forma segura, aunque con Pydantic no es estrictamente necesario aquí.
        return Command(goto=response.next_agent) # type: ignore
    
    @property
    def supervisor_general_graph(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node(node="supervisor_agents_node", action=self.supervisor_general_agent_node)
        workflow.add_node(node="supervisor_search_agent", action=self.team_search.supervisor_search_graph)
        workflow.add_node(node="supervisor_action_agent", action=self.team_action.supervisor_action_graph)

        workflow.add_edge(start_key=START, end_key="supervisor_agents_node")
        workflow.add_edge(start_key="supervisor_search_agent", end_key="supervisor_agents_node")
        workflow.add_edge(start_key="supervisor_action_agent", end_key="supervisor_agents_node")

        return workflow.compile()
