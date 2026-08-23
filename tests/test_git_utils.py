"""Tests unitarios para app/mcp/git_utils.py.

Cubre la función pura ``obtener_git_diff`` de forma directa (sin pasar por el
monolito ``mcp_server.py``), mockeando ``subprocess.run`` y ``os.path.exists``.
Sigue el estilo de tests/test_mcp_server.py (pytest + unittest.mock).
"""

from unittest.mock import MagicMock, patch

from app.mcp.git_utils import obtener_git_diff


def test_obtener_git_diff_exitoso():
    """Caso (a): diff exitoso -> retorna el stdout del diff."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "diff --git a/app/main.py b/app/main.py\n+print('hola')\n"
    mock_res.stderr = ""

    with patch("app.mcp.git_utils.subprocess.run", return_value=mock_res) as mock_run:
        resultado = obtener_git_diff("./")

    assert resultado == "diff --git a/app/main.py b/app/main.py\n+print('hola')"
    mock_run.assert_called_once()
    # Verificar que se ejecuta git diff en el directorio indicado
    assert mock_run.call_args.args[0] == ["git", "diff"]
    assert mock_run.call_args.kwargs["cwd"] == "./"


def test_obtener_git_diff_sin_cambios():
    """Caso (b): sin cambios -> git diff vacío y git status vacío -> retorno vacío."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = ""
    mock_res.stderr = ""

    with patch("app.mcp.git_utils.subprocess.run", return_value=mock_res) as mock_run:
        resultado = obtener_git_diff("./")

    assert resultado == ""
    assert mock_run.call_count == 2  # git diff + git status -s


def test_obtener_git_diff_error_git():
    """Caso (c): error de git (returncode != 0) -> no lanza excepción y retorna vacío."""
    mock_res = MagicMock()
    mock_res.returncode = 128
    mock_res.stdout = ""
    mock_res.stderr = "fatal: not a git repository"

    with patch("app.mcp.git_utils.subprocess.run", return_value=mock_res) as mock_run:
        resultado = obtener_git_diff("./")

    assert resultado == ""
    assert mock_run.call_count == 2  # git diff falla y se intenta git status -s


def test_obtener_git_diff_fallback_git_status():
    """Caso (c'): git diff falla pero git status -s funciona -> retorna listado de archivos."""
    mock_diff = MagicMock()
    mock_diff.returncode = 1
    mock_diff.stdout = ""
    mock_diff.stderr = "error"

    mock_status = MagicMock()
    mock_status.returncode = 0
    mock_status.stdout = " M app/main.py\n?? nuevo.py\n"
    mock_status.stderr = ""

    with patch(
        "app.mcp.git_utils.subprocess.run",
        side_effect=[mock_diff, mock_status],
    ) as mock_run:
        resultado = obtener_git_diff("./")

    assert "Archivos modificados/creados (git status):" in resultado
    assert "M app/main.py" in resultado
    assert "nuevo.py" in resultado
    assert mock_run.call_count == 2


def test_obtener_git_diff_directorio_inexistente():
    """Caso (d): directorio inexistente -> retorna vacío sin invocar subprocess."""
    with patch("app.mcp.git_utils.os.path.exists", return_value=False) as mock_exists:
        with patch("app.mcp.git_utils.subprocess.run") as mock_run:
            resultado = obtener_git_diff("/ruta/inexistente/xyz_12345")

    assert resultado == ""
    mock_exists.assert_called_once_with("/ruta/inexistente/xyz_12345")
    mock_run.assert_not_called()


def test_obtener_git_diff_directorio_vacio():
    """Caso (d'): directorio vacío/None -> retorna vacío sin invocar subprocess."""
    with patch("app.mcp.git_utils.subprocess.run") as mock_run:
        assert obtener_git_diff("") == ""
        assert obtener_git_diff(None) == ""
    mock_run.assert_not_called()


def test_obtener_git_diff_subprocess_lanza_excepcion():
    """Caso (e): subprocess.run lanza FileNotFoundError -> no propaga y retorna vacío."""
    with patch(
        "app.mcp.git_utils.subprocess.run",
        side_effect=FileNotFoundError("git no instalado"),
    ):
        resultado = obtener_git_diff("./")

    assert resultado == ""