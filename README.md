# AIDevTeam

**AIDevTeam** es una plataforma de agentes autónomos de IA para automatizar el SDLC, orquestada con **LangGraph** y expuesta como servidor MCP (**FastMCP**).

## Arquitectura

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

- Los rechazos regresan al agente anterior (Pausa 1 → Planificador; Pausa 2 → Codificador); el Revisor reenvía errores al Codificador con máx. 3 revisiones.
- **Estado**: `ProjectState` (hereda de `MessagesState`) mantiene historial, plan, contadores e índice.
- **Resumen de contexto** ([`app/utils/summarization.py`](app/utils/summarization.py)): `SummarizationMiddleware` con trigger de 15 mensajes, conserva 8.
- **Índice de proyecto** ([`app/utils/project_index.py`](app/utils/project_index.py)): caché incremental invalidada por `mtime_ns` + tamaño + `sha256`.

## Agentes

| Agente | Rol | Herramientas | Límites |
|--------|-----|--------------|---------|
| Planificador | Arquitecto | Búsqueda web DuckDuckGo | Máx. 15 iteraciones |
| Codificador | Programador senior | Escribe código, aplica feedback | Máx. 15 iteraciones |
| Revisor | QA/DevOps | Ejecuta tests vía shell | Máx. 3 revisiones; aprueba auto si no hay tests requeridos |

## Modelos LLM

Soporta Google Gemini, OpenAI, Anthropic, OpenRouter y Ollama/local vía `init_chat_model`. Configuración multi-modelo por agente (`PLANNER_*`, `CODER_*`, `REVIEWER_*`) con fallback a variables globales `LLM_*`.

## Instalación

Requisitos: Python 3.10+

```bash
git clone <repository-url>
cd copilot_support
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Bloque `.env`:

```env
# Global (fallback)
LLM_API_KEY="tu_llm_api_key"
LLM_PROVIDER="google"
LLM_MODEL="gemini-2.5-flash-lite"

# Por agente (opcional)
PLANNER_PROVIDER="anthropic"
PLANNER_MODEL="claude-3-5-sonnet"
PLANNER_API_KEY="tu_anthropic_api_key"
CODER_PROVIDER="openai"
CODER_MODEL="gpt-4o"
CODER_API_KEY="tu_openai_api_key"
REVIEWER_PROVIDER="openrouter"
REVIEWER_MODEL="nvidia/nemotron-3-super-120b-a12b:free"
REVIEWER_API_KEY="tu_openrouter_api_key"

# Servidor MCP
MCP_AUTO_APPROVE="true"
MCP_TASK_TIMEOUT_SECONDS="300"

# Índice de proyecto
PROJECT_INDEX_ENABLED="true"
PROJECT_INDEX_MAX_TOKENS_PER_FILE="400"
PROJECT_INDEX_CACHE_DIR=".project_index"
```

## Servidor MCP

El servidor expone 4 herramientas para delegar, supervisar y controlar tareas del equipo de agentes.

### `delegar_tarea_a_equipo_ia`

Delega una tarea al equipo de 3 agentes (Planificador → Codificador → Revisor).

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `instruccion` | string | Sí | Qué construir, o feedback si se rechaza plan/código. |
| `directorio_proyecto` | string | Sí | Ruta absoluta del proyecto. |
| `approve` | boolean | No | Aprobar y continuar si pausado (Pausa 1 o 2). |
| `tarea_id` | string | No* | Obligatorio si `approve=true` o reanudando. |
| `auto_approve` | boolean | No | Auto-aprueba pausas (o `MCP_AUTO_APPROVE="true"`). |

### `consultar_estado_tarea`

Consulta el estado actual de una tarea registrada.

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `tarea_id` | string | Sí | Id de la tarea a consultar. |
| `directorio_proyecto` | string | No | Ruta del proyecto. |

### `listar_tareas`

Lista las tareas registradas, opcionalmente filtradas por estado.

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `estado` | string | No | Filtro opcional: `running`/`paused_planning`/`paused_code`/`completed`/`cancelled`/`timeout`/`error`. |

### `cancelar_tarea`

Cancela una tarea en curso.

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `tarea_id` | string | Sí | Id de la tarea en curso a cancelar. |

**Flujo**: tarea nueva → Planificador → **Pausa 1** (plan) → aprobar → Codificador → **Pausa 2** (código) → aprobar → Revisor ejecuta tests → Fin. Los rechazos regresan al agente anterior; los errores del Revisor vuelven al Codificador (máx. 3 revisiones).

**Transporte**: `stdio` (por defecto) o `sse` (`FASTMCP_TRANSPORT`, `FASTMCP_HOST`, `FASTMCP_PORT`).

> ⚠️ Error `-32000 Connection closed`: suele deberse a imports relativos fallidos cuando el cliente lanza el proceso desde otro `cwd`. Configura `cwd` en el cliente apuntando a la raíz del proyecto.

Ejemplo `mcpServers` mínimo:

```json
{
  "mcpServers": {
    "AIDevTeam": {
      "command": "/ruta/a/copilot_support/.venv/bin/python",
      "args": ["/ruta/a/copilot_support/mcp_server.py"],
      "cwd": "/ruta/a/copilot_support",
      "env": {
        "LLM_API_KEY": "tu_api_key",
        "LLM_MODEL": "gemini-2.5-flash-lite",
        "LLM_PROVIDER": "google"
      }
    }
  }
}
```

Compatible con Zoo Code ([`tech-lead-export.yaml`](tech-lead-export.yaml)) y Claude Code (`/mcp`).

## Pruebas

```bash
./run_tests.sh          # unitarias + linter (flake8)
./run_tests.sh --e2e    # incluye End-to-End
```

Módulos en `tests/`: `test_agents`, `test_e2e`, `test_files`, `test_integration`, `test_llm_factory`, `test_mcp_server`, `test_project_index`, `test_summarization`, `test_tool_nodes`.

## Términos de uso

Source available, no comercial. Prohibida la explotación comercial sin autorización.

© 2026 AIDevTeam