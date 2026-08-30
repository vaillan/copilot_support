"""Pruebas de las correcciones del agente planificador (bucle, sanitización y búsqueda web)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

from app.agents.agente_planificador import agente_planificador, _get_tools
from app.utils.summarization import sanitizar_pares_tool_call


def _tool_call_ai(id_llamada: str, nombre: str = "read_file") -> AIMessage:
    return AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {"name": nombre, "arguments": "{}", "id": id_llamada, "type": "function"}
            ]
        },
    )


def test_guard_planificador_resetea_loop_counter():
    resultado = agente_planificador({"loop_counter": 8, "messages": []})
    assert resultado.goto == END
    assert resultado.update["loop_counter"] == 0
    assert "8" in resultado.update["messages"][0].content


def test_sanitizacion_elimina_mensajes_huerfanos():
    ok_ai = _tool_call_ai("call-1")
    huerfano_ai = _tool_call_ai("call-2")
    tool_ok = ToolMessage(content="ok", tool_call_id="call-1")
    tool_huerfano = ToolMessage(content="huérfano", tool_call_id="call-9")
    mensajes = [ok_ai, huerfano_ai, tool_ok, tool_huerfano, HumanMessage(content="hola")]

    limpio = sanitizar_pares_tool_call(mensajes)

    assert ok_ai in limpio
    assert huerfano_ai not in limpio
    assert tool_ok in limpio
    assert tool_huerfano not in limpio
    assert any(isinstance(m, HumanMessage) for m in limpio)


def test_get_tools_sin_busqueda_web(monkeypatch):
    import app.agents.agente_planificador as mod

    mod._get_tools.cache_clear()
    monkeypatch.setattr(mod, "get_custom_file_tools", lambda directorio: [])
    monkeypatch.setattr(mod.settings, "ENABLE_WEB_SEARCH", False)
    nombres = [t.name for t in mod._get_tools("./")]
    assert "busqueda_web_duckduckgo" not in nombres


def test_get_tools_con_busqueda_web(monkeypatch):
    import app.agents.agente_planificador as mod

    mod._get_tools.cache_clear()
    monkeypatch.setattr(mod, "get_custom_file_tools", lambda directorio: [])
    monkeypatch.setattr(mod.settings, "ENABLE_WEB_SEARCH", True)
    nombres = [t.name for t in mod._get_tools("./")]
    assert "busqueda_web_duckduckgo" in nombres
