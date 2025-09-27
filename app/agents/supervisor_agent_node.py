
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from ..utils.model_provider import llm
from ..utils.state import GraphState


class SupervisorResponse(BaseModel):
    next_agent: str = Field(description="El nombre del agente a llamar a continuación. Debe ser uno de: ['SearchAgent', 'ReportAgent', 'FINISH']")


class SupervisorAgentNode:

    structured_llm = llm.with_structured_output(SupervisorResponse) # type: ignore
 
    def supervisor_agent_node(self, state: GraphState):
        print("--- Ejecutando Nodo: Orquestador ---")
        if state["search_results"]:
            print("    > Decisión: Hay resultados de búsqueda, pasando a generar el reporte.")
            return {"next_agent": "ReportAgent"}
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
            "Eres el supervisor de un equipo de agentes. Tu trabajo es enrutar la consulta al agente correcto o finalizar. Agentes disponibles: SearchAgent (para buscar info), ReportAgent (se activa solo). Si la conversación parece terminada, responde 'FINISH'."), 
            MessagesPlaceholder(variable_name="messages")
            ])
        chain = prompt | self.structured_llm # type: ignore
        response = chain.invoke({"messages": state["messages"]})
        
        if response is None:
            print("    > Advertencia: La respuesta del LLM fue None. Finalizando el flujo.")
            return {"next_agent": "FINISH"}
        
        # print(f"    > Decisión del LLM: {response.next_agent}") # type: ignore
        return {"next_agent": response.next_agent} # type: ignore
