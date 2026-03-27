# AIDevTeam - Equipo de Agentes de Desarrollo IA

## Descripción
**AIDevTeam** es un sistema de agentes autónomos diseñado para automatizar tareas de desarrollo de software. Utiliza la arquitectura de **LangGraph** para orquestar un flujo de trabajo entre tres agentes especializados: un **Planificador** (Arquitecto), un **Codificador** (Programador) y un **Revisor** (QA). 

El sistema está diseñado para integrarse como un servidor **MCP (Model Context Protocol)**, lo que permite delegar tareas de programación complejas directamente desde editores de código compatibles que actúen como clientes MCP.

## Características
- **Arquitectura Multi-Agente**: Orquestación robusta de agentes con roles definidos para asegurar la calidad y coherencia del código generado.
- **Servidor MCP Nativo**: Implementado con `FastMCP`, exponiendo herramientas de desarrollo directamente a LLMs.
- **Flujo de Trabajo Inteligente**:
  - **Agente Planificador**: Analiza los requerimientos del usuario y diseña una estrategia detallada de implementación.
  - **Agente Codificador**: Implementa la lógica de negocio y las funcionalidades siguiendo el plan diseñado.
  - **Agente Revisor**: Valida el código escrito, detecta posibles errores y asegura el cumplimiento de las especificaciones.
- **Integración con Google Gemini**: Potenciado por los modelos de lenguaje de última generación de Google para un razonamiento avanzado.

## Estructura del Proyecto
```text
.
├── app/
│   ├── agents/             # Lógica de los agentes (Planificador, Codificador, Revisor)
│   ├── models/             # Fábrica de LLMs y definición del estado del grafo
│   ├── prompts/            # Prompts del sistema en formato Markdown para cada agente
│   ├── settings/           # Configuraciones globales y variables de entorno
│   ├── utils/              # Funciones de utilidad para manejo de archivos y procesos
│   └── main.py             # Definición y compilación del grafo de LangGraph
├── mcp_server.py           # Servidor MCP que expone el equipo de IA como herramienta
├── requirements.txt        # Dependencias del proyecto (LangChain, LangGraph, MCP, etc.)
└── .env                    # Configuración de claves de API (requerido: GEMINI_API_KEY)
```

## Requisitos Previos
- Python 3.10 o superior.
- Una clave de API de Google Gemini (`GEMINI_API_KEY`).

## Instalación
1.  **Clona el repositorio**:
    ```bash
    git clone <url-del-repositorio>
    cd copilot_support
    ```

2.  **Crea y activa un entorno virtual**:
    ```bash
    python -m venv .venv
    # Linux/macOS:
    source .venv/bin/activate
    # Windows:
    .venv\Scripts\activate
    ```

3.  **Instala las dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configura las variables de entorno**:
    Crea un archivo `.env` en la raíz del proyecto con el siguiente contenido:
    ```env
    GEMINI_API_KEY=tu_clave_de_api_aqui
    ```

## Uso
### Ejecución del Servidor MCP
Para iniciar el servidor MCP y que esté disponible para clientes como Claude Desktop u otros editores compatibles:
```bash
python mcp_server.py
```

### Herramienta Principal: `delegar_tarea_a_equipo_ia`
El servidor expone una herramienta principal para la delegación de tareas:
- **`instruccion`**: La descripción detallada de lo que deseas que el equipo de IA construya o modifique.
- **`directorio_proyecto`**: La ruta absoluta donde el equipo debe trabajar.

El sistema devolverá un resumen de los cambios realizados y el estado final de las validaciones realizadas por el agente Revisor.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
