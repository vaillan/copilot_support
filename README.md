# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** es una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados (`StateGraph`) utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo. Además, incorpora un sistema de **Human-in-the-Loop (HITL)** para garantizar la calidad y el control humano sobre las decisiones críticas.

### Gestión de Estado y Enrutamiento Dinámico
- **Estado del Proyecto (`ProjectState`)**: Hereda de `MessagesState` de LangGraph, lo que permite la gestión automática del historial de mensajes (`messages`) entre los agentes y el usuario, además de mantener variables de estado globales como el plan de acción y los errores de terminal.
- **Control de Flujo (`Command`)**: Se utiliza el objeto `Command` de LangGraph para el enrutamiento dinámico. Esto permite a cada agente decidir de manera autónoma cuál es el siguiente nodo a ejecutar (por ejemplo, ir a su nodo de herramientas, avanzar al siguiente agente o terminar el proceso) y actualizar el estado global de forma explícita.

### El Equipo de Agentes
La lógica de todos los agentes ha sido refactorizada utilizando `ToolNode` y `ChatPromptTemplate` de LangGraph/LangChain, lo que garantiza una mayor modularidad y un manejo claro de los prompts del sistema.

1.  **🏗️ Agente Planificador (Arquitecto)**:
    - **Función**: Analiza los requerimientos del usuario y la estructura actual del proyecto.
    - **Herramientas**: Búsqueda web avanzada (`ddgs`), exploración de archivos y lectura técnica (`FileManagementToolkit`).
    - **Salida**: Genera un `PlanDeAccion` estructurado que guía al resto del equipo.

2.  **💻 Agente Codificador (Programador)**:
    - **Función**: Traduce el plan de acción en código ejecutable.
    - **Herramientas**: `FileManagementToolkit` para manipulación segura de archivos (creación y edición).
    - **Autocorrección**: Recibe retroalimentación del Revisor para aplicar parches inmediatos ante fallos.

3.  **🪲 Agente Revisor (QA/Tester)**:
    - **Función**: Valida la integridad del código escrito mediante pruebas de ejecución.
    - **Herramientas**: `SecureShellTool` para ejecución de comandos en terminal y verificación de sintaxis o tests.
    - **Bucle de Feedback**: Si detecta errores, devuelve el estado al Codificador con un reporte detallado.

### ⏸️ Flujo de Aprobación Manual (Human-in-the-Loop)
El sistema está diseñado para pausar su ejecución en momentos clave, permitiendo la intervención humana:
- **PAUSA 1 (Aprobación del Plan)**: Tras la generación del plan por el Arquitecto, el sistema se detiene para que el usuario valide el enfoque técnico antes de escribir código.
- **PAUSA 2 (Revisión de Código)**: Una vez que el Programador escribe los archivos, el sistema se pausará nuevamente. Esto permite al usuario revisar el *Diff* (cambios en Git) y aprobar el código antes de que el QA ejecute las pruebas.

## 🌍 Soporte Multi-Lenguaje y Seguridad

AIDevTeam ha sido actualizado para soportar la ejecución y prueba de código en múltiples lenguajes de programación, incluyendo **C, C++, JavaScript (Node.js), PHP y Python**.

- **Ejecución Segura (`SecureShellTool`)**: Se ha reemplazado la herramienta estándar de terminal por una implementación personalizada (`SecureShellTool`) que incluye un **timeout estricto de 15 segundos**. Esto previene bloqueos del sistema causados por bucles infinitos en el código generado por la IA.
- **Entorno Estandarizado (`Dockerfile.env`)**: Se incluye un archivo `Dockerfile.env` que documenta las dependencias del sistema operativo necesarias (como `gcc`, `g++`, `nodejs`, `php-cli`) para garantizar que el Agente Revisor pueda compilar y ejecutar código en cualquier lenguaje soportado.

## 📁 Estructura del Proyecto y Módulos

La estructura del proyecto está organizada de la siguiente manera:

```text
.
├── app/
│   ├── agents/             # Definiciones lógicas y nodos de agentes (ToolNode, ChatPromptTemplate)
│   │   ├── agente_planificador.py # Lógica del Arquitecto (análisis y planificación)
│   │   ├── agente_codificador.py  # Lógica del Programador (escritura de código)
│   │   ├── agente_revisor.py      # Lógica del QA (pruebas y validación)
│   │   └── __init__.py
│   ├── models/             # Esquemas de datos y configuración de LLMs
│   │   ├── llm_factory.py  # Fábrica multi-proveedor con abstracción init_chat_model
│   │   └── models.py       # Estado global del grafo (ProjectState)
│   ├── prompts/            # Prompts del sistema en formato Markdown
│   │   ├── planificador_prompt.md
│   │   ├── codificador_prompt.md
│   │   └── revisor_prompt.md
│   ├── settings/           # Configuración dinámica y variables de entorno
│   │   ├── settings.py     # Carga de variables desde .env (API Keys, Modelos)
│   │   └── __init__.py
│   ├── tools/              # Herramientas personalizadas para los agentes
│   │   ├── secure_terminal.py # Implementación de SecureShellTool con timeout
│   │   └── __init__.py
│   ├── utils/              # Utilidades generales
│   │   ├── files.py        # Gestión de lectura de archivos (ej. carga de prompts)
│   │   └── __init__.py
│   └── main.py             # Orquestador del Grafo (StateGraph con aristas explícitas)
├── mcp_server.py           # Punto de entrada para el servidor FastMCP
├── Dockerfile.env          # Definición del entorno con compiladores e intérpretes
├── requirements.txt        # Dependencias del proyecto (incluye ddgs, langchain-experimental)
├── .env                    # Configuración de credenciales (no versionado)
└── README.md               # Documentación del proyecto
```

### Propósito de los Módulos en `app/`
- **`app/agents/`**: Contiene la lógica individual de cada agente. Refactorizados para usar `ToolNode` para la ejecución de herramientas y `ChatPromptTemplate` para la gestión de instrucciones.
- **`app/models/`**: Define las estructuras de datos fundamentales. `llm_factory.py` utiliza la función `init_chat_model`, permitiendo una inicialización dinámica y agnóstica de proveedores (Google, OpenAI, Anthropic, OpenRouter, etc.).
- **`app/prompts/`**: Almacena los System Prompts de cada agente en archivos Markdown para facilitar su mantenimiento.
- **`app/settings/`**: Centraliza la configuración de la aplicación utilizando `pydantic-settings`.
- **`app/tools/`**: Contiene herramientas customizadas como `SecureShellTool` para garantizar la seguridad en la ejecución de código.
- **`app/utils/`**: Proporciona utilidades auxiliares como la carga de prompts desde disco.
- **`app/main.py`**: Orquestador principal. Define el `StateGraph` de LangGraph incluyendo aristas explícitas de retorno desde las herramientas hacia los agentes, asegurando un flujo de ejecución correcto y predecible.

## 🛠️ Instalación y Configuración

### 1. Requisitos Previos
- Python 3.10 o superior.
- Conexión a internet para búsqueda web.
- (Opcional) Compiladores e intérpretes definidos en `Dockerfile.env` si se desea probar código en lenguajes distintos a Python.

### 2. Configuración del Entorno
Clona el repositorio y configura el entorno virtual:

```bash
git clone <repository-url>
cd copilot_support
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Nota sobre dependencias:** El proyecto requiere explícitamente `langchain-experimental` (incluido en `requirements.txt`) para el funcionamiento de ciertas herramientas heredadas.

### 3. Variables de Entorno (.env)
Crea un archivo `.env` en la raíz del proyecto:
```env
LLM_PROVIDER=google
LLM_MODEL=gemini-1.5-pro
LLM_API_KEY=tu_api_key_aqui
```

## 🔌 Integración con MCP (Model Context Protocol)

AIDevTeam funciona como un servidor **FastMCP**, permitiendo su integración con editores como VSCode a través de clientes compatibles.

- **Servidor**: `mcp_server.py`
- **Herramienta Principal**: `delegar_tarea_a_equipo_ia`
- **Gestión de Sesión**: Utiliza un sistema de persistencia basado en `MemorySaver`. Cada directorio genera un `thread_id` único mediante un hash MD5.

## 💻 Uso

### Iniciar el Servidor MCP
```bash
python mcp_server.py
```

### Flujo de Trabajo (HITL)
El sistema utiliza el parámetro `approve` para gestionar las pausas de revisión (Aprobación del Plan y Revisión de Código), asegurando que el usuario mantenga el control total sobre los cambios realizados.

## 🧪 Pruebas

El proyecto incluye un conjunto de pruebas unitarias para verificar el correcto funcionamiento de los agentes y su interacción con las herramientas. Las pruebas están escritas utilizando `pytest` y `pytest-mock`.

Para ejecutar todas las pruebas unitarias, puedes utilizar el script proporcionado:

```bash
./run_tests.sh
```

O ejecutar `pytest` directamente desde la raíz del proyecto:

```bash
pytest tests/
```

Para ejecutar una prueba específica, por ejemplo, la validación de aprobación del Agente Revisor:

```bash
pytest tests/test_agents.py::test_agente_revisor_approval
```

---
© 2026 AIDevTeam - Automatización Inteligente de Software.