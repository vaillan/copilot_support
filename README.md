# AIDevTeam - Equipo de Agentes de Desarrollo IA

## Descripción
**AIDevTeam** es un ecosistema de agentes autónomos diseñado para automatizar el ciclo de vida del desarrollo de software. Utiliza la arquitectura de **LangGraph** para orquestar un flujo de trabajo dinámico entre tres agentes especializados: un **Planificador** (Arquitecto), un **Codificador** (Programador) y un **Revisor** (QA/Tester).

El sistema se expone como un servidor **MCP (Model Context Protocol)**, permitiendo que cualquier cliente compatible (como Claude Desktop o VS Code) delegue tareas complejas de programación mediante una herramienta unificada.

## Características Principales
- **Arquitectura Multi-Agente con Memoria**: Los agentes comparten un estado común (`ProjectState`) y un historial de mensajes, permitiendo una colaboración coherente.
- **Ciclo de Autocorrección**: Si el agente Revisor detecta errores en los tests o la ejecución, el flujo regresa automáticamente al Codificador para aplicar las correcciones necesarias.
- **Herramientas Especializadas**:
  - **Planificador**: Acceso a búsqueda web (SearxNG) y exploración de archivos.
  - **Codificador**: Manipulación segura de archivos en el sistema local.
  - **Revisor**: Ejecución de comandos en terminal (ShellTool) para validación de código.
- **Agnóstico al Entorno**: Diseñado para operar en cualquier directorio local especificado por el usuario.
- **Integración con LLMs**: Soporta múltiples proveedores (Google Gemini, etc.) configurables mediante variables de entorno.

## Estructura del Proyecto
```text
.
├── app/
│   ├── agents/             # Lógica y definición de agentes (Planificador, Codificador, Revisor)
│   ├── models/             # Esquemas de datos (Pydantic), Estado del Grafo y Fábrica de LLMs
│   ├── prompts/            # Instrucciones del sistema (Markdown) para cada agente
│   ├── settings/           # Configuración centralizada y gestión de variables de entorno
│   ├── utils/              # Clases de utilidad para manejo de archivos
│   └── main.py             # Construcción y compilación del grafo de LangGraph
├── mcp_server.py           # Punto de entrada del servidor FastMCP
├── requirements.txt        # Dependencias (LangChain, LangGraph, FastMCP, Pydantic)
└── .env                    # Configuración de API Keys y Modelos
```

## Flujo de Trabajo
1.  **Entrada**: El usuario proporciona una instrucción y un directorio de trabajo a través del servidor MCP.
2.  **Planificación**: El `Agente Planificador` investiga el proyecto y genera un plan de acción estructurado.
3.  **Implementación**: El `Agente Codificador` sigue el plan, crea o modifica archivos y reporta sus cambios.
4.  **Validación**: El `Agente Revisor` ejecuta el código. 
    - Si hay éxito, el proceso termina (`END`).
    - Si hay errores, se notifican al Codificador para reiniciar el ciclo de edición.

## Requisitos Previos
- Python 3.10+
- Una clave de API para el modelo LLM configurado (ej. Google Gemini).
- (Opcional) Instancia local de SearxNG para la herramienta de búsqueda web.

## Instalación y Configuración
1.  **Clonar e instalar**:
    ```bash
    git clone <repository-url>
    cd copilot_support
    python -m venv .venv
    source .venv/bin/activate  # En Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Variables de Entorno**:
    Configura tu archivo `.env`:
    ```env
    # Proveedor de LLM (ej. google)
    LLM_PROVIDER=google
    # Modelo a utilizar (ej. gemini-1.5-pro)
    LLM_MODEL=gemini-1.5-pro
    # Tu API Key
    LLM_API_KEY=tu_clave_aqui
    ```

## Uso
### Ejecución del Servidor
Inicia el servidor MCP para conectarlo a tu cliente favorito:
```bash
python mcp_server.py
```

### Herramientas Expuestas
- **`delegar_tarea_a_equipo_ia(instruccion, directorio_proyecto)`**:
  - `instruccion`: Descripción de la tarea (ej: "Añade un endpoint de login a la API de FastAPI").
  - `directorio_proyecto`: Ruta absoluta de la carpeta donde se realizarán los cambios.

---
© 2026 AIDevTeam - Automatización Inteligente de Software.
