"""
Utilidades para la construcción segura de prompts.

Evita que el contenido dinámico (índice del proyecto, errores de terminal,
tracebacks, etc.) que contiene llaves literales de código fuente (ej.
`Dict[str, Any]`, `{directorio}`) sea interpretado por `ChatPromptTemplate`
como variables de plantilla al invocar `.format()`.
"""

from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def escapar_llaves(texto: str) -> str:
    """
    Escapa llaves literales para que ChatPromptTemplate no las interprete
    como variables de plantilla.

    Convierte '{' en '{{' y '}' en '}}'. Debe aplicarse SOLO al contenido
    dinámico inyectado (índice del proyecto, errores, etc.), nunca al prompt
    base que contiene placeholders legítimos como {directorio} o {plan}.

    Args:
        texto: Cadena de texto que puede contener llaves literales.

    Returns:
        Cadena con las llaves escapadas.
    """
    if not texto:
        return texto
    return texto.replace("{", "{{").replace("}", "}}")


@lru_cache(maxsize=32)
def construir_prompt_template_cacheado(prompt_sistema: str) -> ChatPromptTemplate:
    """
    Construye (con caché) el ChatPromptTemplate de un agente a partir de su prompt de sistema.

    Los agentes reconstruyen el template en cada iteración de su bucle aunque el
    prompt de sistema sea idéntico (el LLM reenvía el contexto, pero el parseo y
    la compilación del template son trabajo redundante). Al cachear por el hash
    natural del string (lru_cache usa los argumentos como clave), las iteraciones
    con el mismo prompt de sistema reutilizan la instancia compilada.

    IMPORTANTE (ahorro de tokens): el reenvío del contexto a la API del LLM es
    inevitable (las APIs son sin estado); esta caché elimina el trabajo CPU
    redundante local. El ahorro real de tokens lo aporta `aplicar_resumen_middleware`.

    Args:
        prompt_sistema: Contenido completo del prompt de sistema del agente (str).

    Returns:
        ChatPromptTemplate: Template compilado con placeholder "messages".
    """
    return ChatPromptTemplate.from_messages([
        ("system", prompt_sistema),
        MessagesPlaceholder(variable_name="messages"),
    ])