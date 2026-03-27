# AI DevTeam: Servidor MCP de Agentes de Desarrollo Autónomo

![LangGraph](https://img.shields.io/badge/LangGraph-000000?style=for-the-badge&logo=langchain&logoColor=white)
![FastMCP](https://img.shields.io/badge/FastMCP-005571?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

## 📋 Descripción General

**AI DevTeam** es un servidor compatible con el [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) que permite delegar tareas de programación complejas a un equipo de agentes autónomos orquestados con [LangGraph](https://www.langchain.com/langgraph). 

El sistema utiliza una arquitectura de agentes especializados para planificar, ejecutar, revisar y documentar cambios en el código de manera iterativa, asegurando que las soluciones propuestas sean funcionales, seguras y sigan estrictamente los requisitos del usuario.

## ✨ Características Principales

- **🤖 Arquitectura de Agentes Especializados**: Orquestación colaborativa de cuatro agentes (Planificador, Codificador, Revisor y Documentador) con roles bien definidos.
- **🔌 Integración MCP**: Expone una herramienta (`delegar_tarea_a_equipo_ia`) directamente consumible por clientes MCP como Claude Desktop, Roo-Code, Cursor o Windsurf.
- **⚙️ Automatización End-to-End**: El equipo planifica la arquitectura, escribe el código fuente, valida errores y genera documentación automáticamente.
- **👨‍💻 Human-in-the-loop (Aprobación Manual)**: Implementa pausas de ejecución (interruptions) que permiten al desarrollador revisar y aprobar el plan de desarrollo propuesto por el Arquitecto antes de escribir código.
- **💾 Persistencia de Estado**: Utiliza una base de datos SQLite (`memoria_agentes.db`) para mantener el estado de las conversaciones y tareas, permitiendo reanudar procesos pausados.
- **📂 Contexto del Proyecto Activo**: Diseñado para operar dinámicamente sobre el sistema de archivos de cualquier directorio de proyecto especificado.

## 🧠 Flujo de Trabajo de los Agentes

El sistema utiliza un grafo de estados (`StateGraph` de LangGraph) que gestiona el ciclo de vida de la tarea a través de los siguientes nodos:

1. **🏗️ Agente Planificador (Arquitecto)**:
   - Analiza la instrucción inicial del usuario.
   - Explora el directorio del proyecto para entender el contexto.
   - Diseña un plan de acción detallado paso a paso.
   - *Pausa la ejecución esperando aprobación (Human-in-the-loop).*
2. **💻 Agente Codificador (Programador)**:
   - Toma el plan aprobado como referencia.
   - Implementa los cambios directamente en el código base utilizando herramientas de sistema de archivos.
3. **🕵️ Agente Revisor (QA)**:
   - Revisa el código implementado por el Programador.
   - Ejecuta validaciones (linters, tests, ejecución de comandos en terminal).
   - Si encuentra fallos o discrepancias, genera retroalimentación y devuelve el control al Codificador para que corrija los errores (Ciclo Iterativo).
4. **📝 Agente Documentador**:
   - Una vez que el código es validado, analiza los cambios realizados.
   - Actualiza archivos de documentación (como README o docs internos) para reflejar las nuevas funcionalidades.

## 🚀 Requisitos Previos

- Python 3.10 o superior.
- Clave de API válida para un modelo fundacional (Google Gemini, OpenAI o Anthropic).
- Dependencias de Python instaladas (ver `requirements.txt`).

## 🛠️ Instalación y Configuración

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/tu_usuario/copilot_support.git
   cd copilot_support
   ```

2. **Crear y activar un entorno virtual**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```

3. **Instalar las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**:
   Crea un archivo `.env` en la raíz del proyecto configurando:
   ```env
   LLM_API_KEY="tu_clave_api_aqui"
   LLM_MODEL="gemini-2.0-flash" # o tu modelo preferido
   LLM_PROVIDER="google-genai" # opciones: google-genai, openai, anthropic
   ```

## 🔌 Uso como Servidor MCP

El servidor se comunica a través del transporte `stdio` (entrada/salida estándar). Para ejecutarlo de forma aislada:

```bash
python mcp_server.py
```

### Configuración en Clientes MCP (Ej. Claude Desktop o Roo-Code)

Añade la siguiente configuración en tu archivo de configuración de cliente MCP:

```json
{
	"mcpServers": {
		"AIDevTeam": {
			"command": "/ruta/a/tu/venv/bin/python",
			"args": [
				"/ruta/a/tu/proyecto/mcp_server.py"
			],
			"env": {
				"LLM_API_KEY": "tu_api_key",
				"LLM_MODEL": "gemini-2.0-flash",
				"LLM_PROVIDER": "google-genai"
			},
			"alwaysAllow": [
				"delegar_tarea_a_equipo_ia"
			],
			"timeout": 900
		}
	}
}
```

## 🧰 Herramientas MCP Expuestas

### `delegar_tarea_a_equipo_ia`
Invoca al equipo de agentes LangGraph para resolver un problema de programación o crear una nueva característica.

**Argumentos**:
- `instruccion` *(string, requerido)*: Descripción de la tarea.
- `directorio_proyecto` *(string, requerido)*: Ruta absoluta del proyecto.
- `thread_id` *(string, opcional)*: ID para la persistencia de la sesión.
- `approve` *(boolean, opcional)*: `True` para aprobar el plan del Arquitecto.

**Flujo de Aprobación**:
1. El Arquitecto propone un plan y el proceso se pausa.
2. El usuario revisa el plan.
3. El usuario vuelve a llamar a la herramienta con `approve=True` y el mismo `thread_id`.

## 📁 Estructura del Proyecto

```text
.
├── app/
│   ├── agents/                    # Nodos de LangGraph (Lógica de los agentes)
│   │   ├── agente_planificador.py # Agente Arquitecto
│   │   ├── agente_codificador.py  # Agente Programador
│   │   ├── agente_revisor.py      # Agente QA
│   │   └── agente_documentador.py # Agente Documentador (Nuevo ✨)
│   ├── models/                    # Pydantic schemas y definición de estados
│   │   └── models.py              # Definición de ProjectState
│   ├── prompts/                   # System Prompts para cada agente
│   │   ├── planificador_prompt.md 
│   │   ├── codificador_prompt.md  
│   │   ├── revisor_prompt.md      
│   │   └── documentador_prompt.md 
│   ├── settings/                  # Configuración de entorno y LLM
│   │   └── settings.py            
│   ├── utils/                     # Herramientas de soporte
│   │   └── files.py               
│   └── main.py                    # Orquestación del StateGraph
├── mcp_server.py                  # Punto de entrada FastMCP
├── memoria_agentes.db             # Persistencia SQLite (Autogenerado)
├── requirements.txt               # Dependencias
└── README.md                      # Esta documentación
```

## 🏗️ Extensibilidad

El diseño modular permite:
- **Nuevos Agentes**: Fácil adición de nodos al flujo de LangGraph.
- **Persistencia Flexible**: El sistema ya integra `SqliteSaver` para historial de tareas.
- **Soporte Multi-Modelo**: Compatible con Google, OpenAI y Anthropic mediante LangChain.
