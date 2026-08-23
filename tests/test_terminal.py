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

    def test_validar_comando_php_artisan_test(self):
        """`php artisan test` (Laravel/PHP) es un comando permitido."""
        permitido, mensaje = _validar_comando("php artisan test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_composer_test(self):
        """`composer test` (Composer/PHP) es un comando permitido."""
        permitido, mensaje = _validar_comando("composer test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_go_test(self):
        """`go test ./...` (Go) es un comando permitido."""
        permitido, mensaje = _validar_comando("go test ./...")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_mvn_test(self):
        """`mvn test` (Maven/Java) es un comando permitido."""
        permitido, mensaje = _validar_comando("mvn test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_gradle_test(self):
        """`gradle test` (Gradle/Java) es un comando permitido."""
        permitido, mensaje = _validar_comando("gradle test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_npm_test(self):
        """`npm test` (Node.js) es un comando permitido."""
        permitido, mensaje = _validar_comando("npm test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_jest(self):
        """`jest` (Node.js) es un comando permitido."""
        permitido, mensaje = _validar_comando("jest")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_cargo_test(self):
        """`cargo test` (Cargo/Rust) es un comando permitido."""
        permitido, mensaje = _validar_comando("cargo test")
        assert permitido is True
        assert mensaje == ""

    def test_validar_comando_prefijo_nuevo_sin_espacio_no_falso_positivo(self):
        """Un prefijo nuevo sin espacio no produce un falso positivo."""
        permitido, mensaje = _validar_comando("npmtest")
        assert permitido is False
        assert "Error" in mensaje

    def test_validar_comando_operadores_peligrosos_con_nuevos_prefijos(self):
        """Los operadores peligrosos se rechazan incluso con los nuevos
        prefijos de la whitelist ampliada."""
        permitido, mensaje = _validar_comando("npm test; rm -rf /")
        assert permitido is False
        assert "Error" in mensaje

        permitido, mensaje = _validar_comando("go test && echo pwned")
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

    def test_limitar_salida_retrocompatible_sin_limites_extra(self):
        """Con max_lineas=None y max_caracteres_por_linea=None el resultado
        es exactamente el original (solo el cap max_chars)."""
        salida = "linea1\nlinea2\nlinea3"
        resultado = _limitar_salida(salida, max_chars=4000)
        assert resultado == salida

    def test_limitar_salida_por_lineas(self):
        """Se conservan las primeras max_lineas y se añade el marcador."""
        salida = "\n".join(f"linea{i}" for i in range(10))
        resultado = _limitar_salida(salida, max_lineas=3)
        lineas = resultado.splitlines()
        assert lineas[0] == "linea0"
        assert lineas[1] == "linea1"
        assert lineas[2] == "linea2"
        assert lineas[3] == "[lineas restantes omitidas: 7]"
        assert len(lineas) == 4

    def test_limitar_salida_por_lineas_sin_omitir(self):
        """Si no se supera max_lineas, la salida queda intacta."""
        salida = "a\nb\nc"
        resultado = _limitar_salida(salida, max_lineas=5)
        assert resultado == salida

    def test_limitar_salida_por_lineas_limite_cero(self):
        """max_lineas <= 0 trunca toda la salida."""
        resultado = _limitar_salida("a\nb\nc", max_lineas=0)
        assert resultado == ""

    def test_limitar_salida_por_caracteres_por_linea(self):
        """Las líneas que exceden el límite se truncan con el marcador."""
        salida = "a" * 100 + "\n" + "b" * 10
        resultado = _limitar_salida(salida, max_caracteres_por_linea=20)
        lineas = resultado.splitlines()
        assert lineas[0] == "a" * 20 + "[...]"
        assert lineas[1] == "b" * 10

    def test_limitar_salida_por_caracteres_por_linea_limite_cero(self):
        """max_caracteres_por_linea <= 0 trunca toda la salida."""
        resultado = _limitar_salida("abc", max_caracteres_por_linea=0)
        assert resultado == ""

    def test_limitar_salida_combinado(self):
        """Se aplican límite de líneas, por línea y global en orden."""
        salida = "\n".join("x" * 100 for _ in range(10))
        resultado = _limitar_salida(
            salida,
            max_chars=4000,
            max_lineas=3,
            max_caracteres_por_linea=10,
        )
        lineas = resultado.splitlines()
        assert lineas[0] == "x" * 10 + "[...]"
        assert lineas[1] == "x" * 10 + "[...]"
        assert lineas[2] == "x" * 10 + "[...]"
        assert lineas[3] == "[lineas restantes omitidas: 7]"

    def test_limitar_salida_vacia(self):
        """La salida vacía retorna cadena vacía."""
        assert _limitar_salida("") == ""
        assert _limitar_salida("", max_lineas=3) == ""
        assert _limitar_salida("", max_caracteres_por_linea=3) == ""


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