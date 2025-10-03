from langchain_core.messages import AIMessage # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # type: ignore
from langchain.agents import AgentExecutor, create_tool_calling_agent # type: ignore
from langgraph.types import Command # type: ignore
from typing import Literal
from pydantic import BaseModel, Field # type: ignore
from ..utils.state import GraphState
from ..tools.list_boards_tool import list_boards
from ..tools.similarity_search_tool import similarity_search
from ..utils.model_provider import llm
import json
from langgraph.graph import StateGraph, MessagesState, START, END # type: ignore
from ..utils.state import GraphState
import re
from ..utils.files import File

class SupervisorSearchResponse(BaseModel):
    next_agent: str = Field(description="El nombre del agente a llamar a continuación. Debe ser uno de: ['search_agent_node', 'report_agent_node', 'FINISH']")
class SearchTeam(File):

    def __init__(self):
        super().__init__(directory="prompts")
        search_prompt_content = self.get_file_content(file_name="search_prompt.md")
        
        report_prompt_content = self.get_file_content(file_name="report_prompt.md")

        supervisor_search_prompt_content = self.get_file_content(file_name="supervisor_search_prompt.md")

        search_tools = [list_boards, similarity_search]
        search_prompt = ChatPromptTemplate.from_messages([
            ("system", search_prompt_content),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        self.report_prompt = ChatPromptTemplate.from_messages([
            ("system", report_prompt_content),
            ("human", "{item_data}")
        ])

        supervisor_search_prompt = ChatPromptTemplate.from_messages([
            ("system", supervisor_search_prompt_content),
            MessagesPlaceholder(variable_name="messages")
        ])
        structured_llm_search = llm.with_structured_output(SupervisorSearchResponse)
        self.supervisor_search_chain = supervisor_search_prompt | structured_llm_search

        search_agent_runnable = create_tool_calling_agent(llm, search_tools, search_prompt)
        self.search_agent_executor = AgentExecutor(agent=search_agent_runnable, tools=search_tools, verbose=True)

    def search_agent_node(self, state: GraphState) -> Command[Literal["supervisor_search_agent_node", "report_agent_node"]]:
        # print("--- Ejecutando Nodo: Agente de Búsqueda ---")
        result = self.search_agent_executor.invoke({"messages": state["messages"]})
        agent_output = result.get("output")

        try:
            match = re.search(r"```json\s*(.*?)\s*```", agent_output, re.DOTALL | re.IGNORECASE) # type: ignore
            json_string_content = None
            if match:
                json_string_content = match.group(1)
            else:
                json_string_content = agent_output.strip() # type: ignore
            
            if not json_string_content:
                return ValueError("Error Contenido vacio") # type: ignore

            json_object = json.loads(json_string_content)
    
            result_data = {"search_results": json_object}
            return Command(goto="report_agent_node", update=result_data)
        except (json.JSONDecodeError, TypeError):
            result_data = {"messages": [AIMessage(content=agent_output)]} # type: ignore
            return Command(goto="supervisor_search_agent_node", update=result_data)

    def report_agent_node(self, state: GraphState) -> Command[Literal["supervisor_search_agent_node"]]:
        # print("--- Ejecutando Nodo: Generación de Reportes ---")
        final_report = f"Reporte ejecutivo:\n\n"
        search_results = state['search_results'] # type: ignore
        report_chain = self.report_prompt | llm
        if(len(search_results[0]['results']) == 0):
            return Command(goto=END, update={"messages": [AIMessage(content="No se encontraron datos en el tablero ingresado")]}) # type: ignore

        for item in search_results[0]['results']: # type: ignore
            # Esta invocación ahora funciona perfectamente con el nuevo prompt
            item_summary = report_chain.invoke({
                "item_data": json.dumps(item, indent=2, ensure_ascii=False),
                "item_name": search_results[0].get('item_name', 'N/A'),
                "item_id": search_results[0].get('item_id', 'N/A'),
                "board_name": search_results[0].get('board_name', 'N/A') 
            })
            
            final_report += item_summary.content + "\n\n---\n\n" # type: ignore
        
        return Command(goto="supervisor_search_agent_node", update={"messages": [AIMessage(content=final_report)]}) # type: ignore

    def supervisor_search_agent_node(self, state: GraphState) -> Command[Literal["search_agent_node", "report_agent_node", END]]: # type: ignore
        # print("--- Ejecutando Nodo: Orquestador ---")
        if isinstance(state["messages"][-1], AIMessage):
            return Command(goto=END)

        if state.get("search_results"):
            return Command(goto="report_agent_node")

        response = self.supervisor_search_chain.invoke({"messages": state["messages"]})

        return Command(goto=response.next_agent) # type: ignore

    @property
    def supervisor_search_graph(self):
        workflow = StateGraph(GraphState)
        workflow.add_node(node="supervisor_search_agent_node", action=self.supervisor_search_agent_node)
        workflow.add_node(node="search_agent_node", action=self.search_agent_node)
        workflow.add_node(node="report_agent_node", action=self.report_agent_node)
        
        workflow.add_edge(start_key=START, end_key="supervisor_search_agent_node")
        #workflow.add_edge(start_key="search_agent_node", end_key="supervisor_search_agent_node")
        #workflow.add_edge(start_key="report_agent_node", end_key="supervisor_search_agent_node")
        return workflow.compile()
