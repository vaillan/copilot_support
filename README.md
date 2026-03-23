# MiEquipoLangGraph - Servidor MCP

## Descripción

**MiEquipoLangGraph** es un servidor compatible con el [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) que permite delegar tareas de programación complejas a un equipo de agentes autónomos orquestados con [LangGraph](https://www.langchain.com/langgraph). 

El sistema utiliza una arquitectura de agentes especializados para planificar, ejecutar y revisar cambios en el código de manera iterativa, asegurando que las soluciones propuestas sean funcionales y sigan los requisitos del usuario.

## Características

- **Arquitectura de Agentes**: Orquestación de tres agentes especializados (Planificador, Codificador y Revisor).
- **Integración MCP**: Expone una herramienta (`delegar_tarea_a_equipo_ia`) que puede ser consumida por clientes MCP como Claude Desktop o Roo-Code.
- **Automatización Completa**: El equipo es capaz de planificar la solución, escribir el código y validar los errores de ejecución automáticamente.
- **Contexto del Proyecto**: Diseñado para operar directamente sobre el sistema de archivos del proyecto especificado.

## Cómo Funciona

El sistema utiliza un grafo de estados (`StateGraph`) que gestiona el flujo de trabajo entre los siguientes nodos:

1.  **Agente Planificador (Arquitecto)**: Analiza la instrucción del usuario y diseña un plan de acción detallado.
2.  **Agente Codificador (Programador)**: Implementa los cambios en el código siguiendo el plan establecido. Utiliza herramientas para interactuar con el sistema de archivos.
3.  **Agente Revisor (QA)**: Ejecuta el código o realiza pruebas para identificar errores. Si encuentra fallos, el ciclo se repite para corregirlos.

## Requisitos Previos

- Python 3.10 o superior.
- Clave de API de Gemini (u otro modelo configurado en el entorno).
- Dependencias instaladas (ver `requirements.txt`).

## Instalación

1.  Clona el repositorio:
    ```bash
    git clone https://github.com/tu_usuario/copilot_support.git
    cd copilot_support
    ```

2.  Crea un entorno virtual e instálalo:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # En Windows: .venv\Scripts\activate
    ```

3.  Instala las dependencias:
    ```bash
    pip install -r requirements.txt
    ```

4.  Configura las variables de entorno en un archivo `.env`:
    ```env
    GEMINI_API_KEY="tu_clave_api_aquí"
    # Otras configuraciones opcionales (ver app/settings/settings.py)
    ```

## Uso como Servidor MCP

Para ejecutar el servidor MCP a través del transporte `stdio`, utiliza el siguiente comando:

```bash
python mcp_server.py
```

### Configuración en Claude Desktop

Añade lo siguiente a tu archivo de configuración de Claude Desktop:

```json
{
  "mcpServers": {
    "equipo-langgraph": {
      "command": "/ruta/absoluta/al/proyecto/.venv/bin/python",
      "args": ["/ruta/absoluta/al/proyecto/mcp_server.py"],
      "env": {
        "LLM_API_KEY": "tu_clave_api_aquí",
        "LLM_MODEL": "gemini-3.1-pro-preview",
        "LLM_PROVIDER": "google"
      }
    }
  }
}
```

## Definición del Servidor MCP

El servidor MCP en este proyecto se define de manera simplificada utilizando **FastMCP**, una abstracción de alto nivel que facilita la creación de servidores. Esto se realiza en el archivo `mcp_server.py`:

```python
from mcp.server.fastmcp import FastMCP

# 1. Inicialización del servidor
mcp = FastMCP("EquipoAgentesLangGraph")

# 2. Exposición de herramientas mediante decoradores
@mcp.tool()
def delegar_tarea_a_equipo_ia(instruccion: str, directorio_proyecto: str, thread_id: str = "1", approve: bool = False) -> str:
    # Lógica de la herramienta y llamada a LangGraph...
    pass

# 3. Ejecución del servidor a través de stdio
if __name__ == "__main__":
    mcp.run()
```

Esta estructura permite exponer funciones de Python regulares como herramientas MCP simplemente añadiéndoles el decorador `@mcp.tool()`, y el servidor se encarga automáticamente del ciclo de vida y la comunicación mediante la entrada/salida estándar (`stdio`).

## Herramientas Expuestas

### `delegar_tarea_a_equipo_ia`
Invoca al equipo de agentes para resolver un problema de programación.
- **Argumentos**:
  - `instruccion`: Descripción de la tarea (ej. "Crea un endpoint de login con JWT").
  - `directorio_proyecto`: Ruta absoluta de la carpeta donde se debe trabajar.

## Estructura del Proyecto

```text
.
├── app/
│   ├── agents/            # Lógica de los agentes (Planificador, Codificador, Revisor)
│   ├── models/            # Definiciones de estado (ProjectState)
│   ├── prompts/           # Prompts del sistema para cada agente
│   ├── settings/          # Gestión de configuración y variables de entorno
│   ├── utils/             # Funciones de utilidad (manejo de archivos, etc.)
│   └── main.py            # Construcción y compilación del grafo LangGraph
├── mcp_server.py          # Punto de entrada del servidor MCP (FastMCP)
├── requirements.txt       # Dependencias del proyecto
└── README.md              # Documentación principal
```

## Tecnologías Utilizadas

- **LangGraph**: Orquestación de agentes.
- **FastMCP**: Implementación del servidor MCP.
- **Pydantic**: Validación de datos y configuraciones.
- **Google Gemini**: Modelo de lenguaje principal (configurable).
