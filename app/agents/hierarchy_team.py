from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage

from ..agents.make_supervisor_node import make_supervisor_node
from ..utils.state import DocumentWritingState, HierarchyTeamState, ResearchState # type: ignore

from ..tools.doc_tools import *
from ..settings.settings import Settings
from .research_team import ResearchTeam
from .document_writer_team import DocumentWriterTeam

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
    
    async def call_research_team(self, state: ResearchState) -> Command[Literal["supervisor"]]:
        response = await self.research_agent.ainvoke({"messages": state["messages"][-1]}) # type: ignore
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content=response["messages"][-1].content, name="research_team"
                    )
                ]
            },
            goto="supervisor",
        )
    
    async def call_paper_writing_team(self, state: DocumentWritingState) -> Command[Literal["supervisor"]]:
        response = await self.document_writer_agent.ainvoke({"messages": state["messages"][-1]}) # type: ignore
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content=response["messages"][-1].content, name="writing_team"
                    )
                ]
            },
            goto="supervisor",
        )
    
    @property
    def hierarchy_graph(self):
        teams_supervisor_node = make_supervisor_node(self.llm_gemini_flash, ["research_team", "writing_team"])
        hierarchy_team_builder = StateGraph(HierarchyTeamState)
        hierarchy_team_builder.add_node("supervisor", teams_supervisor_node) # type: ignore
        hierarchy_team_builder.add_node("research_team", self.call_research_team)
        hierarchy_team_builder.add_node("writing_team", self.call_paper_writing_team)

        hierarchy_team_builder.add_edge(START, "supervisor")
        graph = hierarchy_team_builder.compile()
        return graph