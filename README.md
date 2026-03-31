# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** es una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados (`StateGraph`) utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo.

### Gestión de Estado y Enrutamiento Dinámico
- **Estado del Proyecto (`ProjectState`)**: Hereda de `MessagesState` de LangGraph, lo que permite la gestión automática del historial de mensajes (`messages`) entre los agentes y el usuario, además de mantener variables de estado globales como el plan de acción y los errores de terminal.
- **Control de Flujo (`Command`)**: Se utiliza el objeto `Command` de LangGraph para el enrutamiento dinámico. Esto permite a cada agente decidir de manera autónoma cuál es el siguiente nodo a ejecutar (por ejemplo, ir a su nodo de herramientas, avanzar al siguiente agente o terminar el proceso) y actualizar el estado global de forma explícita.
- **Aristas Explícitas**: El grafo utiliza aristas explícitas para conectar los nodos de herramientas de vuelta a sus agentes correspondientes, asegurando un flujo de ejecución predecible y robusto.

### Estabilidad y Prevención de Bucles
Los agentes ahora gestionan explícitamente la creación de objetos `ToolMessage` y validan las respuestas del LLM para asegurar que siempre se llame a una herramienta o se finalice el proceso. Esto evita bucles infinitos y cumple con los requisitos estrictos de la API de LangGraph, garantizando un flujo de ejecución estable y predecible.

### Investigación Web Autónoma
El `agente_planificador` integra `DuckDuckGoSearchAPIWrapper` para buscar en internet documentación técnica actualizada, tutoriales y foros antes de generar el plan de acción. Esto permite al sistema tomar decisiones arquitectónicas basadas en las mejores prácticas más recientes.

### Soporte Multi-Proveedor de LLMs
El sistema cuenta con una fábrica de modelos (`llm_factory.py`) que utiliza `init_chat_model` de LangChain para inicializar dinámicamente el LLM. Esto permite soportar múltiples proveedores de manera agnóstica, incluyendo **Google**, **OpenAI**, **Anthropic** y **OpenRouter**, facilitando el cambio de modelos sin modificar el código de los agentes.

### Motor de Terminal y Feedback Loop
El `agente_revisor` (QA) incorpora un motor de terminal utilizando `ShellTool`. Esto le permite ejecutar el código generado y correr pruebas reales en el entorno del sistema operativo. Si se detectan errores de sintaxis o fallos en las pruebas, el revisor captura la salida de la terminal y retroalimenta automáticamente al `agente_codificador` para que realice las correcciones necesarias, creando un ciclo de mejora continua.

### ⏸️ Configuración de Interrupciones (HITL)
El sistema utiliza la funcionalidad `interrupt_before` de LangGraph para implementar un flujo de **Human-in-the-Loop (HITL)**. El grafo está configurado para pausar la ejecución antes de nodos críticos (como el `agente_codificador` o el `agente_revisor`), permitiendo al usuario inspeccionar el estado, revisar los cambios propuestos y aprobar la continuación del proceso.

*Nota:* La herramienta MCP `delegar_tarea_a_equipo_ia` gestiona dinámicamente este flujo mediante el parámetro `approve`. Si el usuario rechaza los cambios (`approve=False`), el sistema enruta el flujo de vuelta al agente correspondiente (Planificador o Codificador) incluyendo el feedback del usuario para su corrección.

### Persistencia de Memoria
El sistema utiliza `MemorySaver` para persistir el estado del grafo entre ejecuciones. Para gestionar múltiples proyectos, se utiliza un `thread_id` único generado mediante el hash MD5 de la ruta absoluta del directorio del proyecto:
```python
import hashlib
thread_id = hashlib.md5(directorio_proyecto.encode()).hexdigest()
```
Esto garantiza que cada proyecto mantenga su propio historial de conversación y estado de forma aislada.

## 📁 Estructura del Proyecto

La estructura del proyecto está organizada para maximizar la modularidad:

```text
.
├── app/
│   ├── agents/             # Lógica de nodos de agentes (ToolNode, ChatPromptTemplate)
│   ├── models/             # Esquemas de datos (ProjectState) y fábrica de LLMs
│   ├── prompts/            # System Prompts en formato Markdown
│   ├── settings/           # Configuración dinámica (pydantic-settings)
│   ├── utils/              # Utilidades auxiliares
│   └── main.py             # Orquestador del Grafo (StateGraph)
├── mcp_server.py           # Punto de entrada para el servidor FastMCP
├── tech-lead-export.yaml   # Perfil personalizado (Custom Mode) para Roo Code / Cline
├── tests/                  # Suite de pruebas unitarias y de integración
└── README.md               # Documentación
```

### Descripción de Módulos Clave
- **`app/agents/`**: Contiene la lógica individual de cada agente (Planificador, Codificador, Revisor). Refactorizados para usar `ToolNode` y `ChatPromptTemplate`.
- **`app/models/`**: Define las estructuras de datos fundamentales y la fábrica de LLMs (`llm_factory.py`), que permite una inicialización dinámica y agnóstica de proveedores.
- **`app/prompts/`**: Los system prompts están externalizados en archivos Markdown y se cargan dinámicamente usando la utilidad `app.utils.files.File`, facilitando su edición sin tocar código Python.
- **`app/settings/`**: Utiliza `pydantic-settings` para la validación robusta y tipada de las variables de entorno y la configuración global.
- **`app/main.py`**: Orquestador principal. Define el `StateGraph` incluyendo la configuración de `interrupt_before` y la persistencia con `MemorySaver`.
- **`tech-lead-export.yaml`**: Define un "Custom Mode" para Roo Code / Cline, estableciendo el rol de "Tech Lead" diseñado para delegar tareas al equipo de IA a través de MCP.

## 🛠️ Instalación y Configuración

### 1. Requisitos Previos
- Python 3.10 o superior.

### 2. Configuración del Entorno
```bash
git clone <repository-url>
cd copilot_support
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Variables de Entorno (.env)
Crea un archivo `.env` en la raíz. El sistema es flexible y soporta múltiples proveedores:

**Ejemplo para Google (por defecto):**
```env
LLM_PROVIDER=google
LLM_MODEL=gemini-1.5-pro
LLM_API_KEY=tu_api_key_aqui
```

**Ejemplo para OpenRouter:**
```env
LLM_PROVIDER=open-router
LLM_MODEL=anthropic/claude-3.5-sonnet
LLM_API_KEY=tu_api_key_aqui
```

**Ejemplo para OpenAI:**
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=tu_api_key_aqui
```

## 🔌 Integración con MCP

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
        "LLM_MODEL": "stepfun/step-3.5-flash",
        "LLM_PROVIDER": "open-router",
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

AIDevTeam funciona como un servidor **FastMCP**. La herramienta principal `delegar_tarea_a_equipo_ia` permite invocar el flujo de trabajo desde editores compatibles.

## 🤖 Integración con Roo Code / Cline
El proyecto incluye un archivo `tech-lead-export.yaml` que define un "Custom Mode" (Tech Lead) para Roo Code (anteriormente Cline). Este perfil está diseñado específicamente para que el asistente actúe como un Gestor de Proyectos, delegando el trabajo pesado de programación al equipo de agentes de IA a través de la herramienta MCP, en lugar de escribir código manualmente. Para utilizarlo, simplemente importa este archivo en la configuración de Custom Modes de tu extensión.

## 🧪 Pruebas
El proyecto incluye una suite exhaustiva de pruebas unitarias y de integración utilizando `pytest` y `pytest-mock`, además de análisis estático de código. Ejecuta la suite completa de pruebas y linter (`flake8`) con:
```bash
./run_tests.sh
```
El script ahora soporta la ejecución separada de pruebas End-to-End (E2E) utilizando el flag `--e2e` (ej. `./run_tests.sh --e2e`), permitiendo aislar las pruebas unitarias de las de integración.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
