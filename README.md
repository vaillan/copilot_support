# AI DevTeam: Servidor MCP de Agentes de Desarrollo Autónomo

![LangGraph](https://img.shields.io/badge/LangGraph-000000?style=for-the-badge&logo=langchain&logoColor=white)
![FastMCP](https://img.shields.io/badge/FastMCP-005571?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

## 📋 Descripción General

**AI DevTeam** es un servidor compatible con el [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) que permite delegar tareas de programación complejas a un equipo de agentes autónomos orquestados con [LangGraph](https://www.langchain.com/langgraph). 

El sistema utiliza una arquitectura de agentes especializados que emplean la API funcional de LangGraph (`Command`, `goto`, `update`) para planificar, ejecutar, revisar y documentar cambios en el código de manera iterativa.

## ✨ Características Principales

- **🤖 Arquitectura de Agentes Especializados**: Orquestación colaborativa de cuatro agentes (Planificador, Codificador, Revisor y Documentador).
- **🔌 Integración MCP**: Expone una herramienta (`delegar_tarea_a_equipo_ia`) consumible por clientes MCP como Claude Desktop, Roo-Code, Cursor o Windsurf.
- **⚙️ Automatización End-to-End**: Planificación de arquitectura, implementación de código, validación técnica y generación de documentación.
- **👨‍💻 Human-in-the-loop (Aprobación Manual)**: Pausas de ejecución (interruptions) para revisar y aprobar el plan de desarrollo antes de la codificación.
- **💾 Persistencia de Estado**: Base de datos SQLite (`memoria_agentes.db`) para mantener el estado de las conversaciones y tareas.
- **🔍 Investigación Avanzada**: El planificador puede realizar búsquedas web mediante SearxNG para obtener documentación técnica actualizada.
- **🧠 Soporte de Modelos con Razonamiento**: Configuración optimizada para modelos de "Thinking" como Gemini 2.0 Flash Thinking, Claude 3.7 (thinking mode) y OpenAI o1/o3-mini.

## 🧠 Flujo de Trabajo de los Agentes

El sistema utiliza un grafo de estados dinámico gestionado mediante nodos funcionales:

1. **🏗️ Agente Planificador (Arquitecto)**:
   - Analiza la instrucción y explora el proyecto.
   - Realiza búsquedas web si es necesario (SearxNG).
   - Diseña un plan de acción estructurado.
   - *Pausa la ejecución esperando aprobación.*
2. **💻 Agente Codificador (Programador)**:
   - Implementa los cambios basados en el plan aprobado.
   - Utiliza herramientas de gestión de archivos (`write_file`, `edit_file`, etc.).
3. **🕵️ Agente Revisor (QA)**:
   - Valida la implementación ejecutando comandos en una terminal real.
   - Si detecta fallos, devuelve el flujo al Codificador con retroalimentación detallada.
4. **📝 Agente Documentador**:
   - Analiza los cambios finales.
   - Actualiza archivos de documentación (`README.md`, `docs/`) para reflejar las novedades.

## 🚀 Requisitos Previos

- Python 3.10 o superior.
- Instancia de SearxNG (opcional, para búsqueda web).
- Clave de API para el modelo LLM elegido.

## 🛠️ Instalación y Configuración

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/tu_usuario/copilot_support.git
   cd copilot_support
   ```

2. **Configurar el entorno**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Variables de Entorno (.env)**:
   ```env
   LLM_API_KEY="tu_clave_api_aqui"
   LLM_PROVIDER="google-genai" # google-genai, openai, anthropic, open-router
   LLM_MODEL="gemini-2.0-flash" 
   LLM_THINKING="false" # true para habilitar modo thinking (si el modelo lo soporta)
   LLM_THINKING_BUDGET="2048"
   SEARXNG_HOST="http://localhost:8888" # Host de tu instancia SearxNG
   ```

## 🔌 Uso como Servidor MCP

Añade esta configuración a tu cliente MCP (ej. `claude_desktop_config.json` o configuración de Roo-Code):

```json
{
  "mcpServers": {
    "AIDevTeam": {
      "command": "/ruta/a/tu/venv/bin/python",
      "args": ["/ruta/a/tu/proyecto/mcp_server.py"],
      "env": {
        "LLM_API_KEY": "tu_api_key",
        "LLM_MODEL": "gemini-2.0-flash",
        "LLM_PROVIDER": "google-genai"
      },
      "timeout": 900
    }
  }
}
```

## 📁 Estructura del Proyecto

```text
.
├── app/
│   ├── agents/            # Lógica de agentes (nodos funcionales)
│   ├── models/            # Esquemas Pydantic y ProjectState
│   ├── prompts/           # Plantillas de sistema para cada rol
│   ├── settings/          # Configuración global y factory de LLM
│   ├── utils/             # Factoría de agentes y gestión de archivos
│   └── main.py            # Orquestación del StateGraph
├── docs/                  # Documentación técnica detallada
├── mcp_server.py          # Punto de entrada FastMCP
├── requirements.txt       # Dependencias del proyecto
└── README.md              # Guía de inicio rápido
```

## 🏗️ Extensibilidad

El sistema es altamente modular. Puedes añadir nuevos proveedores en `app/settings/settings.py` o modificar el comportamiento de los agentes ajustando sus prompts en `app/prompts/`.
