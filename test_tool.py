import asyncio
from app.models.models import ProjectState
from app.agents.agente_codificador import nodo_herramientas_codificador
from langchain_core.messages import AIMessage

def main():
    state = ProjectState(
        messages=[AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "test.txt", "text": "hola"}, "id": "1"}])],
        directorio_proyecto="./",
        instruccion_usuario="test",
        plan_de_accion={},
        codigo_escrito="",
        errores_terminal=""
    ) # type: ignore
    res = nodo_herramientas_codificador(state, config={"configurable": {"thread_id": "test_thread"}})
    print(res)

if __name__ == "__main__":
    main()
