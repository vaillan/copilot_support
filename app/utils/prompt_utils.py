"""
Utilidades para la construcción segura de prompts.

Evita que el contenido dinámico (índice del proyecto, errores de terminal,
tracebacks, etc.) que contiene llaves literales de código fuente (ej.
`Dict[str, Any]`, `{directorio}`) sea interpretado por `ChatPromptTemplate`
como variables de plantilla al invocar `.format()`.
"""


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