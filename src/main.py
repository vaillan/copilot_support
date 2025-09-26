import sys
import os
from langgraph.graph import StateGraph, END

from utils.state import GraphState
from agents.supervisor_agent_node import supervisor_agent_node
from agents.search_agent_node import search_agent_node
from agents.report_agent_node import report_agent_node

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def router(state: GraphState):
    return state["next_agent"]

workflow = StateGraph(GraphState)
workflow.add_node("Supervisor", supervisor_agent_node)
workflow.add_node("SearchAgent", search_agent_node)
workflow.add_node("ReportAgent", report_agent_node) # No necesitamos el ActionAgent para este ejemplo
workflow.set_entry_point("Supervisor")
workflow.add_conditional_edges("Supervisor", router, {"SearchAgent": "SearchAgent", "ReportAgent": "ReportAgent", "FINISH": END})
workflow.add_edge("SearchAgent", "Supervisor")
workflow.add_edge("ReportAgent", END)
app = workflow.compile()
