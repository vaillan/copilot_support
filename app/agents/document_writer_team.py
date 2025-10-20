from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from google.ai.generativelanguage_v1beta.types import Tool as GenAITool

from ..agents.make_supervisor_node import make_supervisor_node
from ..utils.state import BaseState

from ..utils.files import File
from ..tools.doc_tools import *
from ..settings.settings import Settings

settings = Settings()

class DocumentWriterTeam(File):
    def __init__(self):
        self.llm_gemini_flash_lite = ChatGoogleGenerativeAI(
            model="models/gemini-flash-lite-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.5,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        
        self.llm_gemini_flash = ChatGoogleGenerativeAI(
            model="models/gemini-flash-latest",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.5,
            top_p=0.9,
            max_retries=10,
            timeout=15,
            transport='grpc_asyncio',
        )
        
        self.chart_generating_agent = create_agent(
            self.llm_gemini_flash_lite, tools=[read_document]
        )

        self.note_taking_agent = create_agent(
            self.llm_gemini_flash_lite,
            tools=[create_outline, read_document],
            system_prompt=(
                "Tu trabajo es leer el informe de investigación proporcionado y crear un esquema detallado para el redactor de documentos. "
                "El esquema debe capturar los puntos clave, la estructura y el flujo del informe. "
                "Asegúrate de que el esquema sea completo y fácil de seguir para el redactor. "
                "No hagas preguntas de seguimiento."
            ),
        )

        self.doc_writer_agent = create_agent(
            self.llm_gemini_flash_lite,
            tools=[
                write_document,
                edit_document,
                read_document,
                create_word_document,
                create_excel_spreadsheet,
                create_powerpoint_presentation,
            ],
            system_prompt=(
                "Tu trabajo es escribir un documento completo basado en el esquema proporcionado por el tomador de notas. "
                "Sigue el esquema de cerca, ampliando los puntos clave para crear un documento bien estructurado y coherente. "
                "Puedes crear documentos de texto plano, Word (.docx), Excel (.xlsx), o PowerPoint (.pptx) según se requiera."
                "Asegúrate de que el documento final esté pulido y listo para su publicación. "
                "No hagas preguntas de seguimiento."
            ),
        )
    
    async def doc_writing_node(self, state: BaseState) -> Command[Literal["supervisor"]]:
        result = await self.doc_writer_agent.ainvoke(state) # type: ignore
        return Command(
            update={
                "messages": [
                   HumanMessage(content=result["messages"][-1].content, name="doc_writer")
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto="supervisor",
        )

    async def note_taking_node(self, state: BaseState) -> Command[Literal["supervisor"]]:
        result = await self.note_taking_agent.ainvoke(state) # type: ignore
        return Command(
            update={
                "messages": [
                    HumanMessage(content=result["messages"][-1].content, name="note_taking")
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto="supervisor",
        )

    async def chart_generating_node(self, state: BaseState) -> Command[Literal["supervisor"]]:
        result = await self.chart_generating_agent.ainvoke(state, tools=[GenAITool(code_execution={})]) # type: ignore
        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=result["messages"][-1].content, name="chart_generator"
                    )
                ]
            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto="supervisor",
        )
    
    @property
    def document_writer_graph(self):
        doc_writing_supervisor_node = make_supervisor_node(
            llm=self.llm_gemini_flash,
            members=["doc_writer", "note_taker", "chart_generator"],
        )
        paper_writing_builder = StateGraph(BaseState)
        paper_writing_builder.add_node("supervisor", doc_writing_supervisor_node) # type: ignore
        paper_writing_builder.add_node("doc_writer", self.doc_writing_node)
        paper_writing_builder.add_node("note_taker", self.note_taking_node)
        paper_writing_builder.add_node("chart_generator", self.chart_generating_node)

        paper_writing_builder.add_edge("doc_writer", "supervisor")
        paper_writing_builder.add_edge("note_taker", "supervisor")
        paper_writing_builder.add_edge("chart_generator", "supervisor")
        paper_writing_builder.add_edge(START, "supervisor")

        graph = paper_writing_builder.compile()
        return graph