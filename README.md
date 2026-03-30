# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** es una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados (`StateGraph`) utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo.

### Gestión de Estado y Enrutamiento Dinámico
- **Estado del Proyecto (`ProjectState`)**: Hereda de `MessagesState` de LangGraph, lo que permite la gestión automática del historial de mensajes (`messages`) entre los agentes y el usuario, además de mantener variables de estado globales como el plan de acción y los errores de terminal.
- **Control de Flujo (`Command`)**: Se utiliza el objeto `Command` de LangGraph para el enrutamiento dinámico. Esto permite a cada agente decidir de manera autónoma cuál es el siguiente nodo a ejecutar (por ejemplo, ir a su nodo de herramientas, avanzar al siguiente agente o terminar el proceso) y actualizar el estado global de forma explícita.
- **Aristas Explícitas**: El grafo utiliza aristas explícitas para conectar los nodos de herramientas de vuelta a sus agentes correspondientes, asegurando un flujo de ejecución predecible y robusto.

### ⏸️ Configuración de Interrupciones (HITL)
El sistema utiliza la funcionalidad `interrupt_before` de LangGraph para implementar un flujo de **Human-in-the-Loop (HITL)**. El grafo está configurado para pausar la ejecución antes de nodos críticos (como el `agente_codificador` o el `agente_revisor`), permitiendo al usuario inspeccionar el estado, revisar los cambios propuestos y aprobar la continuación del proceso.

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
├── tests/                  # Suite de pruebas unitarias
└── README.md               # Documentación
```

### Descripción de Módulos Clave
- **`app/agents/`**: Contiene la lógica individual de cada agente (Planificador, Codificador, Revisor). Refactorizados para usar `ToolNode` y `ChatPromptTemplate`.
- **`app/models/`**: Define las estructuras de datos fundamentales y la fábrica de LLMs (`llm_factory.py`), que permite una inicialización dinámica y agnóstica de proveedores.
- **`app/main.py`**: Orquestador principal. Define el `StateGraph` incluyendo la configuración de `interrupt_before` y la persistencia con `MemorySaver`.

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
Crea un archivo `.env` en la raíz:
```env
LLM_PROVIDER=google
LLM_MODEL=gemini-1.5-pro
LLM_API_KEY=tu_api_key_aqui
```

## 🔌 Integración con MCP
AIDevTeam funciona como un servidor **FastMCP**. La herramienta principal `delegar_tarea_a_equipo_ia` permite invocar el flujo de trabajo desde editores compatibles.

## 🧪 Pruebas
Ejecuta la suite de pruebas con:
```bash
./run_tests.sh
```

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
