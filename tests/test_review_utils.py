"""
Tests unitarios para ``app/utils/review_utils.py``.

Cubren los cuatro helpers puros de revisión: ``plan_requiere_pruebas``,
``detectar_errores_en_mensajes``, ``detectar_comando_duplicado`` y
``es_respuesta_aprobatoria``. Se usan objetos simples con atributo
``content`` (``SimpleNamespace``) en lugar de mensajes reales de LangChain
para mantener las pruebas aisladas.
"""

from types import SimpleNamespace

from app.utils.review_utils import (
    detectar_comando_duplicado,
    detectar_errores_en_mensajes,
    es_respuesta_aprobatoria,
    plan_requiere_pruebas,
)


def _mensaje(content):
    """Crea un mensaje dummy con atributo ``content``."""
    return SimpleNamespace(content=content)


class TestPlanRequierePruebas:
    def test_plan_requiere_pruebas_true(self):
        """Plan con un paso requiere_test=True retorna True."""
        plan = {"pasos": [
            {"archivo": "a.py", "tarea": "x", "requiere_test": False},
            {"archivo": "b.py", "tarea": "y", "requiere_test": True},
        ]}
        assert plan_requiere_pruebas(plan) is True

    def test_plan_requiere_pruebas_false(self):
        """Plan con todos los pasos requiere_test=False retorna False."""
        plan = {"pasos": [
            {"archivo": "a.py", "tarea": "x", "requiere_test": False},
            {"archivo": "b.py", "tarea": "y", "requiere_test": False},
        ]}
        assert plan_requiere_pruebas(plan) is False

    def test_plan_requiere_pruebas_none(self):
        """Plan None retorna False."""
        assert plan_requiere_pruebas(None) is False

    def test_plan_requiere_pruebas_sin_clave(self):
        """Pasos sin la clave 'requiere_test' retornan False."""
        plan = {"pasos": [
            {"archivo": "a.py", "tarea": "x"},
            {"archivo": "b.py", "tarea": "y"},
        ]}
        assert plan_requiere_pruebas(plan) is False

    def test_plan_requiere_pruebas_pasos_vacios_requieren_revision(self):
        """Plan con lista de pasos vacía NO se aprueba automáticamente: retorna True / requiere revisión."""
        assert plan_requiere_pruebas({"pasos": []}) is True

    def test_plan_requiere_pruebas_sin_clave_pasos(self):
        """Dict sin la clave 'pasos' retorna False."""
        assert plan_requiere_pruebas({"otro_campo": 1}) is False

    def test_plan_requiere_pruebas_valor_no_booleano(self):
        """Valores no booleanos en requiere_test no cuentan como True."""
        plan = {"pasos": [{"tarea": "x", "requiere_test": "si"}]}
        assert plan_requiere_pruebas(plan) is False


class TestDetectarErroresEnMensajes:
    def test_detectar_errores_en_mensajes(self):
        """Mensaje con 'Traceback' retorna su content."""
        mensajes = [
            _mensaje("Todo correcto"),
            _mensaje("Traceback (most recent call last):\n  File x.py"),
        ]
        resultado = detectar_errores_en_mensajes(mensajes)
        assert "Traceback" in resultado

    def test_detectar_errores_sin_errores(self):
        """Mensajes sin patrones de error retornan cadena vacía."""
        mensajes = [
            _mensaje("Todo correcto"),
            _mensaje("Pruebas pasadas exitosamente"),
        ]
        assert detectar_errores_en_mensajes(mensajes) == ""

    def test_detectar_errores_content_none(self):
        """Mensajes con content None se ignoran sin lanzar excepción."""
        mensajes = [_mensaje(None), _mensaje("sin errores")]
        assert detectar_errores_en_mensajes(mensajes) == ""

    def test_detectar_errores_mensaje_sin_content(self):
        """Mensajes sin atributo content se ignoran sin lanzar excepción."""
        mensajes = [SimpleNamespace(otro="campo")]
        assert detectar_errores_en_mensajes(mensajes) == ""


class TestDetectarComandoDuplicado:
    def test_detectar_comando_duplicado(self):
        """Comando ya presente en el content de mensajes previos retorna True."""
        mensajes = [
            _mensaje("Ejecutando pytest tests/"),
            _mensaje("Resultado: OK"),
        ]
        assert detectar_comando_duplicado(mensajes, "pytest tests/") is True

    def test_detectar_comando_duplicado_en_tool_calls(self):
        """Comando presente en tool_calls de un AIMessage previo retorna True."""
        tool_call = {
            "name": "terminal",
            "args": {"commands": ["pytest tests/"]},
            "id": "call_1",
        }
        mensajes = [
            _mensaje("test"),
            SimpleNamespace(content="", tool_calls=[tool_call]),
        ]
        assert detectar_comando_duplicado(mensajes, "{'commands': ['pytest tests/']}") is True

    def test_detectar_comando_no_duplicado(self):
        """Comando nuevo no presente en mensajes previos retorna False."""
        mensajes = [
            _mensaje("Ejecutando pytest tests/"),
            _mensaje("Resultado: OK"),
        ]
        assert detectar_comando_duplicado(mensajes, "python -m compileall app/") is False

    def test_detectar_comando_duplicado_content_none(self):
        """Mensajes con content None no lanzan excepción."""
        mensajes = [_mensaje(None)]
        assert detectar_comando_duplicado(mensajes, "pytest") is False

    def test_detectar_comando_duplicado_comando_vacio(self):
        """Comando vacío retorna False."""
        mensajes = [_mensaje("pytest tests/")]
        assert detectar_comando_duplicado(mensajes, "") is False


class TestEsRespuestaAprobatoria:
    def test_es_respuesta_aprobatoria(self):
        """Texto con palabras de aprobación retorna True."""
        assert es_respuesta_aprobatoria("El código es correcto y paso las pruebas") is True

    def test_es_respuesta_no_aprobatoria(self):
        """Texto con errores retorna False."""
        assert es_respuesta_aprobatoria("hay errores en el código") is False

    def test_es_respuesta_aprobatoria_none(self):
        """Texto None retorna False."""
        assert es_respuesta_aprobatoria(None) is False

    def test_es_respuesta_aprobatoria_vacia(self):
        """Texto vacío retorna False."""
        assert es_respuesta_aprobatoria("") is False

    def test_es_respuesta_aprobatoria_mayusculas(self):
        """La comparación es insensible a mayúsculas."""
        assert es_respuesta_aprobatoria("TODO BIEN, APROBADO") is True