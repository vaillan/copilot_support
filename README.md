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
- **Anti-bucle**: el Planificador aborta tras 4 reintentos consecutivos (umbral anti-bucle) y el Codificador regenera tests ante bucles; el aborto por bucle infinito se registra en `errores_terminal`.
- **Timeouts**: llamadas LLM con timeout de 900s (10 min); timeout de tareas MCP corregido en unidades.
- **Resumen de contexto** ([`app/utils/summarization.py`](app/utils/summarization.py)): `SummarizationMiddleware` con trigger de 15 mensajes, conserva 8; aplica ahorro de tokens, preserva pares `tool_calls`/`ToolMessage` y cachea plantillas de prompt.
- **Rechazo y aprobación**: el rechazo de planes/código usa `aupdate_state` con `StructuredTool` en la búsqueda web; el Agente Revisor aprueba con fallback agnóstico al idioma.
- **Índice de proyecto** ([`app/utils/project_index.py`](app/utils/project_index.py)): caché incremental invalidada por `mtime_ns` + tamaño + `sha256`.

## Agentes

| Agente | Rol | Herramientas | Límites |
|--------|-----|--------------|---------|
| Planificador | Arquitecto | Búsqueda web DuckDuckGo | Máx. 15 iteraciones; umbral de reintentos anti-bucle = 4 |
| Codificador | Programador senior | Escribe código, aplica feedback | Máx. 15 iteraciones; regeneración de tests anti-bucle ([`app/utils/test_regenerator.py`](app/utils/test_regenerator.py)) |
| Revisor | QA/DevOps | Ejecuta tests vía shell | Máx. 3 revisiones; aprueba auto si no hay tests requeridos |

## Modelos LLM

Soporta Google Gemini, OpenAI, Anthropic, OpenRouter y Ollama/local vía `init_chat_model`. Configuración multi-modelo por agente (`PLANNER_*`, `CODER_*`, `REVIEWER_*`) con fallback a variables globales `LLM_*`.

## Sistema de Skills

El sistema de skills ([`app/utils/skills_loader.py`](app/utils/skills_loader.py)) permite enriquecer los prompts de los tres agentes con instrucciones, convenciones y guías reutilizables. Las skills se descubren automáticamente desde el directorio del proyecto, se parsean y se inyectan dinámicamente en el prompt de cada agente mediante `cargar_skills_para_prompt(directorio)`.

### Cómo funciona

1. Al iniciar cada agente, se invoca `cargar_skills_para_prompt(directorio_proyecto)`.
2. El cargador recorre los directorios estándar de skills dentro del proyecto y parsea los archivos encontrados.
3. Las skills se formatean como un bloque Markdown (`=== SKILLS DISPONIBLES ===`) y se inyectan en el prompt del agente.
4. Si no hay skills, la inyección es una cadena vacía: el flujo no se rompe y el agente trabaja con su prompt base.

Las skills se cargan **por directorio de proyecto** y se inyectan en los **tres agentes** (Planificador, Codificador y Revisor).

### Instalación y directorios esperados

Basta con crear el directorio `.skills/` en la raíz del proyecto y colocar dentro los archivos de skill. El cargador también reconoce los directorios estándar de otros editores y asistentes:

| Directorio | Origen |
|------------|--------|
| `.skills/` | Directorio genérico recomendado |
| `.claude/skills/` | Claude Code |
| `.zoo/skills/` | Zoo Code |
| `.cursor/skills/` | Cursor |
| `.windsurf/skills/` | Windsurf |
| `.gemini/skills/` | Gemini CLI |
| `.codex/skills/` | OpenAI Codex |
| `.github/copilot/skills/` | GitHub Copilot |
| `.vscode/skills/` | VS Code |
| `.zed/skills/` | Zed |
| `.roo/skills/` | Roo Code |
| `.clinerules/skills/` | Cline |
| `.aider/skills/` | Aider |
| `.opencode/skills/` | OpenCode |
| `.continue/skills/` | Continue |
| `.kilo/skills/` | Kilo Code |
| `.codeium/skills/` | Codeium |
| `.tabnine/skills/` | Tabnine |
| `.warp/skills/` | Warp |

### Formatos de skills

Se soportan tres formatos de archivo: `.md`, `.json` y `.yaml`/`.yml`.

| Formato | Claves | Notas |
|---------|--------|-------|
| Markdown (`.md`) | `name`, `description`, `agentes` (frontmatter YAML opcional) | Si no hay `name`, se usa el nombre del archivo; si no hay `description`, se usa la primera línea no vacía. `agentes` opcional: si se omite aplica a todos los agentes. |
| JSON (`.json`) | `name`, `description`, `agentes`, `content` (o `instructions`) | `content`/`instructions` es obligatorio. `agentes` opcional: si se omite aplica a todos los agentes. |
| YAML (`.yaml`/`.yml`) | `name`, `description`, `agentes`, `content` (o `instructions`) | `content`/`instructions` es obligatorio. `agentes` opcional: si se omite aplica a todos los agentes. |

**Markdown con frontmatter:**

```markdown
---
name: estilo-codigo-python
description: Convenciones de estilo para el código Python del proyecto.
---

Sigue PEP 8, usa type hints en todas las firmas y docstrings de una línea.
```

**JSON:**

```json
{
  "name": "convenciones-arquitectura",
  "description": "Reglas de arquitectura para el Planificador.",
  "content": "Prioriza módulos pequeños, inyección de dependencias y YAGNI/KISS."
}
```

**YAML:**

```yaml
name: checklist-qa
description: Checklist de verificación para el Revisor.
content: |
  - Ejecutar las pruebas unitarias antes de aprobar.
  - Verificar que no haya código muerto ni placeholders.
```

### Filtrado por agente/modelo

El campo opcional `agentes` indexa el nombre del agente/modelo destino al que se inyecta la skill. Acepta una cadena separada por comas (p. ej. `planificador, revisor`) o una lista. Los valores válidos son `planificador`, `codificador` y `revisor`, y se comparan sin distinguir mayúsculas/minúsculas (case-insensitive). Si se omite o se deja vacío, la skill se inyecta en los tres agentes.

**Markdown frontmatter:**

```markdown
---
name: estilo-codigo-python
description: Convenciones de estilo para el código Python del proyecto.
agentes: codificador
---

Sigue PEP 8, usa type hints en todas las firmas y docstrings de una línea.
```

**JSON:**

```json
{
  "name": "convenciones-arquitectura",
  "description": "Reglas de arquitectura para el Planificador y el Revisor.",
  "agentes": ["planificador", "revisor"],
  "content": "Prioriza módulos pequeños, inyección de dependencias y YAGNI/KISS."
}
```

**YAML:**

```yaml
name: checklist-qa
description: Checklist de verificación para el Revisor.
agentes: revisor
content: |
  - Ejecutar las pruebas unitarias antes de aprobar.
  - Verificar que no haya código muerto ni placeholders.
```

### Ejemplos de configuración y carga por agente

Las skills se colocan en `.skills/` y se inyectan automáticamente en el prompt del agente correspondiente.

**Skill para el Planificador** (`.skills/arquitectura.md`):

```markdown
---
name: convenciones-arquitectura
description: Convenciones de diseño para el Planificador.
---

Diseña planes con pasos pequeños y verificables. Respeta YAGNI/KISS y
evita refactorizaciones no solicitadas.
```

**Skill para el Codificador** (`.skills/estilo-codigo.json`):

```json
{
  "name": "estilo-codigo-python",
  "description": "Estilo de código para el Codificador.",
  "agentes": ["codificador"],
  "content": "Usa type hints en todas las firmas, docstrings de una línea y nombres autoexplicativos."
}
```

**Skill para el Revisor** (`.skills/checklist-qa.yaml`):

```yaml
name: checklist-qa
description: Checklist de QA para el Revisor.
agentes: revisor
content: |
  - Ejecutar las pruebas antes de aprobar.
  - Rechazar si hay placeholders, TODO o código muerto.
```

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

El registro de tareas (`TaskRegistry`, [`app/utils/task_registry.py`](app/utils/task_registry.py)) persiste en disco en una base SQLite de ruta fija `tasks.db` (en la raíz del proyecto), reemplazando la persistencia previa en JSON; los errores de persistencia se registran mediante logging. El timeout de tareas MCP (`MCP_TASK_TIMEOUT_SECONDS`) se aplica en segundos y el reporte de pausa se devuelve con formato de iconos y prosa neutralizada (sin texto fijo en español).

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

Módulos en `tests/`: `test_agents`, `test_e2e`, `test_files`, `test_integration`, `test_llm_factory`, `test_mcp_server`, `test_project_index`, `test_summarization`, `test_tool_nodes`, `test_task_registry`, `test_test_regenerator`, `test_mcp_fixes`, `test_contexto_largo`, `test_revisor_fallback`.

## Nota de actualización

- **2026-01-28**: Persistencia SQLite del `TaskRegistry` en `tasks.db` (reemplaza la persistencia previa en JSON) con logging de errores de persistencia.
- **2026-01-26**: Anti-bucle reforzado: umbral de reintentos del Planificador = 4 y regeneración de tests del Codificador; el aborto por bucle infinito se registra en `errores_terminal`.
- **2026-01-24**: Timeouts LLM de 900s (10 min) y corrección de unidades del timeout de tareas MCP.
- **2026-01-22**: Resumen de contexto mejorado: ahorro de tokens, preservación de pares `tool_calls`/`ToolMessage` y caché de plantillas de prompt.
- **2026-01-20**: Mecanismo de rechazo con `aupdate_state`/`StructuredTool` en búsqueda web y fallback de aprobación del Revisor agnóstico al idioma.
- **2026-01-18**: Reporte de pausa del MCP con formato de iconos y prosa neutralizada (sin texto fijo en español).
- **2026-01-15**: Nuevos módulos de tests: `test_task_registry`, `test_test_regenerator`, `test_mcp_fixes`, `test_contexto_largo`, `test_revisor_fallback`.

## Términos de uso

Source available, no comercial. Prohibida la explotación comercial sin autorización.

© 2026 AIDevTeam