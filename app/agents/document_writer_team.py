from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage

from ..agents.make_supervisor_node import make_supervisor_node
from ..utils.state import DocumentWritingState

from ..utils.files import File
from ..tools.doc_tools import *
from ..settings.settings import Settings

settings = Settings()

class DocumentWriterTeam(File):
    def __init__(self):
        self.llm_gemini_flash_lite = ChatGoogleGenerativeAI(
            model="models/gemini-flash-lite-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.8,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        # self.llm_gemini_flash_lite = ChatOpenAI(
        #     model_name="models/gemini-flash-lite-latest", # type: ignore
        #     base_url="https://generativelanguage.googleapis.com/v1beta",
        #     api_key=settings.GEMINI_API_KEY,
        #     temperature=0.8,
        #     top_p=0.9,
        #     max_retries=30,
        #     timeout=15,
        # )
        
        self.chart_generating_agent = create_react_agent(
            self.llm_gemini_flash_lite, tools=[read_document, python_repl_tool]
        )

        self.note_taking_agent = create_react_agent(
            self.llm_gemini_flash_lite,
            tools=[create_outline, read_document],
            prompt=(
                "Puedes leer documentos y crear esquemas para el redactor de documentos. "
                "No hagas preguntas de seguimiento."
            ),
        )

        self.doc_writer_agent = create_react_agent(
            self.llm_gemini_flash_lite,
            tools=[write_document, edit_document, read_document],
            prompt=(
                "Puedes leer, escribir y editar documentos basándote en los esquemas del tomador de notas. "
                "No hagas preguntas de seguimiento."
            ),
        )
    
    async def doc_writing_node(self, state: DocumentWritingState) -> Command[Literal["supervisor_doc_writing_team"]]:
        result = await self.doc_writer_agent.ainvoke(state)
        return Command(
            update={
                "messages": [
                   HumanMessage(content=result["messages"][-1].content, name="doc_writer")
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto="supervisor_doc_writing_team",
        )

    async def note_taking_node(self, state: DocumentWritingState) -> Command[Literal["supervisor_doc_writing_team"]]:
        result = await self.note_taking_agent.ainvoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="note_taking")
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor_doc_writing_team when done
            goto="supervisor_doc_writing_team",
        )

    async def chart_generating_node(self, state: DocumentWritingState) -> Command[Literal["supervisor_doc_writing_team"]]:
        result = await self.chart_generating_agent.ainvoke(state)
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=result["messages"][-1].content, name="chart_generator"
                    )
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto="supervisor_doc_writing_team",
        )
    
    @property
    def document_writer_graph(self):
        doc_writing_supervisor_node = make_supervisor_node(llm=self.llm_gemini_flash_lite, members=["doc_writer", "note_taker", "chart_generator"])
        paper_writing_builder = StateGraph(DocumentWritingState)
        paper_writing_builder.add_node("supervisor_doc_writing_team", doc_writing_supervisor_node) # type: ignore
        paper_writing_builder.add_node("doc_writer", self.doc_writing_node)
        paper_writing_builder.add_node("note_taker", self.note_taking_node)
        paper_writing_builder.add_node("chart_generator", self.chart_generating_node)

        paper_writing_builder.add_edge(START, "supervisor_doc_writing_team")
        graph = paper_writing_builder.compile()
        return graph