# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** es una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo.

### El Equipo de Agentes
1.  **🏗️ Agente Planificador (Arquitecto)**:
    - **Función**: Analiza los requerimientos del usuario y la estructura actual del proyecto.
    - **Herramientas**: Búsqueda web avanzada (SearxNG), exploración de archivos y lectura técnica.
    - **Salida**: Genera un `PlanDeAccion` estructurado que guía al resto del equipo.

2.  **💻 Agente Codificador (Programador)**:
    - **Función**: Traduce el plan de acción en código ejecutable.
    - **Herramientas**: `FileManagementToolkit` para manipulación segura de archivos (creación y edición).
    - **Autocorrección**: Recibe retroalimentación del Revisor para aplicar parches inmediatos ante fallos.

3.  **🪲 Agente Revisor (QA/Tester)**:
    - **Función**: Valida la integridad del código escrito mediante pruebas de ejecución.
    - **Herramientas**: `ShellTool` para ejecución de comandos en terminal y verificación de sintaxis o tests.
    - **Bucle de Feedback**: Si detecta errores, devuelve el estado al Codificador con un reporte detallado.

## 🔌 Integración con MCP (Model Context Protocol)

AIDevTeam está diseñado para funcionar como un servidor **FastMCP**. Esto permite que el sistema se integre perfectamente con editores de código y clientes compatibles, exponiendo la capacidad del equipo de agentes como una herramienta estándar.

- **Servidor**: `mcp_server.py`
- **Herramienta Principal**: `delegar_tarea_a_equipo_ia`
- **Gestión de Sesión**: Utiliza un sistema de persistencia basado en `MemorySaver`. Cada directorio de proyecto genera un `thread_id` único mediante un hash MD5, permitiendo que los agentes mantengan el contexto histórico de cada proyecto por separado.

## 📁 Estructura del Proyecto

```text
.
├── app/
│   ├── agents/             # Definiciones lógicas y nodos de agentes
│   │   ├── agente_planificador.py
│   │   ├── agente_codificador.py
│   │   └── agente_revisor.py
│   ├── models/             # Esquemas Pydantic y configuración del Grafo
│   │   ├── llm_factory.py  # Fábrica multi-proveedor de LLM
│   │   └── models.py       # Estado global (ProjectState)
│   ├── prompts/            # Prompts del sistema en Markdown
│   ├── settings/           # Configuración dinámica y variables de entorno
│   ├── utils/              # Utilidades para manejo de archivos
│   └── main.py             # Definición y compilación del Grafo de LangGraph
├── mcp_server.py           # Punto de entrada para el servidor MCP
├── requirements.txt        # Dependencias core
└── .env                    # Configuración de credenciales
```

## 🛠️ Instalación y Configuración

### 1. Requisitos Previos
- Python 3.10 o superior.
- Instalación de [SearxNG](https://github.com/searxng/searxng) (opcional, para búsqueda web).

### 2. Configuración del Entorno
Clona el repositorio y configura el entorno virtual:
```bash
git clone <repository-url>
cd copilot_support
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Variables de Entorno (.env)
Crea un archivo `.env` en la raíz con la siguiente configuración:
```env
# Proveedor: google, openai, anthropic, etc.
LLM_PROVIDER=google
LLM_MODEL=gemini-1.5-pro
LLM_API_KEY=tu_api_key_aqui
```

### 4. Configuración del Cliente MCP (ej. Roo Code, Claude Desktop)
Para integrar AIDevTeam como un servidor MCP en tu cliente preferido, agrega la siguiente configuración en el archivo de ajustes de MCP (`mcp_settings.json` o similar):

```json
{
	"mcpServers": {
		"AIDevTeam": {
			"command": "/home/valentin-ortiz/dev/copilot_support/.venv/bin/python",
			"args": [
				"/home/valentin-ortiz/dev/copilot_support/mcp_server.py"
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

### Ejecutar desde un Cliente MCP
Una vez conectado, puedes llamar a la herramienta:
```json
{
  "name": "delegar_tarea_a_equipo_ia",
  "arguments": {
    "instruccion": "Crea una función de suma en un nuevo archivo math_utils.py",
    "directorio_proyecto": "/ruta/absoluta/a/tu/proyecto"
  }
}
```

## 🛡️ Seguridad
El sistema utiliza un `root_dir` en el `FileManagementToolkit` para restringir las operaciones de archivos al directorio especificado en la instrucción inicial, evitando accesos no autorizados fuera del área de trabajo del proyecto.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
