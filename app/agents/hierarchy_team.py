from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
# from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.agents.make_supervisor_node import make_supervisor_node
from app.utils.state import BaseState
from app.settings.settings import Settings
from app.agents.research_team import ResearchTeam
from app.agents.document_writer_team import DocumentWriterTeam

settings = Settings()

class HierarchyTeam:

    def __init__(self, tools: list) -> None:
        research_executor = ResearchTeam(tools=tools)
        document_writer_executor = DocumentWriterTeam()
        self.research_agent = research_executor.research_graph
        self.document_writer_agent = document_writer_executor.document_writer_graph
        
        self.llm_gemini_flash = ChatGoogleGenerativeAI(
            model="models/gemini-flash-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.5,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        # self.llm_gemini_flash_lite = ChatOpenAI(
        #     model_name="models/gemini-flash-latest", # type: ignore
        #     base_url="https://generativelanguage.googleapis.com/v1beta",
        #     api_key=settings.GEMINI_API_KEY,
        #     temperature=0.8,
        #     top_p=0.9,
        #     max_retries=30,
        #     timeout=15,
        # )
    
    async def call_research_team(self, state: BaseState) -> Command[Literal["supervisor"]]:
        response = await self.research_agent.ainvoke({"messages": state["messages"][-1]}) # type: ignore
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=response["messages"][-1].content, name="research_team"
                    )
                ]
            },
            goto="supervisor",
        )
    
    async def call_paper_writing_team(self, state: BaseState) -> Command[Literal["supervisor"]]:
        response = await self.document_writer_agent.ainvoke({"messages": state["messages"]}) # type: ignore
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=response["messages"][-1].content, name="doc_writing_team"
                    )
                ]
            },
            goto="supervisor",
        )
    
    @property
    def hierarchy_graph(self):
        teams_supervisor_node = make_supervisor_node(self.llm_gemini_flash, ["research_team", "doc_writing_team"])
        hierarchy_team_builder = StateGraph(BaseState)
        hierarchy_team_builder.add_node(node="supervisor", action=teams_supervisor_node) # type: ignore
        hierarchy_team_builder.add_node(node="research_team", action=self.call_research_team)
        hierarchy_team_builder.add_node(node="doc_writing_team", action=self.call_paper_writing_team)

        hierarchy_team_builder.add_edge(start_key=START, end_key="supervisor")

        graph = hierarchy_team_builder.compile()
        return graph