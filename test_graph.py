import asyncio
from app.main import crear_grafo
from app.models.models import ProjectState
from langchain_core.messages import HumanMessage
graph = crear_grafo()
state = ProjectState(
    messages=[HumanMessage(content="hola")],
    directorio_proyecto="./",
    instruccion_usuario="test",
    plan_de_accion={"pasos": ["crea archivo.txt con hola"]},
    codigo_escrito="",
    errores_terminal=""
)
config = {"configurable": {"thread_id": "1"}}
for event in graph.stream(state, config, stream_mode="values"):
    print(event)
