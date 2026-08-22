"""
Tests unitarios para ``app/utils/terminal.py``.

Cubren: validación de comandos (whitelist de prefijos seguros), rechazo de
inyección de comandos, truncado de salida, ejecución con ``subprocess``
(exitosa y con timeout) y la herramienta decorada ``terminal`` (directorio
inexistente, comando vacío).
"""

import subprocess
from unittest.mock import patch

import pytest

from app.utils.terminal import (
    _ejecutar_comando,
    _limitar_salida,
    _validar_comando,
    _MAX_SALIDA_DEFAULT,
    terminal,
)


class TestValidarComando:
    """Pruebas de la función pura ``_validar_comando``."""

    def test_validar_comando_permitido(self):
        """Un comando que comienza con un prefijo permitido es válido."""
        permitido, mensaje = _validar_comando("pytest tests/")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_permitido_echo_con_argumentos(self):
        """Comandos con múltiples argumentos siguen siendo válidos."""
        permitido, mensaje = _validar_comando("echo hola mundo")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_rechazado_rm(self):
        """`rm` sin la restricción del directorio del proyecto se rechaza."""
        permitido, mensaje = _validar_comando("rm -rf /")
        assert permitido is False
        assert "Error" in mensaje

    def test_validar_comando_rechazado_curl(self):
        """Comandos fuera de la whitelist (p.ej. curl) se rechazan."""
        permitido, mensaje = _validar_comando("curl http://evil.com")
        assert permitido is False
        assert "Error" in mensaje

    def test_validar_comando_inyeccion_punto_y_coma(self):
        """Secuencias con `;` se rechazan por riesgo de inyección."""
        permitido, mensaje = _validar_comando("pytest; rm -rf /")
        assert permitido is False
        assert "Error" in mensaje

    def test_validar_comando_inyeccion_python_c(self):
        """Comandos con sub-shell (p.ej. python -c con ';') se rechazan."""
        permitido, mensaje = _validar_comando(
            "python -c \"import os; os.system('x')\""
        )
        assert permitido is False
        assert "Error" in mensaje

    def test_validar_comando_vacio(self):
        """El comando vacío se rechaza."""
        permitido, mensaje = _validar_comando("")
        assert permitido is False
        assert "Error" in mensaje


class TestLimitarSalida:
    def test_limitar_salida(self):
        """Salida larga se trunca a max_chars con el marcador."""
        salida_larga = "a" * 10000
        resultado = _limitar_salida(salida_larga, max_chars=4000)
        assert len(resultado) <= 4000 + len("[...salida truncada...]")
        assert "[...salida truncada...]" in resultado

    def test_limitar_salida_corta_sin_truncar(self):
        """Salida corta se devuelve intacta."""
        salida_corta = "hola"
        resultado = _limitar_salida(salida_corta, max_chars=4000)
        assert resultado == "hola"

    def test_limitar_salida_por_defecto(self):
        """El límite por defecto de la herramienta es 4000 caracteres."""
        assert _MAX_SALIDA_DEFAULT == 4000


class TestEjecutarComando:
    def test_ejecutar_comando_exitoso(self):
        """`echo hola` retorna la salida con el contenido esperado."""
        resultado = _ejecutar_comando("echo hola", directorio=".")
        assert "hola" in resultado

    @patch("app.utils.terminal.subprocess.run")
    def test_ejecutar_comando_timeout(self, mock_run):
        """Un TimeoutExpired de subprocess produce un mensaje controlado."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 5", timeout=1)
        resultado = _ejecutar_comando("sleep 5", directorio=".", timeout=1)
        assert "Timeout" in resultado
        assert "sleep 5" in resultado

    @patch("app.utils.terminal.subprocess.run")
    def test_ejecutar_comando_file_not_found(self, mock_run):
        """Un FileNotFoundError produce un mensaje controlado."""
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        resultado = _ejecutar_comando("comando_inexistente", directorio=".")
        assert "No se encontró" in resultado


class TestHerramientaTerminal:
    def test_terminal_directorio_inexistente(self):
        """Directorio inexistente produce un error controlado."""
        resultado = terminal.invoke(
            {"comando": "echo hola", "directorio": "/ruta/que/no/existe/xyz"}
        )
        assert "Error" in str(resultado)
        assert "directorio" in str(resultado).lower()

    def test_terminal_comando_vacio(self):
        """El comando vacío produce un error controlado."""
        resultado = terminal.invoke({"comando": ""})
        assert "Error" in str(resultado)

    def test_terminal_comando_no_permitido(self):
        """Un comando no permitido no se ejecuta y devuelve el error."""
        resultado = terminal.invoke({"comando": "curl http://evil.com"})
        assert "Error" in str(resultado)
        assert "permitido" in str(resultado)

    def test_terminal_comando_exitoso(self):
        """Un comando válido se ejecuta y devuelve su salida."""
        resultado = terminal.invoke({"comando": "echo hola"})
        assert "hola" in str(resultado)