"""Pruebas del módulo de internacionalización app/utils/i18n.py."""

from typing import Optional

import pytest

from app.utils.i18n import (
    MENSAJES,
    detectar_idioma,
    normalizar_idioma,
    obtener_mensaje,
)


# ---------------------------------------------------------------- detección
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Escribe el archivo de configuración", "es"),
        ("Write the config file", "en"),
        ("", "en"),
        ("   ", "en"),
        ("Refactor the module and add tests", "en"),
        ("Refactoriza el módulo y añade pruebas", "es"),
        ("12345 !@#$%^&*()", "en"),
        ("¿Puedes revisar el código?", "es"),
        ("Please create the file", "en"),
    ],
)
def test_detectar_idioma(texto: str, esperado: str) -> None:
    assert detectar_idioma(texto) == esperado


# ------------------------------------------------------------- normalización
@pytest.mark.parametrize(
    ("idioma", "esperado"),
    [
        ("ES", "es"),
        ("es", "es"),
        ("en", "en"),
        ("fr", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_normalizar_idioma(idioma: Optional[str], esperado: str) -> None:
    assert normalizar_idioma(idioma) == esperado


# ------------------------------------------------------- obtención de mensaje
def test_obtener_mensaje_clave_existente_es_y_en() -> None:
    assert obtener_mensaje("pausa.si", "es") == "Si"
    assert obtener_mensaje("pausa.si", "en") == "Yes"


def test_obtener_mensaje_clave_inexistente_retorna_la_clave() -> None:
    assert obtener_mensaje("clave.inexistente") == "clave.inexistente"


def test_obtener_mensaje_interpola_kwargs() -> None:
    mensaje = obtener_mensaje("flujo.completada", "es", tarea_id="abc")
    assert mensaje == "✅ Tarea 'abc' completada exitosamente."


def test_obtener_mensaje_kwargs_faltante_retorna_plantilla_sin_formatear() -> None:
    mensaje = obtener_mensaje("flujo.completada", "es")
    assert mensaje == "✅ Tarea '{tarea_id}' completada exitosamente."


def test_obtener_mensaje_idioma_desconocido_usa_en() -> None:
    assert obtener_mensaje("pausa.si", "fr") == "Yes"


def test_catalogo_tiene_es_y_en_para_todas_las_claves() -> None:
    for clave, plantillas in MENSAJES.items():
        assert "es" in plantillas, f"Falta plantilla 'es' para {clave}"
        assert "en" in plantillas, f"Falta plantilla 'en' para {clave}"