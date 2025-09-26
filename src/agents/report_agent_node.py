from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
import json

from utils.model_provider import llm
from utils.state import GraphState

def report_agent_node(state: GraphState):
    print("--- Ejecutando Nodo: Generación de Reportes ---")
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "Eres un asistente de productividad experto en analizar y resumir información de monday.com. Tu objetivo es transformar los datos de un ítem en un resumen claro y accionable. Usa formato Markdown. Si un campo no existe en el JSON, omítelo."),
        ("human", "Resume el siguiente ítem de monday.com, extrayendo la información más crítica. Datos del Ítem (JSON): {item_data}. Sigue esta estructura flexible: ### 📌 {item_name} (ID: {item_id})\n- **Tablero**: {board_name}\n- **Información Clave**: [Extrae dinámicamente 2-4 campos importantes como Estatus, Prioridad, etc.]\n\n#### Resumen Principal:\n[Describe el propósito central del ítem.]\n\n#### Última Actividad Relevante:\n[Describe la actualización más reciente.]\n\n#### Análisis y Próximos Pasos:\n[Ofrece un breve análisis y sugiere el siguiente paso lógico.]")
    ])
    final_report = f"Basado en tu consulta: '{state['user_query']}', he encontrado la siguiente información relevante:\n\n"
    for item in state['search_results']:
        report_chain = prompt_template | llm
        item_summary = report_chain.invoke({"item_data": json.dumps(item, indent=2, ensure_ascii=False), "item_name": item.get('item_name', 'N/A'), "item_id": item.get('item_id', 'N/A'), "board_name": item.get('board_name', 'N/A')})
        final_report += item_summary.content + "\n\n---\n\n" # type: ignore
    return {"messages": [AIMessage(content=final_report)]}
