from typing import Literal
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langgraph.types import Command # type: ignore
from pydantic import BaseModel, Field # type: ignore
from langchain_core.messages import AIMessage # type: ignore # NUEVO: Importar AIMessage para el manejo de errores

from ..utils.model_provider import llm
from .search_team import SearchTeam
from .action_team import ActionTeam
from ..utils.files import File

class SupervisorGeneralResponse(BaseModel):
    """La decisión del supervisor de alto nivel."""
    next_agent: Literal["supervisor_search_agent", "supervisor_action_agent", "FINISH"] = Field(description="La decisión sobre a qué equipo enrutar la conversación o si finalizar.")

class Coordination(File):

    def __init__(self, tools) -> None:
        super().__init__(directory="prompts")
        self.team_search = SearchTeam()
        self.team_action = ActionTeam(tools=tools)
        supervisor_general_prompt_content = self.get_file_content(file_name="supervisor_general_prompt.md")

        top_level_prompt = ChatPromptTemplate.from_messages([
            ("system", supervisor_general_prompt_content),
            MessagesPlaceholder(variable_name="messages"),
        ])
        structured_llm = llm.with_structured_output(SupervisorGeneralResponse)
        self.supervisor_general_chain = top_level_prompt | structured_llm

    def supervisor_general_agent_node(self, state: MessagesState) -> Command[Literal["supervisor_search_agent", "supervisor_action_agent", END]]: # type: ignore

        if isinstance(state["messages"][-1], AIMessage):
            return Command(goto=END) # type: ignore

        response = self.supervisor_general_chain.invoke({"messages": state["messages"]})

        if response.next_agent == "FINISH": # type: ignore
            return Command(goto=END)

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
