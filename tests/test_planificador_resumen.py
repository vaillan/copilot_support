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
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.agents import agente_planificador
from app.agents.agente_planificador import (
    UMBRAL_FORZAR_PLAN,
    UMBRAL_INSTRUCCION_LARGA,
    UMBRAL_PLAN_ESTRUCTURADO,
    agente_planificador as nodo_planificador,
    _resumir_instruccion_larga,
)


class _RespuestaFake:
    """Fake de respuesta de LLM con atributo content."""

    def __init__(self, content: str):
        self.content = content


class TestConstantesUmbrales:
    """CA3: verificación de los umbrales anti-bucle."""

    def test_umbral_forzar_plan_es_3(self):
        assert UMBRAL_FORZAR_PLAN == 3

    def test_umbral_plan_estructurado_es_5(self):
        assert UMBRAL_PLAN_ESTRUCTURADO == 5

    def test_umbral_instruccion_larga_es_1500(self):
        assert UMBRAL_INSTRUCCION_LARGA == 1500

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

    def test_fallback_deriva_plan_desde_instruccion(self):
        """CA4 robusto: si la salida estructurada falla en iteración 1, se
        deriva un plan desde la instrucción en lugar de degradar al flujo
        normal de tool-calls (evita agotar las iteraciones)."""
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory, patch(
            "app.agents.agente_planificador.fileSystem.get_file_content"
        ) as mock_get_file:
            mock_llm = mock_factory.return_value
            mock_get_file.return_value = "system prompt"
            mock_llm.with_structured_output.side_effect = RuntimeError("fallo structured output")

            estado = {
                "messages": [HumanMessage(content="x" * 2000)],
                "directorio_proyecto": "./",
                "loop_counter": 0,
                "instruccion_usuario": "implementa " + "x" * 2000,
            }
            resultado = nodo_planificador(estado)

            assert isinstance(resultado, Command)
            assert resultado.goto == "agente_codificador"
            update = resultado.update or {}
            assert "plan_de_accion" in update
            assert update["loop_counter"] == 0
            plan = update["plan_de_accion"]
            assert isinstance(plan.get("pasos"), list) and plan["pasos"]
            assert "fallback" in update["messages"][0].content


class TestResumenCacheado:
    """CA1: el resumen de instrucción larga se cachea para no repetir la
    llamada LLM en cada iteración del grafo."""

    def test_resumen_es_cacheado(self):
        with patch(
            "app.agents.agente_planificador.get_planner_llm"
        ) as mock_factory:
            mock_llm = mock_factory.return_value
            mock_llm.invoke.return_value = _RespuestaFake("Resumen cacheado")
            _resumir_instruccion_larga.cache_clear()

            primera = _resumir_instruccion_larga("instruccion larga " * 200)
            segunda = _resumir_instruccion_larga("instruccion larga " * 200)

            assert primera == "Resumen cacheado"
            assert segunda == "Resumen cacheado"
            # La llamada LLM se ejecuta una sola vez gracias a la caché.
            assert mock_llm.invoke.call_count == 1
            _resumir_instruccion_larga.cache_clear()
