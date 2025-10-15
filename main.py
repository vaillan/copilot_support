from fastapi import FastAPI
from app.router import agent

app = FastAPI(
    lifespan=agent.lifespan,
    title="Hierarchical Agent Server",
    description="Un backend para interactuar con sistema multiagente con un supervisor de supervisores",
    version="1.0.0",
)

app.include_router(agent.router, prefix="/agent", tags=["Agent"]) # Incluye el router de agentes

@app.get("/")
def read_root():
    return {"message": "El servidor del agente Hierarchical RAG está en funcionamiento."}
