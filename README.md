# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** es una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados (`StateGraph`) utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo. Además, incorpora un sistema de **Human-in-the-Loop (HITL)** para garantizar la calidad y el control humano sobre las decisiones críticas.

### El Equipo de Agentes
1.  **🏗️ Agente Planificador (Arquitecto)**:
    - **Función**: Analiza los requerimientos del usuario y la estructura actual del proyecto.
    - **Herramientas**: Búsqueda web avanzada (`DuckDuckGoSearchAPIWrapper`), exploración de archivos y lectura técnica (`FileManagementToolkit`).
    - **Salida**: Genera un `PlanDeAccion` estructurado que guía al resto del equipo.

2.  **💻 Agente Codificador (Programador)**:
    - **Función**: Traduce el plan de acción en código ejecutable.
    - **Herramientas**: `FileManagementToolkit` para manipulación segura de archivos (creación y edición).
    - **Autocorrección**: Recibe retroalimentación del Revisor para aplicar parches inmediatos ante fallos.

3.  **🪲 Agente Revisor (QA/Tester)**:
    - **Función**: Valida la integridad del código escrito mediante pruebas de ejecución.
    - **Herramientas**: `ShellTool` para ejecución de comandos en terminal y verificación de sintaxis o tests.
    - **Bucle de Feedback**: Si detecta errores, devuelve el estado al Codificador con un reporte detallado.

### ⏸️ Flujo de Aprobación Manual (Human-in-the-Loop)
El sistema está diseñado para pausar su ejecución en momentos clave, permitiendo la intervención humana:
- **PAUSA 1 (Aprobación del Plan)**: Tras la generación del plan por el Arquitecto, el sistema se detiene para que el usuario valide el enfoque técnico antes de escribir código.
- **PAUSA 2 (Revisión de Código)**: Una vez que el Programador escribe los archivos, el sistema se pausará nuevamente. Esto permite al usuario revisar el *Diff* (cambios en Git) y aprobar el código antes de que el QA ejecute las pruebas.

## 📁 Estructura del Proyecto y Módulos

La estructura del proyecto está organizada de la siguiente manera:

```text
.
├── app/
│   ├── agents/             # Definiciones lógicas y nodos de agentes
│   │   ├── agente_planificador.py # Lógica del Arquitecto (análisis y planificación)
│   │   ├── agente_codificador.py  # Lógica del Programador (escritura de código)
│   │   ├── agente_revisor.py      # Lógica del QA (pruebas y validación)
│   │   └── __init__.py
│   ├── models/             # Esquemas de datos y configuración de LLMs
│   │   ├── llm_factory.py  # Fábrica multi-proveedor (Google, OpenAI, Anthropic, OpenRouter)
│   │   └── models.py       # Estado global del grafo (ProjectState)
│   ├── prompts/            # Prompts del sistema en formato Markdown
│   │   ├── planificador_prompt.md
│   │   ├── codificador_prompt.md
│   │   └── revisor_prompt.md
│   ├── settings/           # Configuración dinámica y variables de entorno
│   │   ├── settings.py     # Carga de variables desde .env (API Keys, Modelos)
│   │   └── __init__.py
│   ├── utils/              # Utilidades generales
│   │   ├── files.py        # Gestión de lectura de archivos (ej. carga de prompts)
│   │   └── __init__.py
│   └── main.py             # Definición, configuración y compilación del Grafo de LangGraph
├── mcp_server.py           # Punto de entrada para el servidor FastMCP
├── requirements.txt        # Dependencias del proyecto
├── .env                    # Configuración de credenciales (no versionado)
└── README.md               # Documentación del proyecto
```

### Propósito de los Módulos en `app/`
- **`app/agents/`**: Contiene la lógica individual de cada agente. Cada archivo define el comportamiento, las herramientas asignadas y las transiciones condicionales dentro del grafo para su respectivo rol.
- **`app/models/`**: Define las estructuras de datos fundamentales. `models.py` contiene el `ProjectState` que fluye a través del grafo, mientras que `llm_factory.py` abstrae la instanciación de modelos de lenguaje, permitiendo cambiar fácilmente entre proveedores (Google, OpenAI, Anthropic, etc.).
- **`app/prompts/`**: Almacena las instrucciones base (System Prompts) de cada agente en archivos Markdown, facilitando su edición y mantenimiento sin tocar el código Python.
- **`app/settings/`**: Centraliza la configuración de la aplicación utilizando `pydantic-settings`, cargando variables de entorno de forma segura.
- **`app/utils/`**: Proporciona clases y funciones auxiliares, como la clase `File` en `files.py` para leer los prompts desde el disco.
- **`app/main.py`**: Es el orquestador principal. Une todos los agentes y herramientas definiendo los nodos y las aristas (edges) del `StateGraph` de LangGraph. Configura la persistencia de memoria (`MemorySaver`) y los puntos de interrupción (`interrupt_before`) para el flujo de aprobación manual.

## 🛠️ Instalación y Configuración

### 1. Requisitos Previos
- Python 3.10 o superior.
- Conexión a internet para búsqueda web.

### 2. Configuración del Entorno
Clona el repositorio y configura el entorno virtual. Luego, instala las dependencias listadas en `requirements.txt`:

```bash
git clone <repository-url>
cd copilot_support
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

*Nota: `requirements.txt` incluye paquetes clave como `langchain`, `langgraph`, `fastmcp`, y conectores para múltiples proveedores de LLM (`langchain-google-genai`, `langchain-openai`, `langchain-anthropic`, `langchain-openrouter`).*

### 3. Variables de Entorno (.env)
Crea un archivo `.env` en la raíz del proyecto con la siguiente configuración:
```env
# Proveedor soportado: google, openai, anthropic, open-router
LLM_PROVIDER=google
LLM_MODEL=gemini-1.5-pro
LLM_API_KEY=tu_api_key_aqui
```

## 🔌 Integración con MCP (Model Context Protocol)

AIDevTeam está diseñado para funcionar como un servidor **FastMCP**. Esto permite que el sistema se integre perfectamente con editores de código y clientes compatibles, exponiendo la capacidad del equipo de agentes como una herramienta estándar.

- **Servidor**: `mcp_server.py`
- **Herramienta Principal**: `delegar_tarea_a_equipo_ia`
- **Gestión de Sesión**: Utiliza un sistema de persistencia basado en `MemorySaver`. Cada directorio de proyecto genera un `thread_id` único mediante un hash MD5, permitiendo que los agentes mantengan el contexto histórico de cada proyecto por separado.

### Configuración del Cliente MCP (ej. Roo Code, Claude Desktop)
Para integrar AIDevTeam como un servidor MCP en tu cliente preferido, agrega la siguiente configuración en el archivo de ajustes de MCP (`mcp_settings.json` o similar):

```json
{
	"mcpServers": {
		"AIDevTeam": {
			"command": "/ruta/absoluta/a/tu/.venv/bin/python",
			"args": [
				"/ruta/absoluta/a/tu/mcp_server.py"
			],
			"env": {
				"LLM_API_KEY": "tu_api_key",
				"LLM_MODEL": "gemini-3.1-pro-preview",
				"LLM_PROVIDER": "google",
				"FASTMCP_LOG_LEVEL": "CRITICAL"
			},
			"alwaysAllow": [
				"delegar_tarea_a_equipo_ia"
			],
			"timeout": 600
		}
	}
}
```

## 💻 Uso

### Iniciar el Servidor MCP
Ejecuta el servidor para habilitar las herramientas:
```bash
python mcp_server.py
```

### Ejecutar desde un Cliente MCP (Flujo de Trabajo)
El sistema utiliza un parámetro `approve` para gestionar las pausas de revisión. El flujo típico es el siguiente:

**1. Iniciar una nueva tarea:**
```json
{
  "name": "delegar_tarea_a_equipo_ia",
  "arguments": {
    "instruccion": "Crea una función de suma en un nuevo archivo math_utils.py",
    "directorio_proyecto": "/ruta/absoluta/a/tu/proyecto",
    "approve": false
  }
}
```
*El sistema devolverá el plan propuesto por el Arquitecto y se pausará (PAUSA 1).*

**2. Aprobar el Plan:**
Si estás de acuerdo con el plan, vuelve a llamar a la herramienta con `approve: true`:
```json
{
  "name": "delegar_tarea_a_equipo_ia",
  "arguments": {
    "instruccion": "Crea una función de suma en un nuevo archivo math_utils.py",
    "directorio_proyecto": "/ruta/absoluta/a/tu/proyecto",
    "approve": true
  }
}
```
*El Programador escribirá el código y el sistema se pausará nuevamente (PAUSA 2).*

**3. Revisar y Aprobar el Código:**
Revisa los cambios en la pestaña de Control de Código Fuente (Git) de tu editor. Si todo es correcto, llama a la herramienta nuevamente con `approve: true` para que el QA ejecute las pruebas y finalice la tarea.

## 🛡️ Seguridad
El sistema utiliza un `root_dir` en el `FileManagementToolkit` para restringir las operaciones de archivos al directorio especificado en la instrucción inicial, evitando accesos no autorizados fuera del área de trabajo del proyecto.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.-e 
## ⚡ Mejoras Técnicas Recientes (Marzo 2026)

- **Refactorización de Agentes**: Migración a `ToolNode` y `ChatPromptTemplate` de LangGraph para mayor claridad y modularidad.
- **Abstracción de LLMs**: Implementación de `init_chat_model` en `app/models/llm_factory.py`, permitiendo una inicialización dinámica y agnóstica de proveedores (Google, OpenAI, Anthropic, etc.).
- **Orquestación Mejorada**: Adición de aristas explícitas de retorno en `app/main.py` para asegurar un flujo correcto entre herramientas y agentes.
- **Actualización de Dependencias**: Sustitución de `duckduckgo-search` por `ddgs` para búsquedas web más eficientes.
