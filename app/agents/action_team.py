from langchain_core.messages import AIMessage # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langchain.agents import AgentExecutor, create_tool_calling_agent # type: ignore
from langgraph.types import Command # type: ignore
from typing import Literal, List
from ..utils.model_provider import llm
from ..tools.mcp_client import CLIENT
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from langgraph.types import Command # type: ignore

class ActionTeam:
    def __init__(self, tools: List) -> None:

        # print("\nHerramientas descubiertas automáticamente:")
        # for tool in tools: # type: ignore
        #     print(f"- Nombre: {tool.name}")
        #     print(f"  Descripción: {tool.description}\n")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Eres un agente que ejecuta acciones..."),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        action_agent = create_tool_calling_agent(llm, tools, prompt)
        
        self.action_agent_executor = AgentExecutor(
                agent=action_agent,
                tools=tools,
                verbose=True
            )

    def action_agent_node(self, state: MessagesState) -> Command[Literal["supervisor_action_agent_node"]]:
        result = self.action_agent_executor.invoke({"messages": state["messages"]})
        return Command(goto="supervisor_action_agent_node", update={"messages": [AIMessage(content=result['output'])]})

    def supervisor_action_agent_node(self, state: MessagesState) -> Command[Literal["action_agent_node", END]]: # type: ignore
        if isinstance(state["messages"][-1], AIMessage):
            return Command(goto=END)
        return Command(goto="action_agent_node")
    
    @property
    def supervisor_action_graph(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node("supervisor_action_agent_node", self.supervisor_action_agent_node)
        workflow.add_node("action_agent_node", self.action_agent_node)
        
        workflow.add_edge("action_agent_node", "supervisor_action_agent_node")
        workflow.add_edge(START, "supervisor_action_agent_node")
        return workflow.compile()
