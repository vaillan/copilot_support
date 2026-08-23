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
from app.utils.prompt_utils import escapar_llaves
from functools import lru_cache
from app.utils.args_utils import _get_args

# Límite máximo de iteraciones del Agente Planificador.
# Se redujo a 12 para acotar la exploración y evitar bucles prolongados; el
# planificador debe entregar el plan con un número acotado de iteraciones.
MAX_ITERACIONES_PLANIFICADOR = 12

# Umbral a partir del cual (en modo análisis) se instruye al LLM a cerrar la
# exploración y redactar el informe final, para evitar un ciclo de lecturas.
UMBRAL_INSTAR_CIERRE_ANALISIS = 5

# Umbral duro: si al alcanzarlo el LLM sigue solicitando herramientas de
# lectura, se fuerza la entrega del análisis con el contexto ya acumulado
# (una única llamada LLM sin herramientas), sin agotar el límite de iteraciones.
UMBRAL_FORZAR_ENTREGA_ANALISIS = 10

fileSystem = File(directory="prompts")

# Palabras que indican intención de ANÁLISIS puro (no programación).
# Incluye términos de REPORTE, ARQUITECTURA y DOCUMENTACIÓN para que
# peticiones como "genera un reporte" o "genera una arquitectura" NO
# desencadenen la fase de codificación.
PALABRAS_ANALISIS = (
    "analiza", "análisis", "analizar", "explica", "explicar", "revisa",
    "diagnostica", "¿qué hace", "resume", "compara", "investiga",
    "describe", "cómo funciona", "qué es",
    # Reportes / documentación / arquitectura (solo análisis, sin código).
    # NOTA: "diseña"/"propón" NO se incluyen aquí (son ambiguos: pueden
    # implicar implementación); solo se detectan en FRASES_ANALISIS_INICIO
    # con contexto específico de arquitectura/diseño.
    "reporte", "reporta", "arquitectura", "documenta", "documentación",
    "documentar", "documento", "elabora", "redacta", "redactar",
)

# Palabras que indican intención de CREACIÓN/MODIFICACIÓN de código.
# Su presencia anula la detección de análisis puro.
# NOTA: "genera" NO se incluye a propósito: "genera un reporte" / "genera una
# arquitectura" son análisis, mientras que "genera código" (subcadena exacta)
# sí es creación y se detecta en el fallback por subcadena.
PALABRAS_CREACION = (
    "escribe", "crea", "implementa", "modifica", "añade", "agrega",
    "corrige", "refactoriza", "construye", "genera código",
)

# Frases compuestas que, cuando la instrucción COMIENZA con ellas, indican
# intención de ANÁLISIS puro (p. ej. "Realiza el analisis para los demas
# tipos de facturas..."). Se incluyen variantes con y sin tilde.
FRASES_ANALISIS_INICIO = (
    "realiza el analisis", "haz el analisis", "realiza un analisis",
    "haz un analisis", "realiza el análisis", "haz el análisis",
    "realiza un análisis", "haz un análisis",
    # Reportes / arquitectura / documentación (solo análisis, sin código)
    "genera un reporte", "genera una arquitectura", "genera un documento",
    "genera la documentación", "genera un analisis", "genera un análisis",
    "elabora un reporte", "elabora una arquitectura", "elabora un documento",
    "redacta un reporte", "redacta la documentación", "redacta un documento",
    "propón una arquitectura", "propón un diseño", "propón una solución",
    "diseña la arquitectura", "diseña una arquitectura", "diseña un diseño",
    "documenta el", "documenta la", "documenta los", "documenta las",
)


def _contiene_verbo_creacion(texto: str) -> bool:
    """
    Detecta si el texto contiene algún VERBO de creación como PALABRA COMPLETA.

    A diferencia de la detección por subcadena, el matching por palabra
    completa (word boundary) permite distinguir verbos de creación usados como
    órdenes directas ("implementa", "crea", "refactoriza"...) de sustantivos
    derivados usados como contexto descriptivo ("refactorizacion",
    "implementacion"...). Por ejemplo, "refactorizacion" NO matchea
    "refactoriza" (tras el verbo viene "cion", sin límite de palabra), pero
    "implementa" SÍ matchea dentro de "implementa el módulo".
    """
    for p in PALABRAS_CREACION:
        if re.search(rf"\b{re.escape(p)}\b", texto):
            return True
    return False


def _es_peticion_analisis(instruccion: str) -> bool:
    """
    Detecta si la instrucción del usuario expresa intención de ANÁLISIS puro.

    La detección se realiza en 3 niveles jerárquicos:

    1. Si la instrucción COMIENZA con una frase de análisis explícita
       (FRASES_ANALISIS_INICIO, p. ej. "realiza el analisis", "haz el
       analisis") o con un verbo de análisis directo (PALABRAS_ANALISIS,
       p. ej. "analiza", "explica"), se considera análisis puro salvo que
       contenga un VERBO de creación como orden directa (p. ej. "analiza y
       luego implementa" es creación porque "implementa" es una orden).
    2. Para distinguir verbos de creación (órdenes) de sustantivos de
       creación (contexto descriptivo), se usa matching de palabra completa
       (word boundary) en lugar de subcadena. Así, "refactorizacion" como
       contexto descriptivo NO anula el análisis, pero "implementa" como
       orden directa SÍ lo anula.
    3. Como fallback (la instrucción no comienza con análisis), se mantiene
       la lógica original: análisis si contiene alguna palabra de análisis
       y NO contiene ninguna palabra de creación (por subcadena).
    """
    texto = instruccion.lower().strip()

    comienza_con_frase = any(texto.startswith(f) for f in FRASES_ANALISIS_INICIO)
    comienza_con_verbo = any(texto.startswith(p) for p in PALABRAS_ANALISIS)
    tiene_verbo_creacion = _contiene_verbo_creacion(texto)

    if comienza_con_frase or comienza_con_verbo:
        # Análisis puro salvo que haya un verbo de creación como orden directa.
        return not tiene_verbo_creacion

    # Fallback: comportamiento original (detección por subcadena).
    tiene_analisis = any(p in texto for p in PALABRAS_ANALISIS)
    tiene_creacion = any(p in texto for p in PALABRAS_CREACION)
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


def _construir_analisis_desde_contexto(state: ProjectState, instruccion: str) -> str:
    """
    Última red de seguridad: construye un análisis básico a partir del contexto
    ya recopilado en los mensajes cuando la llamada LLM final falla o no
    devuelve texto. Evita que el grafo termine sin entregables.
    """
    msgs = state.get("messages", [])
    fragmentos = []
    for m in msgs[-8:]:
        contenido = str(getattr(m, "content", "")).strip()
        if contenido and contenido not in fragmentos:
            fragmentos.append(contenido[:400])
    contexto = "\n\n".join(fragmentos[-4:]) if fragmentos else "Sin contexto adicional disponible."
    return (
        "## Resumen Ejecutivo\n"
        "El análisis alcanzó el límite de iteraciones de investigación. Se "
        "entrega la evaluación basada en la información recopilada durante la "
        "exploración del proyecto.\n\n"
        "## Análisis Detallado\n"
        f"{contexto}\n\n"
        "## Recomendaciones\n"
        "- Reconsiderar el alcance de la consulta para reducir iteraciones de "
        "exploración si se requiere exactitud adicional.\n"
        "- Revisar los archivos señalados en el índice del proyecto.\n\n"
        "## Conclusión\n"
        "Proceso concluido con la información disponible; el informe puede "
        "refinarse en una segunda ejecución."
    )


def _forzar_entrega_analisis(
    state: ProjectState,
    instruccion: str,
    llm_analisis,
    prompt_template_analisis: ChatPromptTemplate,
    mensajes_contexto_analisis: List,
) -> Command:
    """
    Fuerza la entrega del análisis cuando el LLM lleva muchas iteraciones
    llamando herramientas de lectura sin redactar el informe (evita agotar el
    límite de iteraciones del Planificador en un bucle infinito).

    Normaliza los mensajes (reemplaza ToolMessages y AIMessages con tool_calls
    por texto plano) y hace UNA única llamada LLM SIN herramientas para redactar
    el análisis final con el contexto ya acumulado. Si esa llamada falla o no
    produce texto, se construye el análisis desde el contexto de los mensajes.
    """
    mensajes_normalizados: List = []
    for m in mensajes_contexto_analisis or []:
        if isinstance(m, ToolMessage):
            contenido = str(getattr(m, "content", ""))
            mensajes_normalizados.append(
                HumanMessage(content="Resultado de herramienta:\n" + contenido[:2000])
            )
        elif isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            contenido = str(getattr(m, "content", "")).strip()
            if contenido:
                mensajes_normalizados.append(HumanMessage(content=contenido))
            mensajes_normalizados.append(
                HumanMessage(content="(El modelo consultó herramientas; los resultados se incluyen a continuación)")
            )
        else:
            mensajes_normalizados.append(m)

    mensajes_normalizados.append(
        HumanMessage(
            content=(
                "Redacta RAHORA el informe final completo en Markdown con las "
                "secciones solicitadas. No vuelvas a consultar herramientas."
            ).replace("RAHORA", "AHORA")
        )
    )

    texto_final = ""
    try:
        prompt_final = prompt_template_analisis.invoke({"messages": mensajes_normalizados})
        respuesta_final = llm_analisis.invoke(prompt_final)
        texto_final = str(getattr(respuesta_final, "content", "") or "").strip()
    except Exception:
        texto_final = ""

    if not texto_final:
        texto_final = _construir_analisis_desde_contexto(state, instruccion)

    return Command(
        update={
            "analisis_final": texto_final,
            "messages": state.get("messages", []) + [AIMessage(content=texto_final)],
            "loop_counter": 0,
        },
        goto=END
    )


def agente_planificador(state: ProjectState) -> Command:
    """
    Analiza el requerimiento, investiga el proyecto/internet y genera un plan.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > MAX_ITERACIONES_PLANIFICADOR:
        # P2: Guardar el error en 'errores_terminal' para que mcp_server.py lo
        # reporte correctamente en lugar de devolver "Tarea completada" con None.
        msg_limite = f"Error: Se ha excedido el límite máximo de iteraciones ({MAX_ITERACIONES_PLANIFICADOR}) en el Agente Planificador. El proceso se detiene para evitar un bucle infinito."
        return Command(
            update={
                "errores_terminal": msg_limite,
                "messages": [HumanMessage(content=msg_limite)]
            },
            goto=END
        )

    # --- CAMINO ALTERNATIVO: ANÁLISIS PURO (sin programación) ---
    # Si la instrucción expresa intención de análisis y NO de creación de
    # código, se genera un análisis con el LLM del planificador. P3: se bindean
    # las herramientas de LECTURA para que el LLM pueda explorar el proyecto y
    # fundamentar el reporte en el código real (antes solo generaba texto sin
    # contexto). Si el LLM llama herramientas, se enruta al nodo de herramientas
    # y se reintenta; si responde con texto, se entrega como 'analisis_final'.
    instruccion = state.get("instruccion_usuario", "")
    if state.get("solo_analisis") or _es_peticion_analisis(instruccion):
        directorio = state.get("directorio_proyecto", "./")
        herramientas_lectura = _get_tools(directorio)

        llm_analisis = get_planner_llm(temperature=0.0)
        llm_analisis_con_herramientas = llm_analisis.bind_tools(herramientas_lectura)

        # P6: Prompt estructurado con secciones claras e instrucción explícita
        # de usar las herramientas de lectura para fundamentar el reporte.
        prompt_analisis = (
            "Eres un analista técnico senior. Analiza el siguiente requerimiento "
            "sobre el proyecto y proporciona un análisis detallado y estructurado "
            "en Markdown con las siguientes secciones:\n"
            "## Resumen Ejecutivo\n"
            "## Análisis Detallado\n"
            "## Recomendaciones\n"
            "## Conclusión\n\n"
            "IMPORTANTE:\n"
            "- NO generes ni modifiques código; entrega únicamente el "
            "reporte/análisis/arquitectura solicitado.\n"
            "- Puedes usar las herramientas de lectura (read_file, "
            "list_directory, get_project_index, read_file_summary) para "
            "explorar el proyecto y fundamentar tu análisis en el código real.\n"
            "- Si necesitas más contexto, llama a las herramientas de lectura "
            "antes de redactar el reporte final.\n\n"
            f"Requerimiento:\n{instruccion}"
        )
        # Inyectar el índice del proyecto si está disponible (mejora la calidad
        # del reporte/arquitectura sin necesidad de explorar el disco).
        project_index = state.get("project_index")
        if project_index and isinstance(project_index, dict):
            from app.utils.project_index import formatear_indice_para_prompt
            indice_texto = escapar_llaves(formatear_indice_para_prompt(project_index))
            prompt_analisis += (
                "\n\n=== ÍNDICE DEL PROYECTO (contexto de referencia) ===\n"
                f"{indice_texto}"
            )

        # Freno de bucle: cuando se acumulan suficientes iteraciones de lectura,
        # se instruye al LLM a entregar el informe final ya, para no agotar el
        # límite de iteraciones en un ciclo de búsqueda de herramientas.
        if loop_counter >= UMBRAL_INSTAR_CIERRE_ANALISIS:
            prompt_analisis += (
                "\n\nIMPORTANTE: Has investigado el proyecto lo suficiente. "
                "Redacta AHORA el análisis final completo en Markdown, con las "
                "secciones solicitadas, sin llamar a más herramientas."
            )

        # Usar ChatPromptTemplate con MessagesPlaceholder para mantener el
        # historial de mensajes (incluidos los resultados de las herramientas
        # de lectura) en contexto entre iteraciones del bucle de análisis.
        prompt_template_analisis = ChatPromptTemplate.from_messages([
            ("system", prompt_analisis),
            MessagesPlaceholder(variable_name="messages")
        ])

        msgs_analisis = state.get("messages", [])
        mensajes_contexto_analisis = aplicar_resumen_middleware(msgs_analisis, llm_analisis)
        if mensajes_contexto_analisis and isinstance(mensajes_contexto_analisis[-1], AIMessage):
            mensajes_contexto_analisis = list(mensajes_contexto_analisis) + [HumanMessage(content="Continúa con el análisis.")]

        prompt_analisis_final = prompt_template_analisis.invoke({"messages": mensajes_contexto_analisis})

        # P5: Manejo de errores en la invocación LLM.
        try:
            respuesta_analisis = llm_analisis_con_herramientas.invoke(prompt_analisis_final)
        except BaseException as e:
            msg_err = f"Error al generar el análisis: {str(e)}"
            return Command(
                update={
                    "errores_terminal": msg_err,
                    "messages": state.get("messages", []) + [HumanMessage(content=msg_err)],
                    "loop_counter": 0,
                },
                goto=END
            )

        # Si el LLM quiere explorar el proyecto, enrutar al nodo de herramientas.
        if respuesta_analisis.tool_calls:
            # Freno de emergencia: si el LLM sigue llamando herramientas de
            # lectura tras muchas iteraciones, forzamos la entrega del análisis
            # con el contexto ya acumulado para no agotar el límite (bucle).
            if loop_counter >= UMBRAL_FORZAR_ENTREGA_ANALISIS:
                return _forzar_entrega_analisis(
                    state=state,
                    instruccion=instruccion,
                    llm_analisis=llm_analisis,
                    prompt_template_analisis=prompt_template_analisis,
                    mensajes_contexto_analisis=mensajes_contexto_analisis,
                )

            return Command(
                update={
                    "messages": state.get("messages", []) + [respuesta_analisis],
                    "loop_counter": loop_counter,
                },
                goto="nodo_herramientas_planificador"
            )

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
    # P5: Manejo de errores en la invocación LLM para no propagar excepciones
    # que dejen el grafo sin mensaje claro.
    try:
        respuesta = llm_con_herramientas.invoke(prompt)
    except BaseException as e:
        msg_err = f"Error al invocar el LLM del Planificador: {str(e)}"
        return Command(
            update={
                "errores_terminal": msg_err,
                "messages": [HumanMessage(content=msg_err)],
                "loop_counter": loop_counter,
            },
            goto=END
        )
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "entregar_plan_de_accion":
                plan_generado = _get_args(tool_call) # pyright: ignore[reportArgumentType]
                
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
        # Respuesta de texto sin tool_calls.
        # 1) Si la instrucción es de análisis puro (reporte/arquitectura/documentación),
        #    el contenido generado ES el entregable: terminar el grafo en END con
        #    'analisis_final' sin pasar por el codificador ni el revisor.
        # 2) Si es creación de código, reintentar pidiendo al LLM que use
        #    'entregar_plan_de_accion'. NUNCA fabricar un plan artificial con texto
        #    plano hacia el agente_codificador (evita generación de código no deseada).
        if respuesta.content and _es_peticion_analisis(state.get("instruccion_usuario", "")):
            text_content = str(respuesta.content)
            return Command(
                update={
                    "analisis_final": text_content,
                    "messages": [respuesta],
                    "loop_counter": 0
                },
                goto=END
            )

        # Escape de bucle: si el LLM responde texto plano sin llamar herramientas
        # tras varias iteraciones (loop_counter > 3), forzar la entrega del plan
        # construyendo un plan_de_accion mínimo y avanzar al codificador para no
        # quedar en bucle. Para loop_counter <= 3 se conserva el reintento actual.
        if loop_counter > 3:
            plan_minimo = {
                "explicacion_arquitectura": str(respuesta.content),
                "pasos": []
            }
            return Command(
                update={
                    "plan_de_accion": plan_minimo,
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
