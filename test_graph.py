"""Script de demostración: ejecuta el grafo con el checkpointer async por defecto.

Nota: el checkpointer por defecto es AsyncSqliteSaver, por lo que el grafo debe
ejecutarse en modo async (astream/ainvoke).
"""
import asyncio

from app.main import crear_grafo
from app.models.models import ProjectState
from langchain_core.messages import HumanMessage


async def main():
    graph = crear_grafo()
    state = ProjectState(
        messages=[HumanMessage(content="hola")],
        directorio_proyecto="./",
        instruccion_usuario="test",
        plan_de_accion={"pasos": ["crea archivo.txt con hola"]},
        codigo_escrito="",
        errores_terminal="",
        revision_count=0,
        loop_counter=0
    )
    config = {"configurable": {"thread_id": "1"}}
    async for event in graph.astream(state, config, stream_mode="values"):
        print(event)


if __name__ == "__main__":
    asyncio.run(main())
