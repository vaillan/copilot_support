# MiEquipoLangGraph - Servidor MCP

![LangGraph](https://img.shields.io/badge/LangGraph-000000?style=for-the-badge&logo=langchain&logoColor=white)
![FastMCP](https://img.shields.io/badge/FastMCP-005571?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

## 📋 Descripción General

**MiEquipoLangGraph** es un servidor compatible con el [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) que permite delegar tareas de programación complejas a un equipo de agentes autónomos orquestados con [LangGraph](https://www.langchain.com/langgraph). 

El sistema utiliza una arquitectura de agentes especializados para planificar, ejecutar y revisar cambios en el código de manera iterativa, asegurando que las soluciones propuestas sean funcionales, seguras y sigan estrictamente los requisitos del usuario.

## ✨ Características Principales

- **🤖 Arquitectura de Agentes Especializados**: Orquestación colaborativa de tres agentes (Planificador, Codificador y Revisor) con roles bien definidos.
- **🔌 Integración MCP**: Expone una herramienta (`delegar_tarea_a_equipo_ia`) directamente consumible por clientes MCP como Claude Desktop, Roo-Code, Cursor o Windsurf.
- **⚙️ Automatización End-to-End**: El equipo planifica la arquitectura, escribe el código fuente, y valida los errores de ejecución automáticamente.
- **👨‍💻 Human-in-the-loop (Aprobación Manual)**: Implementa pausas de ejecución (interruptions) que permiten al desarrollador revisar y aprobar el plan de desarrollo propuesto por el Arquitecto antes de escribir código.
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

## 🚀 Requisitos Previos

- Python 3.10 o superior.
- Clave de API válida para un modelo fundacional (por defecto, Google Gemini).
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
   Crea un archivo `.env` en la raíz del proyecto basándote en un posible archivo `.env.example`, o configurando al menos:
   ```env
   GEMINI_API_KEY="tu_clave_api_aqui"
   # Configuraciones opcionales:
   # LLM_MODEL="gemini-3.1-pro-preview"
   ```

## 🔌 Uso como Servidor MCP

El servidor se comunica a través del transporte `stdio` (entrada/salida estándar). Para ejecutarlo de forma aislada:

```bash
python mcp_server.py
```

### Configuración en Clientes MCP (Ej. Claude Desktop o Roo-Code)

Para integrar este servidor en tu cliente MCP favorito, debes añadir la siguiente configuración en tu archivo de configuración (`claude_desktop_config.json` o la configuración de servidores de la extensión):

```json
{
	"mcpServers": {
		"MiEquipoLangGraph": {
			"command": "/home/valentin-ortiz/dev/copilot_support/.venv/bin/python",
			"args": [
				"/home/valentin-ortiz/dev/copilot_support/mcp_server.py"
			],
			"env": {
				"LLM_API_KEY": "tu_api_key",
				"LLM_MODEL": "gemini-3.1-pro-preview",
				"LLM_PROVIDER": "google"
			},
			"alwaysAllow": [
				"delegar_tarea_a_equipo_ia"
			],
			"timeout": 900
		}
	}
}
```
*Asegúrate de reemplazar `/ruta/absoluta/al/proyecto/` con la ruta real en tu sistema.*

## 🧰 Herramientas MCP Expuestas

### `delegar_tarea_a_equipo_ia`
Invoca al equipo de agentes LangGraph para resolver un problema de programación o crear una nueva característica.

**Argumentos**:
- `instruccion` *(string, requerido)*: Descripción detallada de la tarea a realizar (ej. "Crea un sistema de autenticación con JWT y base de datos SQLite").
- `directorio_proyecto` *(string, requerido)*: Ruta absoluta de la carpeta del proyecto donde se realizarán los cambios.
- `thread_id` *(string, opcional, por defecto "1")*: Identificador de la sesión/hilo para la persistencia del grafo, útil para retomar la ejecución en el Human-in-the-loop.
- `approve` *(boolean, opcional, por defecto false)*: Bandera que, al establecerse en `True`, indica a LangGraph que el plan generado por el Arquitecto ha sido aprobado y el Programador puede comenzar a escribir código.

**Flujo de Aprobación (Human-in-the-loop)**:
1. Llamas a la herramienta con `instruccion` y `directorio_proyecto`.
2. El servidor retorna un estado pausado con el plan propuesto.
3. El usuario aprueba el plan.
4. Llamas a la herramienta nuevamente con `approve=True` y el mismo `thread_id` para continuar la ejecución.

## 📁 Estructura del Proyecto

```text
.
├── app/
│   ├── agents/                    # Nodos de LangGraph (Lógica de los agentes)
│   │   ├── agente_planificador.py # Agente Arquitecto (analiza y diseña el plan)
│   │   ├── agente_codificador.py  # Agente Programador (implementa el código)
│   │   └── agente_revisor.py      # Agente QA (ejecuta validaciones y pruebas)
│   ├── models/                    # Pydantic schemas y definición de estados
│   │   └── models.py              # Definición de ProjectState (estado global)
│   ├── prompts/                   # Instrucciones base de los agentes (System Prompts)
│   │   ├── planificador_prompt.md 
│   │   ├── codificador_prompt.md  
│   │   └── revisor_prompt.md      
│   ├── settings/                  # Configuración de entorno
│   │   └── settings.py            
│   ├── utils/                     # Herramientas de soporte y filesystem
│   │   └── files.py               
│   └── main.py                    # Ensamblaje y compilación del StateGraph
├── mcp_server.py                  # Punto de entrada FastMCP
├── requirements.txt               # Dependencias del proyecto
└── README.md                      # Esta documentación
```

## 🏗️ Extensibilidad

El diseño modular permite escalar fácilmente las capacidades del equipo:
- **Nuevos Agentes**: Puedes agregar nuevos nodos a `app/main.py` (ej. `Agente_Documentador` o `Agente_Despliegue`).
- **Nuevas Herramientas**: Las funciones de `app/utils/` pueden registrarse como nuevas herramientas disponibles para el Codificador o Revisor.
- **Soporte Multi-Modelo**: Adaptando `app/settings/settings.py` para instanciar diferentes LLMs de LangChain según la conveniencia de cada agente.
