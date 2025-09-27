from langgraph.graph import StateGraph, END
from .utils.state import GraphState
from .agents.supervisor_agent_node import supervisor_agent_node
from .agents.search_agent_node import search_agent_node
from .agents.report_agent_node import report_agent_node

class Executor:

    def _router(self, state: GraphState):
        return state["next_agent"]

    def main(self):
        workflow = StateGraph(GraphState)
        workflow.add_node("Supervisor", supervisor_agent_node)
        workflow.add_node("SearchAgent", search_agent_node)
        workflow.add_node("ReportAgent", report_agent_node) # No necesitamos el ActionAgent para este ejemplo
        workflow.set_entry_point("Supervisor")
        workflow.add_conditional_edges("Supervisor", self._router, {"SearchAgent": "SearchAgent", "ReportAgent": "ReportAgent", "FINISH": END})
        workflow.add_edge("SearchAgent", "Supervisor")
        workflow.add_edge("ReportAgent", END)
        return workflow.compile()


# # --- NUEVO BLOQUE PARA GENERAR LA IMAGEN DEL GRAFO ---
# executor = Executor()
# app = executor.main()
# print("\n--- Compilando la imagen del grafo ---")
# try:
#     # Obtiene el grafo en un formato dibujable
      
#     graph = app.get_graph()
    
#     # Dibuja el grafo y lo guarda como un archivo PNG
#     # Puedes cambiar el nombre del archivo si lo deseas
#     graph.draw_mermaid_png(output_file_path="flujo_del_agente.png")
    
#     print("✅ ¡Imagen del grafo guardada en 'flujo_del_agente.png'!")

# except ImportError as e:
#     print(f"❌ Error al generar la imagen: {e}")
#     print("Asegúrate de haber instalado Graphviz en tu sistema y la librería 'pygraphviz' de Python.")
#     print("Consulta las instrucciones de instalación para tu sistema operativo.")
# except Exception as e:
#     print(f"❌ Ocurrió un error inesperado al generar la imagen: {e}")