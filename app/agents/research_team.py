from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage # type: ignore

from app.utils.files import File
from app.settings.settings import Settings
from app.agents.make_supervisor_node import make_supervisor_node
from app.utils.monday_client import fetch_all_items_by_board_id, fetch_columns_by_board_id, fetch_item_by_board_id_by_update_date, fetch_items_by_column_value, find_boards_like_name
from app.utils.state import ResearchState

settings = Settings()

class ResearchTeam(File):
    def __init__(self, tools: list):
        super().__init__(directory="prompts")
        search_prompt_content = self.get_file_content(file_name="search_prompt.md")
        report_prompt_content = self.get_file_content(file_name="report_prompt.md")

        search_tools = [
            fetch_all_items_by_board_id,
            fetch_columns_by_board_id,
            fetch_item_by_board_id_by_update_date,
            fetch_items_by_column_value,
            find_boards_like_name,
        ]

        search_mcp_tools = [
            "get_board_items_by_name",
            "get_board_schema",
            "get_board_activity",
            "get_board_info",
            "get_users_by_name",
            "list_users_and_teams",
            "get_form",
            "get_column_type_info",
            "fetch_custom_activity",
            "read_docs",
            "workspace_info",
            "list_workspaces",
            "all_widgets_schema"
        ]

        for tool in tools:
            if tool.name in search_mcp_tools:
                search_tools.append(tool)

        self.llm_gemini_flash_lite = ChatGoogleGenerativeAI(
            model="models/gemini-flash-lite-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.5,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        # self.llm_gemini_flash_lite = ChatOpenAI(
        #     model_name="models/gemini-flash-lite-latest", # type: ignore
        #     base_url="https://generativelanguage.googleapis.com/v1beta",
        #     api_key=settings.GEMINI_API_KEY,
        #     temperature=1.0,
        #     top_p=0.9,
        #     max_retries=30,
        #     timeout=60,
        # )
        self.llm_gemini_flash = ChatGoogleGenerativeAI(
            model="models/gemini-flash-lite-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.9,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        # self.llm_gemini_flash = ChatOpenAI(
        #     model_name="models/gemini-flash-latest", # type: ignore
        #     base_url="https://generativelanguage.googleapis.com/v1beta",
        #     api_key=settings.GEMINI_API_KEY,
        #     temperature=0.8,
        #     top_p=0.9,
        #     max_retries=30,
        #     timeout=60,
        # )

        self.search_agent = create_react_agent(model=self.llm_gemini_flash, tools=search_tools, prompt=search_prompt_content)
        self.report_agent = create_react_agent(model=self.llm_gemini_flash_lite, tools=[], prompt=report_prompt_content)

    async def search_node(self, state: ResearchState) -> Command[Literal["supervisor_research_team"]]:
        result = await self.search_agent.ainvoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="search")
                ]
            },
            goto="supervisor_research_team",
        )

    async def report_node(self, state: ResearchState) -> Command[Literal["supervisor_research_team"]]:
        result = await self.report_agent.ainvoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="report")
                ]
            },
            goto="supervisor_research_team",
        )

    @property
    def research_graph(self):
        research_supervisor_node = make_supervisor_node(llm=self.llm_gemini_flash, members=["search", "report"])

        research_builder = StateGraph(ResearchState)
        research_builder.add_node(node="supervisor_research_team", action=research_supervisor_node) # type: ignore
        research_builder.add_node(node="search", action=self.search_node)
        research_builder.add_node(node="report", action=self.report_node)

        research_builder.add_edge(start_key=START, end_key="supervisor_research_team")

        graph = research_builder.compile()
        return graph