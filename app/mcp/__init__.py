"""Capa de servidor MCP modular: helpers de progreso, git y reporting.

Este paquete aloja los helpers puros (sin dependencia del grafo LangGraph)
que antes vivían en el monolito ``mcp_server.py``:

- ``progress.py``: notificación de progreso segura hacia el cliente MCP.
- ``git_utils.py``: obtención de git diff / git status de un directorio.
- ``reporting.py``: generación de reportes Markdown de pausa y visualización
  de cambios de una tarea.

La orquestación dependiente del grafo (``delegar_tarea_a_equipo_ia``,
``consultar_estado_tarea``, ``listar_tareas``, ``cancelar_tarea``) permanece
en ``mcp_server.py`` para preservar la compatibilidad con los tests existentes
y la configuración de los clientes MCP.

NOTA: este módulo NO importa nada en su interior a propósito, para evitar
ciclos de importación con ``mcp_server.py``.
"""