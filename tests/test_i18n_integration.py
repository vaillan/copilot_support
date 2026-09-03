"""Prueba de integración end-to-end de la internacionalización (es/en).

Ejercita la cadena real del servidor MCP (delegar_tarea_a_equipo_ia ->
generar_markdown_pausa -> obtener_mensaje) mockeando únicamente el grafo
(agentes_app.aget_state y agentes_app.ainvoke) para detener el flujo en
Pausa 1 (nodo agente_codificador). No duplica las pruebas unitarias de
tests/test_i18n.py ni modifica lógica de producción.
"""

import asyncio
from contextlib import ExitStack
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_server import delegar_tarea_a_equipo_ia
from app.utils.i18n import obtener_mensaje


def _estado_pausa1(next_nodes, values):
    """Construye un estado mockeado del grafo con .next y .values."""
    mock_state = MagicMock()
    mock_state.next = next_nodes
    mock_state.values = values
    return mock_state


def _mock_grafo_pausa1():
    """Retorna un contexto que mockea el grafo para detener el flujo en Pausa 1."""
    stack = ExitStack()
    stack.enter_context(patch.multiple(
        "mcp_server.agentes_app",
        aget_state=AsyncMock(side_effect=[
            _estado_pausa1([], {}),
            _estado_pausa1(
                ["agente_codificador"],
                {
                    "plan_de_accion": {
                        "explicacion_arquitectura": "Plan de integración i18n",
                        "pasos": [
                            {
                                "archivo": "app/utils/i18n.py",
                                "tarea": "Refactor",
                                "requiere_test": True,
                            }
                        ],
                    }
                },
            ),
        ]),
        ainvoke=AsyncMock(return_value={}),
    ))
    # Garantiza que la auto-aprobación no consuma el side_effect de aget_state.
    stack.enter_context(patch.dict("os.environ", {"MCP_AUTO_APPROVE": "false"}))
    return stack


def test_flujo_real_pausa1_en_espanol():
    """Una instrucción en español debe producir el markdown de Pausa 1 en español."""
    with _mock_grafo_pausa1():
        markdown = asyncio.run(delegar_tarea_a_equipo_ia(
            instruccion="Crea una función de autenticación para el proyecto",
            directorio_proyecto="./",
        ))

    assert obtener_mensaje("pausa.instrucciones_cuerpo", "es") in markdown
    assert obtener_mensaje("pausa.instrucciones_cuerpo", "en") not in markdown
    assert obtener_mensaje("flujo.titulo_pausa1", "es") in markdown
    assert obtener_mensaje("flujo.titulo_pausa1", "en") not in markdown


def test_flujo_real_pausa1_en_ingles():
    """Una instrucción en inglés debe producir el markdown de Pausa 1 en inglés."""
    with _mock_grafo_pausa1():
        markdown = asyncio.run(delegar_tarea_a_equipo_ia(
            instruccion="Create an authentication function for the project",
            directorio_proyecto="./",
        ))

    assert obtener_mensaje("pausa.instrucciones_cuerpo", "en") in markdown
    assert obtener_mensaje("pausa.instrucciones_cuerpo", "es") not in markdown
    assert obtener_mensaje("flujo.titulo_pausa1", "en") in markdown
    assert obtener_mensaje("flujo.titulo_pausa1", "es") not in markdown