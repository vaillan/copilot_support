import os
from langgraph.graph import END
from langgraph.types import Command
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.tools import tool
from app.models.models import ProjectState
from app.utils.files import File
from app.settings.settings import Settings

settings = Settings()
fileSystem = File(directory="prompts")

@tool
def finalizar_documentacion(resumen: str) -> str:
    """
    Llama a esta herramienta EXCLUSIVAMENTE cuando hayas terminado de documentar el código.
    Describe brevemente qué archivos de documentación se crearon o modificaron.
    """
    return f"Documentación finalizada: {resumen}"

def agente_documentador(state: ProjectState) -> Command:
    """
    Analiza el código final y genera la documentación necesaria.
    """
    directorio_base = state.get("directorio_proyecto", "./")
    directorio = os.path.abspath(directorio_base)
    
    # 1. Configuramos las herramientas de archivos (lectura y escritura)
    toolkit_archivos = FileManagementToolkit(root_dir=directorio)
    herramientas_archivos = [
        t for t in toolkit_archivos.get_tools() 
        if t.name in ["read_file", "write_file", "list_directory"]
    ]
    
    # Unimos las herramientas
    herramientas_documentador = herramientas_archivos + [finalizar_documentacion]
    
    # 2. Configuramos el LLM
    from app.settings.settings import get_llm
    llm = get_llm(temperature=0.2)
    llm_con_herramientas = llm.bind_tools(herramientas_documentador)
    
    # 3. Construimos el Prompt del Sistema
    prompt_raw = fileSystem.get_file_content(file_name="documentador_prompt.md")
    prompt_sistema = prompt_raw.format(directorio=directorio)
    
    # Preparamos los mensajes
    mensajes = [SystemMessage(content=prompt_sistema)] + state["messages"]
    
    # 4. Invocamos al modelo
    respuesta = llm_con_herramientas.invoke(mensajes)
    
    if respuesta.tool_calls:
        nombres_tools = [tc["name"] for tc in respuesta.tool_calls]
        
        # Si el agente intenta finalizar pero también usa otras herramientas, prioritizamos las otras herramientas
        if "finalizar_documentacion" in nombres_tools and len(nombres_tools) > 1:
            # Quitamos el tool_call de finalizar para que no cause problemas y forzamos ejecución de las otras
            # O simplemente dejamos que el nodo de herramientas lo maneje (pero ese nodo no tiene 'finalizar_documentacion')
            pass 

        # Si el único tool call es finalizar_documentacion, terminamos
        if len(nombres_tools) == 1 and nombres_tools[0] == "finalizar_documentacion":
            return Command(
                update={"messages": [respuesta]},
                goto=END
            )
        
        # Si está usando herramientas (incluyendo mezcla), vamos al nodo de herramientas
        return Command(
            update={"messages": [respuesta]},
            goto="nodo_herramientas_documentador"
        )
        
    else:
        # Forzamos al agente a seguir si responde solo con texto
        return Command(
            update={
                "messages": [respuesta]
            },
            goto="agente_documentador"
        )

def nodo_herramientas_documentador(state: ProjectState) -> Command:
    directorio_base = state.get("directorio_proyecto", "./")
    directorio = os.path.abspath(directorio_base)
    
    toolkit = FileManagementToolkit(root_dir=directorio)
    herramientas_archivos = {t.name: t for t in toolkit.get_tools() if t.name in ["read_file", "write_file", "list_directory"]}
    
    # Agregamos la herramienta de finalizar al diccionario para que pueda ser "ejecutada" si se coló
    herramientas = {**herramientas_archivos, "finalizar_documentacion": finalizar_documentacion}
    
    ultimo_mensaje = state["messages"][-1]
    respuestas_tools = []
    
    for tool_call in ultimo_mensaje.tool_calls: # type: ignore
        nombre = tool_call["name"]
        args = tool_call["args"]
        
        print(f"[DEBUG Documentador] Ejecutando herramienta: {nombre} con argumentos: {args}")
        
        if nombre in herramientas:
            try:
                # Log específico para write_file
                if nombre == "write_file":
                    print(f"[DEBUG Documentador] Escribiendo en archivo: {args.get('file_path')}")
                
                resultado = herramientas[nombre].invoke(args)
                print(f"[DEBUG Documentador] Resultado de {nombre}: {str(resultado)[:100]}...")
            except Exception as e:
                resultado = f"Error al ejecutar la herramienta {nombre}: {str(e)}"
                print(f"[DEBUG Documentador] Error en {nombre}: {resultado}")
            
            respuestas_tools.append(ToolMessage(content=str(resultado), tool_call_id=tool_call["id"], name=nombre))
        else:
            print(f"[DEBUG Documentador] Herramienta no encontrada: {nombre}")
            
    return Command(
        update={
            "messages": respuestas_tools
        },
        goto="agente_documentador"
    )
