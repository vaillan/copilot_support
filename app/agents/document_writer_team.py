from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage

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
                "Tu trabajo es leer el informe de investigación proporcionado y crear un esquema detallado para el redactor de documentos. "
                "El esquema debe capturar los puntos clave, la estructura y el flujo del informe. "
                "Asegúrate de que el esquema sea completo y fácil de seguir para el redactor. "
                "No hagas preguntas de seguimiento."
            ),
        )

        self.doc_writer_agent = create_react_agent(
            self.llm_gemini_flash_lite,
            tools=[
                write_document,
                edit_document,
                read_document,
                create_word_document,
                create_excel_spreadsheet,
                create_powerpoint_presentation,
            ],
            prompt=(
                "Tu trabajo es escribir un documento completo basado en el esquema proporcionado por el tomador de notas. "
                "Sigue el esquema de cerca, ampliando los puntos clave para crear un documento bien estructurado y coherente. "
                "Puedes crear documentos de texto plano, Word (.docx), Excel (.xlsx), o PowerPoint (.pptx) según se requiera."
                "Asegúrate de que el documento final esté pulido y listo para su publicación. "
                "No hagas preguntas de seguimiento."
            ),
        )
    
    async def doc_writing_node(self, state: BaseState) -> Command[Literal["supervisor"]]:
        result = await self.doc_writer_agent.ainvoke(state)
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
        result = await self.note_taking_agent.ainvoke(state)
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
            goto="supervisor",
        )
    
    @property
    def document_writer_graph(self):
        doc_writing_supervisor_node = make_supervisor_node(
            llm=self.llm_gemini_flash,
            members=["doc_writer", "note_taker", "chart_generator"],
            # system_prompt_input=(
            #     "Eres el supervisor de un equipo de redacción de documentos. Tu equipo está compuesto por los siguientes agentes: {members}. "
            #     "Se te proporcionará un informe de investigación y tu trabajo es gestionar a tu equipo para crear un documento final basado en ese informe."
            #     "Sigue estos pasos:"
            #     "1. **Creación del Esquema:** Primero, dirige al `note_taker` para que cree un esquema detallado a partir del informe de investigación. "
            #     "El esquema debe ser claro y estructurado para guiar la redacción del documento."
            #     "2. **Redacción del Documento:** Una vez que el esquema esté listo, encarga al `doc_writer` que escriba el documento basándose en el esquema. "
            #     "El `doc_writer` debe ampliar los puntos del esquema para crear un borrador completo y coherente."
            #     "3. **Generación de Gráficos (si es necesario):** Si el documento requiere gráficos o visualizaciones de datos, dirige al `chart_generator` para crearlos. "
            #     "Asegúrate de que los gráficos sean precisos y relevantes para el contenido."
            #     "4. **Revisión y Finalización:** Revisa el trabajo de todos los agentes y coordina las revisiones necesarias. "
            #     "Asegúrate de que el documento final esté bien redactado, sea preciso y esté completo."
            #     "5. **Aprobación Final:** Una vez que estés satisfecho con el documento, da tu aprobación final y termina el proceso."
            #     "Revisa el historial de la conversación y dirige al agente apropiado para continuar con el trabajo, siguiendo el plan paso a paso."
            # ),
        )
        paper_writing_builder = StateGraph(BaseState)
        paper_writing_builder.add_node(node="supervisor", action=doc_writing_supervisor_node) # type: ignore
        paper_writing_builder.add_node(node="doc_writer", action=self.doc_writing_node)
        paper_writing_builder.add_node(node="note_taker", action=self.note_taking_node)
        paper_writing_builder.add_node(node="chart_generator", action=self.chart_generating_node)

        paper_writing_builder.add_edge(start_key=START, end_key="supervisor")

        graph = paper_writing_builder.compile()
        return graph