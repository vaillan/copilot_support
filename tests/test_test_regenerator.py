"""Pruebas unitarias del mecanismo de regeneración de tests (anti-bucle)."""

import json
import time
from pathlib import Path

from langchain_core.messages import AIMessage

from app.utils import test_regenerator
from app.utils.test_regenerator import (
    _es_ruta_excluida,
    _extraer_archivos_modificados,
    calcular_hash_archivo,
    evaluar_regeneracion_tests,
)


def _tool_call(nombre: str, args: dict) -> AIMessage:
    """Construye un AIMessage con una única tool_call del nombre y args dados."""
    return AIMessage(content="", tool_calls=[{"name": nombre, "args": args, "id": "call_1"}])


class _MensajeArgsStr:
    """Stub de mensaje con tool_calls cuyo args es un string JSON (defensa del módulo)."""

    def __init__(self, tool_calls: list) -> None:
        self.tool_calls = tool_calls


def test_calcular_hash_archivo(tmp_path: Path) -> None:
    """Happy path: archivo con contenido devuelve hash de 64 hex; inexistente devuelve ''."""
    archivo = tmp_path / "main.py"
    archivo.write_text("print('hola')", encoding="utf-8")
    hash_calculado = calcular_hash_archivo(archivo)
    assert len(hash_calculado) == 64
    assert all(c in "0123456789abcdef" for c in hash_calculado)
    assert calcular_hash_archivo(tmp_path / "no_existe.py") == ""


def test_es_ruta_excluida() -> None:
    """Edge case: filtrado por componentes de ruta; tupla vacía nunca excluye."""
    assert _es_ruta_excluida("tests/test_x.py", ("tests",)) is True
    assert _es_ruta_excluida("app/tests/y.py", ("tests",)) is True
    assert _es_ruta_excluida("app/main.py", ("tests",)) is False
    assert _es_ruta_excluida("app/main.py", ()) is False


def test_extraer_archivos_modificados() -> None:
    """Extrae rutas de write_file/edit_file/copy_file y args como string JSON; args malformado no lanza."""
    msgs = [
        _tool_call("write_file", {"file_path": "app/a.py", "content": "x"}),
        _tool_call("edit_file", {"path": "app/b.py"}),
        _tool_call("copy_file", {"source_path": "app/c.py", "destination_path": "app/d.py"}),
        _MensajeArgsStr([{"name": "write_file", "args": json.dumps({"file_path": "app/e.py"}), "id": "call_2"}]),
        _MensajeArgsStr([{"name": "write_file", "args": "{json malformado", "id": "call_3"}]),
        _tool_call("read_file", {"file_path": "app/no_cuenta.py"}),
    ]
    rutas = _extraer_archivos_modificados(msgs, AIMessage(content=""))
    assert rutas == ["app/a.py", "app/b.py", "app/d.py", "app/e.py"]


def test_evaluar_happy_path(tmp_path: Path) -> None:
    """Happy path: cambio real de archivo dispara la regeneración exactamente una vez."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v1')", encoding="utf-8")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path), [_tool_call("write_file", {"file_path": "app/main.py"})], AIMessage(content=""), {}
    )
    assert resultado["disparar"] is True
    assert resultado["razon"] == "ok"
    assert resultado["archivos_modificados"] == ["app/main.py"]


def test_evaluar_mismo_contenido_no_dispara(tmp_path: Path) -> None:
    """Edge case: si el contenido no cambió (hash igual), no se dispara nada."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v1')", encoding="utf-8")
    hash_actual = calcular_hash_archivo(tmp_path / "app" / "main.py")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path),
        [_tool_call("write_file", {"file_path": "app/main.py"})],
        AIMessage(content=""),
        {"test_regeneration_hashes": {"app/main.py": hash_actual}},
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "sin_cambios_reales"


def test_evaluar_archivos_en_tests_no_dispara(tmp_path: Path) -> None:
    """Edge case (anti-bucle): los archivos bajo tests/ nunca re-disparan el mecanismo."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test_x(): pass", encoding="utf-8")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path), [_tool_call("write_file", {"file_path": "tests/test_foo.py"})], AIMessage(content=""), {}
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "sin_archivos"


def test_evaluar_tope_iteraciones(tmp_path: Path) -> None:
    """Edge case (anti-bucle): alcanzado el tope de iteraciones, el ciclo se detiene."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v2')", encoding="utf-8")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path),
        [_tool_call("write_file", {"file_path": "app/main.py"})],
        AIMessage(content=""),
        {"test_regeneration_count": test_regenerator.settings.TEST_REGENERATION_MAX_ITERATIONS,
         "test_regeneration_hashes": {"app/main.py": "hash_viejo"}},
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "tope_alcanzado"


def test_evaluar_cooldown(tmp_path: Path) -> None:
    """Edge case (anti-bucle): dentro del cooldown no se dispara una segunda regeneración."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v2')", encoding="utf-8")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path),
        [_tool_call("write_file", {"file_path": "app/main.py"})],
        AIMessage(content=""),
        {"test_regeneration_last_ts": time.time(), "test_regeneration_hashes": {"app/main.py": "hash_viejo"}},
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "cooldown"


def test_evaluar_deshabilitado(tmp_path: Path, monkeypatch) -> None:
    """Edge case: con el mecanismo deshabilitado nunca se dispara."""
    monkeypatch.setattr(test_regenerator.settings, "TEST_REGENERATION_ENABLED", False)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('v1')", encoding="utf-8")
    resultado = evaluar_regeneracion_tests(
        str(tmp_path), [_tool_call("write_file", {"file_path": "app/main.py"})], AIMessage(content=""), {}
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "deshabilitado"


def test_evaluar_archivo_inexistente_sin_crash(tmp_path: Path) -> None:
    """Edge case: archivo borrado/inexistente (hash '') no lanza excepción ni dispara."""
    resultado = evaluar_regeneracion_tests(
        str(tmp_path),
        [_tool_call("write_file", {"file_path": "app/main.py"})],
        AIMessage(content=""),
        {"test_regeneration_hashes": {"app/main.py": ""}},
    )
    assert resultado["disparar"] is False
    assert resultado["razon"] == "sin_cambios_reales"
