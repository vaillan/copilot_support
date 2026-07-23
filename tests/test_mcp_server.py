import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server import visualizar_cambios, delegar_tarea_a_equipo_ia, obtener_git_diff

def test_visualizar_cambios_sin_parametros():
    resultado = asyncio.run(visualizar_cambios())
    assert "No se proporcionó un 'tarea_id' válido" in resultado

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
def test_visualizar_cambios_con_tarea_id(mock_aget_state):
    mock_state = MagicMock()
    mock_state.values = {
        "codigo_escrito": "Se modificó main.py",
        "directorio_proyecto": "./"
    }
    mock_state.next = ["agente_revisor"]
    mock_aget_state.return_value = mock_state

    resultado = asyncio.run(visualizar_cambios(tarea_id="task_123"))
    assert "RESUMEN DE CAMBIOS (Tarea 'task_123')" in resultado
    assert "Se modificó main.py" in resultado
    assert "Pausado antes de 'agente_revisor'" in resultado

@patch("mcp_server.subprocess.run")
def test_obtener_git_diff_exito(mock_subproc):
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "diff --git a/file.txt b/file.txt\n+hola"
    mock_subproc.return_value = mock_res

    res = obtener_git_diff("./")
    assert "diff --git" in res

@patch("mcp_server.agentes_app.aget_state", new_callable=AsyncMock)
@patch("mcp_server.agentes_app.ainvoke", new_callable=AsyncMock)
def test_delegar_tarea_pausa_2_muestra_cambios(mock_ainvoke, mock_aget_state):
    # Simular estado pausado en agente_revisor
    mock_state_pausado = MagicMock()
    mock_state_pausado.next = ["agente_revisor"]
    mock_state_pausado.values = {
        "codigo_escrito": "Creado archivo app/utils/helpers.py con funciones aux."
    }
    mock_aget_state.return_value = mock_state_pausado

    resultado = asyncio.run(delegar_tarea_a_equipo_ia(
        instruccion="Crear helpers",
        directorio_proyecto="./",
        tarea_id="task_test"
    ))

    assert "PAUSA 2 (REVISIÓN DE CÓDIGO)" in resultado
    assert "📝 CAMBIOS REALIZADOS:" in resultado
    assert "Creado archivo app/utils/helpers.py con funciones aux." in resultado
