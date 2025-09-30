from app.tools.mcp_client import CLIENT
from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from typing import List
from contextlib import asynccontextmanager

# 1. Importación corregida: Asume que tu script se ejecuta desde el directorio raíz del proyecto.
from app.agents.coordination import Coordination
from langchain_core.messages import HumanMessage, AIMessage # type: ignore
from langgraph.graph import MessagesState # type: ignore
from langchain_core.runnables.graph_mermaid import MermaidDrawMethod # type: ignore
import logging
from pathlib import Path
# Configuración de logging profesional
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Modelos de Datos Pydantic (sin cambios) ---
class ChatMessage(BaseModel):
    type: str
    content: str

class InvokeRequest(BaseModel):
    messages: List[ChatMessage]

class InvokeResponse(BaseModel):
    messages: List[ChatMessage]

# 2. Variable global para mantener la instancia del agente ejecutor.
#    Se inicializará de forma asíncrona durante el arranque en el 'lifespan'.
agent_executor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida del agente. Se ejecuta al iniciar y finalizar el servidor.
    """
    global agent_executor    
    # Usamos la fábrica asíncrona que definimos en el paso anterior
    tools = await CLIENT.get_tools()
    coordinator = Coordination(tools=tools)

    agent_executor = coordinator.supervisor_general_graph 
    yield  # La aplicación se ejecuta aquí
    agent_executor = None

# 3. Creamos la aplicación FastAPI UNA SOLA VEZ, pasándole el lifespan.
app = FastAPI(
    lifespan=lifespan,
    title="Hierarchical Monday.com Agent Server",
    description="Un backend para interactuar con un agente de LangGraph para Monday.com",
    version="1.0.0",
)

# --- Endpoints de la API ---
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
        final_state = await agent_executor.ainvoke(initial_state)
        response_messages = [ChatMessage(type=msg.type, content=str(msg.content)) for msg in final_state['messages']]
        return InvokeResponse(messages=response_messages)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la ejecución del agente: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "El servidor del agente de Monday.com está en funcionamiento. Usa el endpoint /invoke para interactuar."}
