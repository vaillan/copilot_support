# Documentación Técnica: AI DevTeam

Este documento detalla la arquitectura, el flujo de control y las herramientas de los agentes en el servidor AI DevTeam.

## 🏗️ Arquitectura de LangGraph (API Funcional)

A diferencia de las arquitecturas de grafos tradicionales con bordes estáticos, AI DevTeam utiliza la **API Funcional de LangGraph** (`Command`, `goto`, `update`). Esto permite que cada nodo controle de forma dinámica hacia dónde se dirige el flujo de ejecución, basándose en la lógica interna del agente y los resultados de las herramientas.

### Estructura del Grafo (`app/main.py`)

El grafo se inicializa con `StateGraph(ProjectState)` y registra los nodos principales y sus respectivos nodos de herramientas:

1.  **Agentes (Cerebros)**: `agente_planificador`, `agente_codificador`, `agente_revisor`, `agente_documentador`.
2.  **Nodos de Herramientas**: Gestionados mediante la factoría `create_tool_node` en `app/utils/agent_factory.py`.

### Control de Flujo con `Command`

Cada agente devuelve un objeto `Command` que puede:
- `update`: Modificar el estado (mensajes, plan, errores).
- `goto`: Especificar el siguiente nodo (otro agente o su nodo de herramientas).
- `END`: Finalizar la ejecución del grafo.

## 🤖 Detalles de los Agentes y Herramientas

### 1. Agente Planificador (Arquitecto)
- **Función**: Analizar requerimientos y diseñar la solución técnica.
- **Herramientas de Investigación**:
  - `read_file`, `list_directory`: Exploración local.
  - `busqueda_web_searx`: Búsqueda externa mediante SearxNG.
- **Herramienta de Salida**: `PlanDeAccion` (Pydantic model) que estructura la tarea en pasos.
- **Transición**: Tras generar el plan, el flujo se detiene (`interrupt_before=["agente_codificador"]`) esperando aprobación humana.

### 2. Agente Codificador (Programador)
- **Función**: Traducir el plan en código fuente real.
- **Herramientas de Archivos**: `write_file`, `delete_file`, `move_file`, `copy_file`, `read_file`, `list_directory`, `file_search`.
- **Herramienta de Cierre**: `CodigoCompletado` (utilizada cuando todos los pasos del plan han sido implementados).

### 3. Agente Revisor (QA)
- **Función**: Validar que el código funcione y cumpla con los requisitos.
- **Herramientas**:
  - `terminal` (ShellTool): Ejecución de comandos (tests, linters, compilación).
  - `read_file`, `list_directory`: Inspección post-implementación.
- **Herramienta de Decisión**: `finalizar_revision(aprobado, reporte_errores)`.
  - Si `aprobado=True` -> `goto="agente_documentador"`.
  - Si `aprobado=False` -> `goto="agente_codificador"` (ciclo de corrección).

### 4. Agente Documentador
- **Función**: Actualizar la documentación del proyecto.
- **Herramientas**: `read_file`, `write_file`, `list_directory`.
- **Herramienta de Cierre**: `finalizar_documentacion(resumen)`. Al llamarla, el flujo se dirige a `END`.

## 💾 Persistencia y Estado (`ProjectState`)

El estado del proyecto (`app/models/models.py`) extiende `MessagesState` de LangGraph e incluye campos adicionales:

```python
class ProjectState(MessagesState):
    instruccion_usuario: str
    directorio_proyecto: str
    plan_de_accion: dict  # Estructurado por el Arquitecto
    codigo_escrito: str    # Resumen del Programador
    errores_terminal: str # Retroalimentación del QA
```

La persistencia se maneja mediante `SqliteSaver`, almacenando todo el historial en `memoria_agentes.db`.

## ⚙️ Configuración y Proveedores (Settings)

El sistema soporta múltiples proveedores de LLM configurables en `.env`:

- **Google**: Modelos `gemini-*`. Recomendado para rendimiento/coste.
- **OpenAI**: Soporta modelos de razonamiento `o1` y `o3-mini`.
- **Anthropic**: Soporta `claude-3-7-sonnet` con el parámetro `thinking` habilitado.
- **OpenRouter**: Para acceso a modelos adicionales a través de una API unificada.

La lógica de instanciación reside en `app/settings/settings.py`, asegurando que cada proveedor reciba los parámetros correctos (temperatura, thinking budget, etc.).
