"""Pruebas unitarias del artefacto estático de verificación E2E.

Depende del artefacto `e2e_test_output.txt` generado por tests/test_e2e.py
(que ya no lo elimina al finalizar). Si el artefacto no existe (p. ej. el E2E
se omitió o falló antes de crearlo), los tests se marcan como skip. Tras
verificarse, el artefacto se elimina para no dejar residuos en el repositorio.
"""

from pathlib import Path

import pytest

PROYECTO_RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO_E2E = PROYECTO_RAIZ / "e2e_test_output.txt"
CONTENIDO_ESPERADO = "Hello E2E"

@pytest.fixture(scope="module", autouse=True)
def _artefacto_y_limpieza():
    """Exige el artefacto en tiempo de EJECUCIÓN (no en colección) y lo limpia al final del módulo.

    El skip en runtime es obligatorio: a nivel de colección el archivo aún no
    existe porque tests/test_e2e.py (que lo genera) se ejecuta después de la
    recolección de todos los módulos de test. El ámbito de módulo garantiza que
    la limpieza ocurra solo tras verificar TODOS los tests de este archivo.
    """
    if not ARCHIVO_E2E.is_file():
        pytest.skip("Requiere el artefacto e2e_test_output.txt generado por tests/test_e2e.py")
    yield
    if ARCHIVO_E2E.is_file():
        ARCHIVO_E2E.unlink()


def test_archivo_e2e_existe() -> None:
    """El archivo de salida E2E debe existir en la raíz del proyecto."""
    assert ARCHIVO_E2E.is_file(), f"No se encontró {ARCHIVO_E2E}"


def test_contenido_exacto_sin_salto_final() -> None:
    """El contenido debe coincidir carácter a carácter con 'Hello E2E'."""
    contenido = ARCHIVO_E2E.read_text(encoding="utf-8")
    assert contenido == CONTENIDO_ESPERADO


def test_sin_bom() -> None:
    """El archivo no debe contener BOM (Byte Order Mark) UTF-8."""
    bytes_iniciales = ARCHIVO_E2E.read_bytes()[:3]
    assert bytes_iniciales != b"\xef\xbb\xbf"


def test_longitud_exacta() -> None:
    """El contenido debe tener exactamente 9 caracteres ('Hello E2E')."""
    assert len(ARCHIVO_E2E.read_text(encoding="utf-8")) == len(CONTENIDO_ESPERADO)
