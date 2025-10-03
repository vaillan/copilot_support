from app.tools.mcp_client import CLIENT
from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from typing import List
from contextlib import asynccontextmanager
from IPython.display import Image, display

from app.agents.coordination import Coordination
from langchain_core.messages import HumanMessage, AIMessage # type: ignore
from langgraph.graph import MessagesState # type: ignore
from langchain_core.runnables.graph_mermaid import _render_mermaid_using_pyppeteer

# --- Modelos de Datos Pydantic (sin cambios) ---
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
    global agent_executor
    tools = await CLIENT.get_tools()
    coordinator = Coordination(tools=tools)
    agent_executor = coordinator.supervisor_general_graph
    # graph = agent_executor
    # graph_search_team = coordinator.team_search
    # graph_action_team = coordinator.team_action
    # try:
    #     display(Image(graph.get_graph().draw_mermaid_png(output_file_path="flujo_del_agente_general.png")))
    #     display(Image(graph_search_team.supervisor_search_graph.get_graph().draw_mermaid_png(output_file_path="flujo_del_agente_busqueda.png")))
    #     display(Image(graph_action_team.supervisor_action_graph.get_graph().draw_mermaid_png(output_file_path="flujo_del_agente_accion.png")))
        
    # except Exception:
    #     pass

    yield  # La aplicación se ejecuta aquí
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
        final_state = await agent_executor.ainvoke(initial_state) # type: ignore
        response_messages = [ChatMessage(type=msg.type, content=str(msg.content)) for msg in final_state['messages']]
        return InvokeResponse(messages=response_messages)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la ejecución del agente: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "El servidor del agente de Monday.com está en funcionamiento. Usa el endpoint /invoke para interactuar."}
