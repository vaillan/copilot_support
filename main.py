from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# Importamos la función que crea nuestro agente desde agent.py
from app.utils.state import GraphState
from app.main import Executor

# --- Modelos de Datos Pydantic para la API ---
# LangChain tiene sus propios modelos, pero es mejor definir los nuestros para la API
# para desacoplar el frontend del backend.

class ChatMessage(BaseModel):
    """Representa un mensaje en la conversación (humano o de la IA)."""
    type: str  # 'human' o 'ai'
    content: str

class InvokeRequest(BaseModel):
    """El cuerpo de la petición que el cliente enviará."""
    user_query: str
    messages: List[ChatMessage]

class InvokeResponse(BaseModel):
    """La respuesta que el servidor devolverá."""
    agent_response: str
    messages: List[ChatMessage]

# --- Inicialización de la App y el Agente ---
app = FastAPI(
    title="Monday.com Agent Server",
    description="Un backend para interactuar con un agente de LangGraph para Monday.com",
    version="1.0.0",
)

# Creamos una única instancia del agente cuando el servidor arranca
executor = Executor()
agent_executor = executor.main

# --- Definición del Endpoint de la API ---
@app.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(request: InvokeRequest):
    """
    Recibe una consulta y el historial de la conversación, ejecuta el agente y devuelve la respuesta.
    """
    # Convertimos nuestros mensajes Pydantic al formato que LangChain espera
    # (Esta es una simplificación, en un caso real necesitarías importar HumanMessage, AIMessage)
    langchain_messages = [(msg.type, msg.content) for msg in request.messages]
    
    # Creamos el estado inicial para el grafo
    initial_state: GraphState = {
        "user_query": request.user_query,
        "messages": langchain_messages, # type: ignore
        "next_agent": "",  # El orquestador decidirá
        "search_results": [],
    }

    try:
        # Usamos `ainvoke` para una ejecución asíncrona, ideal para FastAPI
        final_state = await agent_executor.ainvoke(initial_state)
        
        # Extraemos la última respuesta del agente
        agent_last_response = final_state['messages'][-1]

        # Preparamos la respuesta para el cliente
        updated_messages = [
            ChatMessage(type=msg[0], content=msg[1]) if isinstance(msg, tuple) 
            else ChatMessage(type=msg.type, content=msg.content) 
            for msg in final_state['messages']
        ]
        
        return InvokeResponse(
            agent_response=agent_last_response.content,
            messages=updated_messages
        )

    except Exception as e:
        # Si algo sale mal dentro del agente, devolvemos un error 500
        raise HTTPException(status_code=500, detail=f"Error en la ejecución del agente: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "El servidor del agente de Monday.com está en funcionamiento. Usa el endpoint /invoke para interactuar."}
