import sys
from functools import lru_cache
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.graph import END
from langgraph.prebuilt import ToolNode

from app.models.llm_factory import get_coder_llm
from app.models.models import ProjectState
from app.utils.files import File, get_custom_file_tools
from app.utils.summarization import aplicar_resumen_middleware

fileSystem = File(directory="prompts")


class CodigoCompletadoInput(BaseModel):
    resumen_cambios: str = Field(description="Resumen detallado de los archivos que creaste o modificaste.")


@tool(args_schema=CodigoCompletadoInput)
def CodigoCompletado(resumen_cambios: str) -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de programar todos los pasos del plan.
    """
    return "Fase de desarrollo concluida. Enviando a revisión de código."


@lru_cache(maxsize=10)
def _get_tools(directorio: str):
    todas = get_custom_file_tools(directorio)
    herramientas_edicion = [
        t for t in todas 
        if t.name in ["read_file", "write_file", "file_delete", "copy_file", "move_file", "list_directory"]
    ]
    return herramientas_edicion


def agente_codificador(state: ProjectState) -> Command:
    """
    Escribe el código necesario basándose estrictamente en el plan de acción aprobado.
    """
    loop_counter = state.get("loop_counter", 0) + 1
    if loop_counter > 15:
        return Command(
            update={
                "messages": [HumanMessage(content="Error: Se ha excedido el límite máximo de iteraciones (15) en el Agente Codificador. El proceso se detiene.")]
            },
            goto=END
        )

    directorio = state.get("directorio_proyecto", "./")
    herramientas_edicion = _get_tools(directorio)
    
    llm = get_coder_llm(temperature=0.0)
    llm_con_herramientas = llm.bind_tools(herramientas_edicion + [CodigoCompletado])
    
    prompt_sistema = fileSystem.get_file_content(file_name="codificador_prompt.md")
    
    errores = state.get("errores_terminal")
    if errores:
        errores_escaped = str(errores).replace("{", "{{").replace("}", "}}")
        prompt_sistema += f"\n\nATENCIÓN: La ejecución de pruebas anterior falló con los siguientes errores:\n{errores_escaped}\nDebes corregirlos inmediatamente antes de volver a llamar a CodigoCompletado."

    plan = state.get("plan_de_accion", {})
    plan_escaped = str(plan).replace("{", "{{").replace("}", "}}")
    prompt_sistema = prompt_sistema.replace("{plan}", plan_escaped)

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Optimización de contexto con SummarizationMiddleware
    msgs = state.get("messages", [])
    mensajes_contexto = aplicar_resumen_middleware(msgs, llm)
    if mensajes_contexto and isinstance(mensajes_contexto[-1], AIMessage):
        mensajes_contexto = list(mensajes_contexto) + [HumanMessage(content="Continúa programando los archivos pendientes.")]

    prompt = prompt_template.invoke({"messages": mensajes_contexto, "directorio": directorio})
    respuesta = llm_con_herramientas.invoke(prompt)
    
    if respuesta.tool_calls:
        for tool_call in respuesta.tool_calls:
            if tool_call["name"] == "CodigoCompletado":
                # Validar si efectivamente se escribieron o modificaron archivos previamente
                archivos_escritos = False
                for m in msgs:
                    if isinstance(m, AIMessage) and m.tool_calls:
                        for tc in m.tool_calls:
                            if tc.get("name") in ["write_file", "file_delete", "copy_file", "move_file"]:
                                archivos_escritos = True
                                break
                    if archivos_escritos:
                        break

                for tc in respuesta.tool_calls:
                    if tc.get("name") in ["write_file", "file_delete", "copy_file", "move_file"]:
                        archivos_escritos = True
                        break

                if not archivos_escritos:
                    msg = "Error: No has modificado ni creado ningún archivo usando la herramienta 'write_file'. Debes escribir el código correspondiente antes de llamar a 'CodigoCompletado'."
                    return Command(
                        update={
                            "messages": [respuesta, HumanMessage(content=msg)],
                            "loop_counter": loop_counter
                        },
                        goto="agente_codificador"
                    )

                resumen = tool_call["args"].get("resumen_cambios", "Código completado")
                tool_messages = [
                    ToolMessage(
                        tool_call_id=tc["id"],
                        content="Fase de desarrollo concluida. Enviando a revisión de código." if tc["name"] == "CodigoCompletado" else "Operación de archivo completada",
                    )
                    for tc in respuesta.tool_calls
                ]
                
                return Command(
                    update={
                        "codigo_escrito": resumen,
                        "errores_terminal": "",
                        "messages": [respuesta] + tool_messages,
                        "loop_counter": 0
                    },
                    goto="agente_revisor"
                )
        
        return Command(
            update={
                "messages": [respuesta],
                "loop_counter": loop_counter
            },
            goto="nodo_herramientas_codificador"
        )
    else:
        msg = "Debes llamar a las herramientas de edición de archivos ('write_file', etc.) para implementar el código, o llamar a 'CodigoCompletado' si ya terminaste de escribir los archivos."
        return Command(
            update={
                "messages": [respuesta, HumanMessage(content=msg)],
                "loop_counter": loop_counter
            },
            goto="agente_codificador"
        )


def nodo_herramientas_codificador(state: ProjectState, config: RunnableConfig):
    """
    Ejecuta las herramientas de edición de archivos utilizando ToolNode de LangGraph.
    """
    directorio = state.get("directorio_proyecto", "./")
    herramientas = _get_tools(directorio)
    nodo = ToolNode(herramientas)
    return nodo.invoke(state, config=config)
