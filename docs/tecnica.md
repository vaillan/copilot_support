# Documentación Técnica: AI DevTeam

Este documento proporciona una visión técnica detallada del servidor AI DevTeam, incluyendo su arquitectura de grafos, agentes y modelos de datos.

## 🏗️ Arquitectura de LangGraph

El corazón del sistema es un `StateGraph` de LangGraph que orquestra la comunicación entre agentes autónomos. El grafo está configurado para ser persistente y soportar la intervención humana (human-in-the-loop).

### Definición del Grafo (`app/main.py`)

El grafo se compone de los siguientes nodos:

1.  **Agente Planificador**: Genera el plan inicial.
2.  **Nodo Herramientas Planificador**: Ejecuta herramientas de lectura/listado para el planificador.
3.  **Agente Codificador**: Implementa el código basado en el plan.
4.  **Nodo Herramientas Codificador**: Permite la escritura y modificación de archivos.
5.  **Agente Revisor (QA)**: Valida la implementación mediante la ejecución de comandos.
6.  **Nodo Herramientas Revisor**: Ejecuta comandos en la terminal y lee archivos.
7.  **Agente Documentador**: Genera y actualiza archivos de documentación.
8.  **Nodo Herramientas Documentador**: Permite la lectura y escritura de archivos de documentación.

### Flujo de Datos (`ProjectState`)

El estado del proyecto se define en `app/models/models.py` y hereda de `MessagesState`.

```python
class ProjectState(MessagesState):
    instruccion_usuario: str
    directorio_proyecto: str
    plan_de_accion: dict
    codigo_escrito: str
    errores_terminal: str
```

## 🤖 Detalles de los Agentes

### 1. Agente Planificador (`agente_planificador.py`)
- **Objetivo**: Entender el requerimiento y diseñar la solución.
- **Tools**: `list_directory`, `read_file`.
- **Interrupt**: El grafo se detiene **antes** de pasar al Codificador para que el usuario apruebe el plan.

### 2. Agente Codificador (`agente_codificador.py`)
- **Objetivo**: Realizar cambios efectivos en el sistema de archivos.
- **Tools**: `write_file`, `edit_file`, `create_directory`.

### 3. Agente Revisor (`agente_revisor.py`)
- **Objetivo**: Asegurar la calidad y funcionalidad.
- **Tools**: `execute_command`, `read_file`.
- **Lógica**: Si encuentra errores, envía un mensaje de retroalimentación al Codificador reiniciando el ciclo de edición.

### 4. Agente Documentador (`agente_documentador.py`)
- **Objetivo**: Mantener la documentación sincronizada con el código.
- **Tools**: `read_file`, `write_file`.
- **Finalización**: El Agente Documentador finaliza el proceso de documentación invocando la herramienta `finalizar_documentacion`. Esta herramienta registra un resumen de los cambios realizados en la documentación.

## 💾 Persistencia

El sistema utiliza `SqliteSaver` para almacenar el estado del grafo en `memoria_agentes.db`. Esto permite:
- Retomar tareas después de una interrupción manual.
- Mantener el historial de decisiones de los agentes.
- Recuperación ante fallos del proceso.

## 🔌 Integración MCP (`mcp_server.py`)

El servidor utiliza `FastMCP` para exponer la capacidad del equipo de IA como una herramienta estándar de MCP.

### Herramienta: `delegar_tarea_a_equipo_ia`

Esta herramienta actúa como el punto de entrada al grafo. Maneja la lógica de inicialización del estado y la reanudación del proceso tras la aprobación del usuario mediante el parámetro `approve`.

## ⚙️ Configuración (`app/settings/settings.py`)

El sistema es agnóstico al modelo de lenguaje gracias a LangChain. Soporta:
- **Google GenAI** (Gemini 2.0 Flash recomendado).
- **OpenAI** (GPT-4o).
- **Anthropic** (Claude 3.5 Sonnet).

La configuración se carga desde un archivo `.env` o variables de entorno del sistema.
