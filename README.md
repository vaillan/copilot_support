# AIDevTeam - Ecosistema de Agentes de Desarrollo IA

**AIDevTeam** is una plataforma avanzada de agentes autónomos diseñada para automatizar el ciclo de vida del desarrollo de software (SDLC). Utilizando **LangGraph** para la orquestación y el **Model Context Protocol (MCP)** para la interoperabilidad, AIDevTeam permite delegar tareas complejas de programación a un equipo virtual de expertos en IA.

---

## 🚀 Arquitectura del Sistema

El proyecto implementa un grafo cíclico de estados (`StateGraph`) utilizando la arquitectura de agentes de LangChain, permitiendo la colaboración en tiempo real y la corrección de errores en un flujo iterativo.

### Diagrama de Flujo del Ecosistema de Agentes

A continuación se muestra el diagrama de flujo que ilustra la arquitectura de estados, los nodos de agentes, las herramientas y los puntos de interrupción con intervención humana (Human-in-the-Loop) o auto-aprobación:

```mermaid
graph TD
    classDef agent fill:#1e40af,stroke:#3b82f6,stroke-width:2px,color:#ffffff;
    classDef tool fill:#0f766e,stroke:#14b8a6,stroke-width:2px,color:#ffffff;
    classDef hitl fill:#b45309,stroke:#f59e0b,stroke-width:2px,stroke-dasharray: 5 5,color:#ffffff;
    classDef startend fill:#15803d,stroke:#22c55e,stroke-width:2px,color:#ffffff;

    START([Inicio]) --> Planificador

    subgraph Planificación
        Planificador[agente_planificador]:::agent -->|"Llama herramientas"| HerramientasPlanificador[nodo_herramientas_planificador]:::tool
        HerramientasPlanificador -->|"Retorna resultado"| Planificador
        Planificador -->|"Plan completado"| Pausa1{⏸️ Pausa 1 <br/> HITL: Aprobar Plan}:::hitl
    end

    Pausa1 -->|"Aprobar (approve=True) <br/> o Auto-apropiación"| Codificador
    Pausa1 -->|"Rechazar (approve=False)"| Planificador

    subgraph Desarrollo
        Codificador[agente_codificador]:::agent -->|"Llama herramientas"| HerramientasCodificador[nodo_herramientas_codificador]:::tool
        HerramientasCodificador -->|"Retorna código"| Codificador
        Codificador -->|"Código generado"| Pausa2{⏸️ Pausa 2 <br/> HITL: Aprobar Código}:::hitl
    end

    Pausa2 -->|"Aprobar (approve=True) <br/> o Auto-apropiación"| Revisor
    Pausa2 -->|"Rechazar (approve=False)"| Codificador

    subgraph Validación y Pruebas
        Revisor[agente_revisor]:::agent -->|"Ejecuta pruebas/terminal"| HerramientasRevisor[nodo_herramientas_revisor]:::tool
        HerramientasRevisor -->|"Resultados de test"| Revisor
        Revisor -->|"Errores detectados / max revisiones < 3"| Codificador
        Revisor -->|"Pruebas exitosas / Aprobado"| END([Fin / Completado]):::startend
    end
```

### Gestión de Estado, Enrutamiento Dinámico y Optimización de Contexto
- **Estado del Proyecto (`ProjectState`)**: Hereda de `MessagesState` de LangGraph, lo que permite la gestión automática del historial de mensajes (`messages`) entre los agentes y el usuario, además de mantener variables de estado globales como el plan de acción, los errores de terminal, y contadores de control (`loop_counter`, `revision_count`).
- **Control de Flujo (`Command`)**: Se utiliza el objeto `Command` de LangGraph para el enrutamiento dinámico. Esto permite a cada agente decidir de manera autónoma cuál es el siguiente nodo a ejecutar (por ejemplo, ir a su nodo de herramientas, avanzar al siguiente agente o terminar el proceso) y actualizar el estado global de forma explícita.
- **Aristas Explícitas**: El grafo utiliza aristas explícitas para conectar los nodos de herramientas de vuelta a sus agentes correspondientes, asegurando un flujo de ejecución predecible y robusto.
- **Resumen Automático de Contexto (`app/utils/summarization.py`)**: Para prevenir el desbordamiento de la ventana de contexto de los modelos LLM en conversaciones largas o iterativas, se implementa la función `aplicar_resumen_middleware` utilizando `SummarizationMiddleware` de LangChain. Este componente evalúa el historial de mensajes antes de cada invocación al LLM y, al superar un umbral configurable (`trigger_count=15`), resume automáticamente los mensajes más antiguos conservando los últimos mensajes recientes (`keep_count=8`), asegurando una alta eficiencia de tokens en los agentes `agente_planificador`, `agente_codificador` y `agente_revisor`.

---

## 🤖 Roles y Responsabilidades de los Agentes (`app/agents/`)

El equipo de IA está compuesto por tres agentes especializados, cada uno con un rol definido dentro del ciclo de desarrollo:

1. **Agente Planificador (`agente_planificador.py`)**:
   - Actúa como Arquitecto de Software. Analiza la solicitud del usuario, investiga librerías y documentación mediante la herramienta de búsqueda web **DuckDuckGo** (`busqueda_web_duckduckgo`) y diseña un **Plan de Acción** estructurado (`PlanDeAccion`) dividido en tareas atómicas (`archivo`, `tarea`, `requiere_test`).
   - Gestiona un contador de bucles interno (máximo 15 iteraciones) para evitar bucles infinitos de planificación.

2. **Agente Codificador (`agente_codificador.py`)**:
   - Actúa como Programador Senior. Recibe el plan de acción aprobado y desarrolla el código fuente utilizando herramientas de manipulación y creación de archivos en el sistema de ficheros.
   - Si se rechaza una propuesta o se recibe feedback correctivo, analiza los comentarios del usuario o del Revisor y realiza los ajustes necesarios en el código.
   - Gestiona un contador de bucles interno (máximo 15 iteraciones).

3. **Agente Revisor (`agente_revisor.py`)**:
   - Actúa como Ingeniero de Control de Calidad (QA) y DevOps. Ejecuta el código desarrollado y las pruebas automatizadas en la terminal utilizando la `ShellTool`.
   - **Optimización de Verificación Rápida**: Si ningún paso del plan de acción requiere pruebas (`requiere_test=False` en todos los pasos), el Revisor **aprueba automáticamente** el trabajo sin invocar comandos de shell innecesarios.
   - **Ciclo de Feedback**: Si encuentra errores de sintaxis o fallas en las pruebas, re-enruta el flujo de vuelta al Agente Codificador con el informe detallado de errores, soportando hasta un **máximo de 3 revisiones** (`revision_count >= 3`) para converger hacia una solución limpia y funcional.

---

## 🏭 Factoría de Modelos LLM (`app/models/llm_factory.py`)

El módulo `app/models/llm_factory.py` proporciona inicialización centralizada y agnóstica de los modelos de lenguaje a través de la función `init_chat_model` de LangChain.

- **Compatibilidad Multi-Proveedor**:
  - **Google (Gemini)**: Soporta modelos como `gemini-2.5-flash-lite`, `gemini-1.5-pro`, etc.
  - **OpenAI**: Soporta modelos GPT-4o, GPT-4o-mini, etc.
  - **Anthropic**: Soporta modelos Claude 3.5 Sonnet, etc.
  - **OpenRouter**: Permite acceder a una amplia gama de modelos de código abierto y cerrados (ej. `nvidia/nemotron-3-super-120b-a12b:free`, `step-3.5-flash`).
  - **Ollama / Local**: Permite la ejecución de modelos locales (ej. `gemma4:e2b`) sin depender de APIs en la nube.
- **Configuración Dinámica**: Valida y extrae credenciales, proveedores y parámetros mediante `pydantic-settings` (`app/settings/settings.py`), permitiendo alternar entre proveedores de manera transparente.

---

## 🔌 Servidor MCP (`mcp_server.py`)

Implementado utilizando **FastMCP**, el servidor expone capacidades avanzadas para la integración de agentes de IA con entornos de desarrollo y asistentes externos.

- **Herramienta Principal (`delegar_tarea_a_equipo_ia`)**:
  - Recibe la instrucción, el directorio del proyecto y parámetros de control para ejecutar o reanudar el ciclo de desarrollo autónomo.
- **Modo de Auto-Aprobación (`MCP_AUTO_APPROVE`)**:
  - Permite automatizar completamente el flujo sin pausas interactivas. Se activa globalmente mediante la variable de entorno `MCP_AUTO_APPROVE="true"` o por tarea con el parámetro `auto_approve=True`.
- **Notificaciones de Progreso y Timeouts**:
  - Informa el avance en tiempo real mediante notificaciones estructuradas con formato porcentual `[XX%]`.
  - Protege la ejecución frente a bloqueos mediante un timeout configurable (`MCP_TASK_TIMEOUT_SECONDS`, por defecto 300 segundos).
- **Inspección de Cambios (`visualizar_cambios`)**:
  - Captura y analiza el estado actual del repositorio y los diffs de código (`git diff` / `git status`) para enriquecer los informes entregados al usuario o cliente MCP.

---

## 🧪 Pruebas Automatizadas (`tests/`)

El proyecto incluye una suite completa de pruebas unitarias, de integración y End-to-End construida con `pytest` y `pytest-mock`.

### Módulos de Prueba
- `tests/test_agents.py`: Valida el comportamiento individual de los agentes (planificador, codificador y revisor).
- `tests/test_e2e.py`: Pruebas End-to-End del ciclo completo del grafo bajo escenarios simulados.
- `tests/test_files.py`: Verifica la utilidad de lectura y manipulación de archivos y system prompts.
- `tests/test_integration.py`: Comprueba la correcta interacción entre nodos, aristas y herramientas de LangGraph.
- `tests/test_llm_factory.py`: Valida la inicialización correcta de la factoría de LLMs para múltiples proveedores.
- `tests/test_mcp_server.py`: Prueba los endpoints y herramientas expuestas por el servidor FastMCP.
- `tests/test_tool_nodes.py`: Verifica la correcta ejecución de los nodos de herramientas.
- `tests/test_summarization.py`: Valida el comportamiento del middleware de resumen automático de contexto (`aplicar_resumen_middleware`), comprobando la preservación del historial por debajo del umbral (`trigger_count`) y el resumen correcto al superarlo.

### Ejecución de Pruebas y Linter
El script `./run_tests.sh` automatiza la ejecución de toda la suite de pruebas junto con el análisis estático de código utilizando `flake8`:

```bash
# Ejecutar todas las pruebas unitarias y linter
./run_tests.sh

# Ejecutar incluyendo las pruebas End-to-End (E2E)
./run_tests.sh --e2e
```

---

## 📁 Estructura del Proyecto

```text
.
├── .env                    # Variables de entorno
├── .gitignore              # Archivos ignorados por git
├── checkpoints.sqlite      # Base de datos de persistencia (MemorySaver)
├── LICENSE                 # Licencia del proyecto
├── mcp_server.py           # Punto de entrada para el servidor FastMCP
├── README.md               # Documentación completa del proyecto
├── requirements.txt        # Dependencias de Python
├── run_tests.sh            # Script automatizado de pruebas y linter
├── tech-lead-export.yaml   # Perfil personalizado "Tech Lead" para Cline
├── app/                    # Código fuente principal
│   ├── agents/             # Lógica de agentes especializados
│   │   ├── agente_codificador.py
│   │   ├── agente_planificador.py
│   │   ├── agente_revisor.py
│   │   └── __init__.py
│   ├── models/             # Esquemas de datos y fábrica de LLMs
│   │   ├── llm_factory.py
│   │   └── models.py
│   ├── prompts/            # System Prompts en Markdown
│   │   ├── codificador_prompt.md
│   │   ├── planificador_prompt.md
│   │   └── revisor_prompt.md
│   ├── settings/           # Configuración dinámica con pydantic-settings
│   │   ├── settings.py
│   │   └── __init__.py
│   ├── utils/              # Utilidades auxiliares
│   │   ├── files.py
│   │   └── summarization.py # Utilidad de resumen automático de contexto
│   └── main.py             # Orquestador principal del Grafo (StateGraph)
└── tests/                  # Suite de pruebas automatizadas
    ├── conftest.py         # Configuración y fixtures compartidas de pytest
    ├── test_agents.py      # Pruebas de agentes
    ├── test_e2e.py         # Pruebas End-to-End
    ├── test_files.py       # Pruebas de utilidades de archivos
    ├── test_integration.py # Pruebas de integración LangGraph
    ├── test_llm_factory.py # Pruebas de la factoría de LLMs
    ├── test_mcp_server.py  # Pruebas del servidor MCP
    ├── test_summarization.py # Pruebas unitarias de resumen de contexto
    └── test_tool_nodes.py  # Pruebas de nodos de herramientas
```

---

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
Crea un archivo `.env` en la raíz. Ejemplo para Google Gemini:
```env
LLM_API_KEY="tu_gemini_api_key"
LLM_PROVIDER="google"
LLM_MODEL="gemini-2.5-flash-lite"
MCP_AUTO_APPROVE="true"
```

---

## 🔌 Integración con MCP y Cline

### Configuración del Servidor MCP (`mcpServers`)
```json
{
  "mcpServers": {
    "AIDevTeam": {
      "command": "/ruta/a/copilot_support/.venv/bin/python",
      "args": [
        "/ruta/a/copilot_support/mcp_server.py"
      ],
      "env": {
        "LLM_API_KEY": "tu_api_key",
        "LLM_MODEL": "gemini-2.5-flash-lite",
        "LLM_PROVIDER": "google",
        "FASTMCP_LOG_LEVEL": "CRITICAL",
        "MCP_AUTO_APPROVE": "true",
        "MCP_TASK_TIMEOUT_SECONDS": "300"
      },
      "alwaysAllow": [
        "delegar_tarea_a_equipo_ia"
      ],
      "timeout": 600
    }
  }
}
```

### Integración con Cline
El archivo `tech-lead-export.yaml` define un "Custom Mode" (Tech Lead) para Cline, permitiendo que el asistente actúe como gestor de proyectos y delegue el trabajo pesado de codificación al equipo de IA a través del servidor MCP.

---

## 🛡️ Términos de Uso

Este servidor MCP se distribuye bajo un modelo de **Código Visible (Source Available)** para fines no comerciales. Se permite el acceso al código fuente para su auditoría, aprendizaje y uso privado.

Queda estrictamente prohibida la explotación comercial, venta o redistribución de este software como parte de un producto o servicio de pago sin autorización previa por escrito del autor.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
