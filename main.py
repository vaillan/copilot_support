from app.tools.mcp_client import CLIENT
from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from typing import List
from contextlib import asynccontextmanager
from IPython.display import Image, display

# from app.agents.coordination import Coordination
from langchain_core.messages import HumanMessage, AIMessage # type: ignore
from langgraph.graph import MessagesState # type: ignore
# from langchain_core.runnables.graph_mermaid import _render_mermaid_using_pyppeteer
# from app.agents.research_team import ResearchTeam
# from app.agents.document_writer_team import DocumentWriterTeam
from app.agents.hierarchy_team import HierarchyTeam

class ChatMessage(BaseModel):
    type: str
    content: str

class InvokeRequest(BaseModel):
    messages: List[ChatMessage]

class InvokeResponse(BaseModel):
    messages: List[ChatMessage]

agent_executor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida del agente. Se ejecuta al iniciar y finalizar el servidor.
    """
    # global agent_executor
    global agent_executor
    # global agent_research_executor
    tools = await CLIENT.get_tools()
    executor = HierarchyTeam(tools=tools)
    agent_executor = executor.hierarchy_graph
    # try:
    #     display(Image(agent_executor.get_graph().draw_mermaid_png(output_file_path="agent_hierarchy_team.png")))
    # except Exception:
    #     pass

    yield  # La aplicación se ejecuta aquí
    # agent_executor = None
    agent_executor = None

app = FastAPI(
    lifespan=lifespan,
    title="Hierarchical Agent Server",
    description="Un backend para interactuar con sistema multiagente con un supervisor de supervisores",
    version="1.0.0",
)

@app.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(request: InvokeRequest):
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="El agente no está disponible o inicializado. Inténtalo de nuevo en unos segundos.")
    # Convertimos los mensajes de la API al formato de LangChain
    langchain_messages = []
    for msg in request.messages:
        if msg.type == "human":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif msg.type == "ai":
            langchain_messages.append(AIMessage(content=msg.content))

    initial_state: MessagesState = {"messages": langchain_messages}
    try:
        final_state = await agent_executor.ainvoke(initial_state, config={'recursion_limit': 100}) # type: ignore
        
        if final_state is None:
            raise HTTPException(status_code=500, detail="Agent execution resulted in no output.")

        response_messages = [ChatMessage(type=msg.type, content=str(msg.content)) for msg in final_state['messages']] # type: ignore
        return InvokeResponse(messages=response_messages)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la ejecución del agente: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "El servidor del agente de Monday.com está en funcionamiento. Usa el endpoint /invoke para interactuar."}
