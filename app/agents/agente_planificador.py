import re

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
from app.utils.prompt_utils import escapar_llaves, construir_prompt_template_cacheado
from app.utils.skills_loader import cargar_skills_para_prompt
from functools import lru_cache
from app.utils.args_utils import _get_args

fileSystem = File(directory="prompts")

# Palabras que indican intención de ANÁLISIS puro (no programación).
PALABRAS_ANALISIS = (
    "analiza", "análisis", "analizar", "explica", "explicar", "revisa",
    "diagnostica", "¿qué hace", "resume", "compara", "investiga",
    "describe", "cómo funciona", "qué es",
)

# Palabras que indican intención de CREACIÓN/MODIFICACIÓN de código.
# Su presencia anula la detección de análisis puro.
PALABRAS_CREACION = (
    "escribe", "crea", "implementa", "modifica", "añade", "agrega",
    "corrige", "refactoriza", "construye", "genera código",
)


def _construir_patron_palabras(palabras: tuple) -> "re.Pattern":
    """
    Construye un regex con límites de palabra a partir de una tupla de frases.

    Los límites de palabra evitan falsos positivos por subcadena (p. ej. que un
    término coincida dentro de una palabra distinta). Las frases que empiezan o
    terminan con carácter no alfanumérico (ej. '¿qué hace') no reciben límite en
    ese lado para no invalidar la coincidencia.

    Args:
        palabras: Tupla de frases/palabras clave (tuple[str, ...]).

    Returns:
        re.Pattern: Patrón compilado que coincide con alguna de las frases.
    """
    partes = []
    for frase in palabras:
        escapada = re.escape(frase)
        prefijo = r"\b" if frase and frase[0].isalnum() else ""
        sufijo = r"\b" if frase and frase[-1].isalnum() else ""
        partes.append(f"{prefijo}{escapada}{sufijo}")
    return re.compile("|".join(partes))


_PATRON_ANALISIS = _construir_patron_palabras(PALABRAS_ANALISIS)
_PATRON_CREACION = _construir_patron_palabras(PALABRAS_CREACION)

# --- Umbrales anti-bucle del Planificador ---
# Iteración desde la cual se fuerza tool_choice hacia la entrega del plan.
UMBRAL_FORZAR_PLAN = 10
# Iteración desde la cual se usa salida estructurada como red de seguridad.
UMBRAL_PLAN_ESTRUCTURADO = 13
# Máximo de respuestas vacías consecutivas toleradas antes de abortar.
MAX_RESPUESTAS_VACIAS = 2


def _es_peticion_analisis(instruccion: str) -> bool:
    """
    Detecta si la instrucción del usuario expresa intención de ANÁLISIS puro.

    Devuelve True si la instrucción contiene alguna palabra de análisis (PALABRAS_ANALISIS) y NO contiene ninguna palabra de creación/modificación de código (PALABRAS_CREACION). La detección usa regex con límites de palabra (no subcadenas sueltas), lo que reduce falsos positivos. La presencia de cualquier palabra de creación anula la detección de análisis aunque también contenga palabras de análisis.

    Args:
        instruccion: Texto de la instrucción del usuario (str).

    Returns:
        bool: True si la instrucción expresa análisis puro; False en caso contrario.
    """
    texto = instruccion.lower()
    tiene_analisis = bool(_PATRON_ANALISIS.search(texto))
    tiene_creacion = bool(_PATRON_CREACION.search(texto))
    return tiene_analisis and not tiene_creacion


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
    Entrega el plan de acción final y culmina la fase de planificación.

    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de investigar y estés listo para entregar el plan.

    Args:
        explicacion_arquitectura: Breve explicación del enfoque técnico (str).
        pasos: Lista de pasos del plan de acción (list[Paso]).

    Reglas de uso:
        - Invocar UNA SOLA VEZ, al final del análisis, nunca durante la exploración.
        - Cada paso debe contener exactamente los campos archivo, tarea y requiere_test.

    Returns:
        str: Mensaje de confirmación de que el plan fue aceptado.
    """
    return "Plan de acción aceptado e iniciando fase de codificación."

@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    """
    Lista (con caché) las herramientas de investigación del directorio dado.

    Args:
        directorio: Ruta del directorio del proyecto (str).

    Returns:
        list[Tool]: Herramientas de lectura/archivo más la búsqueda web DuckDuckGo.
    """
    todas = get_custom_file_tools(directorio)
    herramientas_lectura = [
        t for t in todas
        if t.name in ["read_file", "list_directory", "get_project_index", "read_file_summary"]
    ]
    
    searx = DuckDuckGoSearchAPIWrapper(max_results=1)
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
        msg_tope = (
            "Error: Se ha excedido el límite máximo de iteraciones (15) en el Agente "
            "Planificador. El proceso se detiene para evitar un bucle infinito."
        )
        return Command(
            update={
                "errores_terminal": msg_tope,
                "messages": [HumanMessage(content=msg_tope)],
            },
            goto=END
        )

    # --- CAMINO ALTERNATIVO: ANÁLISIS PURO (sin programación) ---
    # Si la instrucción expresa intención de análisis y NO de creación de
    # código, se genera un análisis directamente con el LLM del planificador
    # (sin bindear herramientas para evitar tool_calls) y se termina el grafo
    # sin pasar por el codificador ni el revisor.
    instruccion = state.get("instruccion_usuario", "")
    if _es_peticion_analisis(instruccion):
        directorio = state.get("directorio_proyecto", "./")
        prompt_sistema_analisis = fileSystem.get_file_content(file_name="analisis_prompt.md")

        project_index = state.get("project_index")
        if project_index and isinstance(project_index, dict):
            from app.utils.project_index import formatear_indice_para_prompt
            indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index))
            prompt_sistema_analisis += (
                "\n\n=== ÍNDICE DEL PROYECTO (proporcionado para análisis contextual) ===\n"
                f"{indice_texto}"
            )

        seccion_skills = cargar_skills_para_prompt(directorio, agente="planificador")
        if seccion_skills:
            prompt_sistema_analisis += "\n\n" + seccion_skills

        prompt_template_analisis = ChatPromptTemplate.from_messages([
            ("system", prompt_sistema_analisis),
            ("human", "Requerimiento a analizar:\n{instruccion}")
        ])

        llm_analisis = get_planner_llm(temperature=0.0)
        prompt_invocado = prompt_template_analisis.invoke({
            "directorio": directorio,
            "instruccion": instruccion,
        })
        respuesta_analisis = llm_analisis.invoke(prompt_invocado)
        analisis_texto = str(respuesta_analisis.content)
        return Command(
            update={
                "analisis_final": analisis_texto,
                "messages": state.get("messages", []) + [AIMessage(content=analisis_texto)],
                "loop_counter": 0,
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_investigacion = _get_tools(directorio)

    llm = get_planner_llm(temperature=0.0)
    herramientas_completas = herramientas_investigacion + [entregar_plan_de_accion]
    llm_con_herramientas = llm.bind_tools(herramientas_completas)
    if loop_counter >= UMBRAL_FORZAR_PLAN:
        # Anti-bucle: en iteraciones tardías se fuerza la entrega del plan vía
        # tool_choice. Si el proveedor no soporta tool_choice, se degrada sin
        # error al binding normal.
        try:
            llm_con_herramientas = llm.bind_tools(
                herramientas_completas,
                tool_choice="entregar_plan_de_accion",
            )
        except Exception:
            pass

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

    seccion_skills = cargar_skills_para_prompt(directorio, agente="planificador")
    if seccion_skills:
        prompt_sistema += "\n\n" + seccion_skills

    # Caché de template: reutiliza la instancia compilada si el prompt de sistema
    # es idéntico al de la iteración anterior (ahorro de trabajo redundante).
    prompt_template = construir_prompt_template_cacheado(prompt_sistema)
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa con la planificación.")]

    # Red de seguridad final anti-bucle: en iteraciones muy tardías no se confía
    # en que el modelo emita la tool_call; se extrae el plan con salida
    # estructurada tipada (PlanDeAccionInput). Ante cualquier fallo se degrada
    # al flujo normal de tool-calls.
    if loop_counter >= UMBRAL_PLAN_ESTRUCTURADO:
        try:
            llm_estructurado = llm.with_structured_output(PlanDeAccionInput)
            plan_input = llm_estructurado.invoke(mensajes_contexto)
            plan_generado = (
                plan_input.model_dump() if hasattr(plan_input, "model_dump") else dict(plan_input)
            )
            return Command(
                update={
                    "plan_de_accion": plan_generado,
                    "messages": [AIMessage(content="Plan de acción generado mediante salida estructurada (red de seguridad anti-bucle del Planificador).")],
                    "loop_counter": 0,
                    "empty_response_count": 0,
                },
                goto="agente_codificador"
            )
        except Exception:
            pass

    prompt = prompt_template.invoke({"messages": mensajes_contexto, "directorio": directorio})
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "entregar_plan_de_accion":
                plan_generado = _get_args(tool_call)

                # Validación anti-bucle: si los argumentos llegan vacíos o sin
                # 'pasos' (args malformados del LLM), se responde con un error
                # de herramienta para que el modelo reintente con argumentos
                # válidos, en lugar de aceptar un plan vacío en silencio.
                pasos_plan = plan_generado.get("pasos") if isinstance(plan_generado, dict) else None
                if not isinstance(pasos_plan, list) or not pasos_plan:
                    contenido_error = (
                        "ERROR: argumentos inválidos para 'entregar_plan_de_accion'. Se requiere "
                        "'explicacion_arquitectura' (str) y 'pasos' (lista no vacía) donde cada paso "
                        "tenga los campos 'archivo', 'tarea' y 'requiere_test'. Corrige los argumentos "
                        "y vuelve a invocar la herramienta."
                    )
                    tool_messages_error = [
                        ToolMessage(tool_call_id=tc["id"], content=contenido_error)
                        for tc in respuesta.tool_calls
                    ]
                    return Command(
                        update={
                            "messages": [respuesta] + tool_messages_error,
                            "loop_counter": loop_counter,
                            "empty_response_count": 0,
                        },
                        goto="agente_planificador"
                    )

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
                        "loop_counter": 0,
                        "empty_response_count": 0
                    },
                    goto="agente_codificador"
                )
        
        return Command(
            update={
                "messages": [respuesta],
                "empty_response_count": 0,
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_planificador"
        )
    else:
        contenido_texto = str(respuesta.content or "").strip()

        # Anti-bucle: respuesta vacía (sin tool_calls ni contenido). Se tolera un
        # máximo de MAX_RESPUESTAS_VACIAS consecutivas; después se aborta con
        # error explícito en el estado en lugar de loopear en silencio.
        if not contenido_texto:
            vacias_consecutivas = state.get("empty_response_count", 0) + 1
            if vacias_consecutivas >= MAX_RESPUESTAS_VACIAS:
                msg_error = (
                    f"Error: el Agente Planificador devolvió {vacias_consecutivas} respuestas vacías "
                    "consecutivas (sin tool_calls ni contenido). Se aborta para evitar un bucle infinito."
                )
                return Command(
                    update={
                        "errores_terminal": msg_error,
                        "messages": [respuesta, HumanMessage(content=msg_error)],
                        "loop_counter": loop_counter
                    },
                    goto=END
                )
            msg = "Debes llamar a una herramienta para investigar o llamar a entregar_plan_de_accion si ya terminaste."
            return Command(
                update={
                    "messages": [respuesta, HumanMessage(content=msg)],
                    "empty_response_count": vacias_consecutivas,
                    "loop_counter": loop_counter
                },
                goto="agente_planificador"
            )

        # Si la respuesta es de texto y llevamos 2 o más reintentos sin herramientas, derivamos un plan con el contenido generado
        if loop_counter >= 2:
            text_content = str(respuesta.content)
            plan_generado = {
                "explicacion_arquitectura": text_content[:200],
                "pasos": [{"archivo": "main.py", "tarea": state.get("instruccion_usuario", text_content), "requiere_test": False}]
            }
            return Command(
                update={
                    "plan_de_accion": plan_generado,
                    "messages": [respuesta],
                    "loop_counter": 0,
                    "empty_response_count": 0
                },
                goto="agente_codificador"
            )

        msg = "Debes llamar a una herramienta para investigar o llamar a entregar_plan_de_accion si ya terminaste."
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=msg)],
                "empty_response_count": 0,
                "loop_counter": loop_counter
            },
            goto="agente_planificador"
        )

def nodo_herramientas_planificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de investigación mediante ToolNode de LangGraph.

    Args:
        state: Estado global del proyecto (ProjectState).
        config: Configuración de ejecución de LangGraph (RunnableConfig).

    Returns:
        dict: Resultado de la ejecución de las herramientas de investigación.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state, config=config)
