from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.graph import END
from langchain_core.tools import Tool, tool
from langgraph.prebuilt import ToolNode
from app.models.llm_factory import get_planner_llm
from app.models.models import ProjectState
from langchain_core.runnables import RunnableConfig
from app.utils.files import File, get_custom_file_tools
from app.utils.summarization import aplicar_resumen_middleware
from app.utils.prompt_utils import escapar_llaves
from functools import lru_cache
from app.utils.args_utils import _get_args

fileSystem = File(directory="prompts")

class Paso(BaseModel):
    archivo: str = Field(description="Ruta relativa del archivo a modificar o crear")
    tarea: str = Field(description="Descripción técnica de lo que el codificador debe programar")
    requiere_test: bool = Field(description="True si este paso necesita una prueba unitaria")

class PlanDeAccionInput(BaseModel):
    explicacion_arquitectura: str = Field(description="Breve explicación del enfoque técnico")
    pasos: List[Paso]

@tool(args_schema=PlanDeAccionInput)
def entregar_plan_de_accion(explicacion_arquitectura: str, pasos: List[Paso]) -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de investigar y estés listo para entregar el plan.
    """
    return "Plan de acción aceptado e iniciando fase de codificación."

@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    todas = get_custom_file_tools(directorio)
    herramientas_lectura = [
        t for t in todas
        if t.name in ["read_file", "list_directory", "get_project_index", "read_file_summary"]
    ]
    
    searx = DuckDuckGoSearchAPIWrapper(max_results=2)
    tool_busqueda = Tool(
        name="busqueda_web_duckduckgo",
        description="Busca en internet documentación técnica actualizada, tutoriales o foros.",
        func=searx.run
    )
    herramientas = herramientas_lectura + [tool_busqueda]
    return herramientas

def agente_planificador(state: ProjectState) -> Command:
    """
    Analiza el requerimiento, investiga el proyecto/internet y genera un plan.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > 15:
        return Command(
            update={
                "messages": [HumanMessage(content="Error: Se ha excedido el límite máximo de iteraciones (15) en el Agente Planificador. El proceso se detiene para evitar un bucle infinito.")]
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_investigacion = _get_tools(directorio)
    
    llm = get_planner_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_investigacion + [entregar_plan_de_accion])
    
    prompt_sistema = fileSystem.get_file_content(file_name="planificador_prompt.md")
    
    # Inyectar el índice del proyecto si está disponible en el estado (optimización de tokens)
    project_index = state.get("project_index")
    if project_index and isinstance(project_index, dict):
        from app.utils.project_index import formatear_indice_para_prompt
        indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index))
        prompt_sistema += (
            "\n\n=== ÍNDICE DEL PROYECTO (proporcionado, NO necesitas explorar todo) ===\n"
            f"{indice_texto}"
        )
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa con la planificación.")]

    prompt = prompt_template.invoke({"messages": mensajes_contexto, "directorio": directorio})
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "entregar_plan_de_accion":
                plan_generado = _get_args(tool_call)
                
                tool_messages = []
                for tc in respuesta.tool_calls:
                    if tc["name"] == "entregar_plan_de_accion":
                        arq = plan_generado.get('explicacion_arquitectura', 'desconocido')
                        content = f"Plan de acción aceptado e iniciando fase de codificación para: {arq}"
                    else:
                        content = "Ignorado en favor del plan final"
                    
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=tc["id"],
                            content=content,
                        )
                    )
                
                return Command(
                    update={
                        "plan_de_accion": plan_generado,
                        "messages": [respuesta] + tool_messages,
                        "loop_counter": 0
                    },
                    goto="agente_codificador"
                )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_planificador"
        )
    else:
        # Si la respuesta es de texto y llevamos 2 o más reintentos sin herramientas, derivamos un plan con el contenido generado
        if loop_counter >= 2 and respuesta.content:
            text_content = str(respuesta.content)
            plan_generado = {
                "explicacion_arquitectura": text_content[:200],
                "pasos": [{"archivo": "main.py", "tarea": state.get("instruccion_usuario", text_content), "requiere_test": False}]
            }
            return Command(
                update={
                    "plan_de_accion": plan_generado,
                    "messages": [respuesta],
                    "loop_counter": 0
                },
                goto="agente_codificador"
            )

        msg = "Debes llamar a una herramienta para investigar o llamar a entregar_plan_de_accion si ya terminaste."
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=msg)],
                "loop_counter": loop_counter
            },
            goto="agente_planificador"
        )

def nodo_herramientas_planificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de investigación utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state, config=config)
