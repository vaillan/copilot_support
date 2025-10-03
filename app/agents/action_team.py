from langchain_core.messages import AIMessage # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langchain.agents import AgentExecutor, create_tool_calling_agent # type: ignore
from langgraph.types import Command # type: ignore
from typing import Literal, List
from ..utils.model_provider import llm
from ..tools.mcp_client import CLIENT
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from langgraph.types import Command # type: ignore
from ..utils.files import File

class ActionTeam(File):
    def __init__(self, tools: List) -> None:
        super().__init__(directory="prompts")
        action_prompt_content = self.get_file_content(file_name="action_prompt.md")

        # print("\nHerramientas descubiertas automáticamente:")
        # for tool in tools: # type: ignore
        #     print(f"- Nombre: {tool.name}")
        #     print(f"  Descripción: {tool.description}\n")
        prompt = ChatPromptTemplate.from_messages([
            ("system", action_prompt_content),
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
        workflow.add_node(node="supervisor_action_agent_node", action=self.supervisor_action_agent_node)
        workflow.add_node(node="action_agent_node", action=self.action_agent_node)
        
        workflow.add_edge(start_key=START, end_key="supervisor_action_agent_node")
        # workflow.add_edge(start_key="action_agent_node", end_key="supervisor_action_agent_node")
        return workflow.compile()
