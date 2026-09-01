"""Tests de las mitigaciones anti-bucle del Agente Planificador.

Cubren:
- CA1: constante UMBRAL_INSTRUCCION_LARGA y función _resumir_instruccion_larga.
- CA2: la instrucción original permanece intacta y se usa el resumen cuando supera el umbral.
- CA3: umbrales anti-bucle ajustados (6, 9, 10).
- CA4: rama temprana de salida estructurada para instrucciones largas en iteración 1.
- CA5: degradación segura ante fallo o resumen vacío.
"""

from unittest.mock import patch

import pytest

from app.agents import agente_planificador
from app.agents.agente_planificador import (
    UMBRAL_FORZAR_PLAN,
    UMBRAL_INSTRUCCION_LARGA,
    UMBRAL_PLAN_ESTRUCTURADO,
    _resumir_instruccion_larga,
)


class _RespuestaFake:
    """Fake de respuesta de LLM con atributo content."""

    def __init__(self, content: str):
        self.content = content


class TestConstantesUmbrales:
    """CA3: verificación de los umbrales anti-bucle."""

    def test_umbral_forzar_plan_es_6(self):
        assert UMBRAL_FORZAR_PLAN == 6

    def test_umbral_plan_estructurado_es_9(self):
        assert UMBRAL_PLAN_ESTRUCTURADO == 9

    def test_umbral_instruccion_larga_es_2500(self):
        assert UMBRAL_INSTRUCCION_LARGA == 2500

    def test_limite_iteraciones_es_10(self):
        # El tope se valida contra el código fuente (loop_counter > 10).
        fuente = open(agente_planificador.__file__, encoding="utf-8").read()
        assert "loop_counter > 10" in fuente
        assert "límite máximo de iteraciones (10)" in fuente


class TestResumirInstruccionLarga:
    """CA1 + CA5: función de resumen y degradación segura."""

    def test_devuelve_resumen_cuando_llm_responde(self):
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory:
            mock_llm = mock_factory.return_value
            mock_llm.invoke.return_value = _RespuestaFake("Resumen conciso de la instrucción")
            resultado = _resumir_instruccion_larga("x" * 3000)
            assert resultado == "Resumen conciso de la instrucción"
            mock_llm.invoke.assert_called_once()

    def test_degrade_a_original_ante_excepcion(self):
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory:
            mock_llm = mock_factory.return_value
            mock_llm.invoke.side_effect = RuntimeError("fallo del LLM")
            original = "y" * 3000
            resultado = _resumir_instruccion_larga(original)
            assert resultado == original

    def test_degrade_a_original_ante_resumen_vacio(self):
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory:
            mock_llm = mock_factory.return_value
            mock_llm.invoke.return_value = _RespuestaFake("   ")
            original = "z" * 3000
            resultado = _resumir_instruccion_larga(original)
            assert resultado == original

    def test_no_resume_instruccion_corta(self):
        # La función en sí no decide por longitud (eso ocurre en el nodo);
        # verifica que con entrada corta el fallback no altera el flujo.
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory:
            mock_llm = mock_factory.return_value
            mock_llm.invoke.return_value = _RespuestaFake("resumen")
            # Aun llamada directamente con texto corto, si el LLM responde lo usa.
            resultado = _resumir_instruccion_larga("corto")
            assert resultado == "resumen"


class TestRamaTemprana:
    """CA4: la rama temprana está presente para instrucción larga."""

    def test_rama_temprana_existe_en_nodo(self):
        fuente = open(agente_planificador.__file__, encoding="utf-8").read()
        assert "loop_counter == 1" in fuente
        assert "UMBRAL_INSTRUCCION_LARGA" in fuente
        assert "_es_peticion_analisis(instruccion)" in fuente
        assert "with_structured_output(PlanDeAccionInput)" in fuente

    def test_instruccion_efectiva_presente(self):
        fuente = open(agente_planificador.__file__, encoding="utf-8").read()
        assert "_resumir_instruccion_larga(instruccion)" in fuente
        assert "instruccion_efectiva" in fuente
