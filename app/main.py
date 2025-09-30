# from .agents.coordination import Coordination

# # --- NUEVO BLOQUE PARA GENERAR LA IMAGEN DEL GRAFO ---
# executor = Coordination()
# app = executor.supervisor_general_graph
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
#     print("Si el error persiste, asegúrate de haber ejecutado 'pip install pyppeteer' y 'python -m pyppeteer.install' en tu entorno.")
