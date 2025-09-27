from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_tool_calling_agent

from ..utils.state import GraphState
from ..tools.list_boards_tool import list_boards
from ..tools.similarity_search_tool import similarity_search
from ..utils.model_provider import llm

search_tools = [list_boards, similarity_search]

search_prompt = ChatPromptTemplate.from_messages([
        ("system", """
        Eres un especialista en analisis de datos.
        Tu objetivo final es usar la herramienta 'similarity_search'.

        **Asegurate especificamente de llamar a una herramienta, DEBES usar los valores que el usuario ha proporcionado EXPLÍCITAMENTE en la conversación. NO infieras, NO adivines y NO cambies los valores que el usuario ingresa o los términos de búsqueda. Usa los valores EXACTAMENTE como los escribió el usuario.**

        Sigue este proceso lógico paso por paso:
        1.  Para usar 'similarity_search', necesitas los parámetros {{board_name}} y {{query}}.
        2.  Revisa el historial de la conversación. Si el parámetro {{board_name}} NO ha sido especificado por el usuario, tu PRIMERA ACCIÓN debe ser llamar a la herramienta 'list_boards' para obtener las opciones.
        3.  Una vez que tengas la lista de tableros, preséntasela al usuario y pregúntale en cuál de ellos desea buscar.
        4.  Cuando el usuario finalmente te proporcione un nombre de tablero, llama a la herramienta 'similarity_search' usando la consulta original y el **nombre exacto del tablero que el usuario seleccionó**.
        """),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

search_agent_runnable = create_tool_calling_agent(llm, search_tools, search_prompt)
search_agent_executor = AgentExecutor(agent=search_agent_runnable, tools=search_tools, verbose=True)


def search_agent_node(state: GraphState):
    print("--- Ejecutando Nodo: Agente de Búsqueda ---")
    result = search_agent_executor.invoke({"messages": state["messages"]})
    tool_outputs = result.get("tool_outputs")

    if tool_outputs and isinstance(tool_outputs[0], list) and len(tool_outputs[0]) > 0:
        return {"search_results": tool_outputs[0], "messages": [AIMessage(content=f"He encontrado {len(tool_outputs[0])} ítem(s) relevante(s). Generando reporte...")]}

    return {"messages": [AIMessage(content=result["output"])]}
