"""
Helpers puros de revisión para el Agente Revisor.

Este módulo extrae la lógica inline de detección (errores en mensajes,
verificación de si el plan requiere pruebas, comandos duplicados y
aprobación por texto) a funciones puras, sin dependencias de LangChain ni
del grafo LangGraph, para permitir pruebas unitarias aisladas.

Todas las funciones reciben estructuras de datos simples (dicts, listas de
objetos con atributo ``content``, cadenas) y no tienen efectos secundarios.
"""

from typing import Any, List, Optional

# Patrones de error buscados en el contenido de los mensajes (en minúsculas).
_PATRONES_ERROR: tuple = (
    "error",
    "traceback",
    "failed",
    "exception",
)

# Palabras/frases de aprobación buscadas en respuestas de texto (en minúsculas).
_PALABRAS_APROBACION: tuple = (
    "aprobado",
    "correcto",
    "sin errores",
    "paso las pruebas",
    "pasó las pruebas",
    "todo bien",
    "exitoso",
    "funciona correctamente",
    "no requiere",
)


def plan_requiere_pruebas(plan_de_accion: Optional[dict]) -> bool:
    """
    Determina si un plan de acción requiere ejecutar pruebas.

    Retorna ``True`` si el plan existe y contiene al menos un paso con la
    clave ``requiere_test`` igual a ``True``. También retorna ``True`` si el
    plan CONTIENE la clave ``"pasos"`` pero con lista vacía: un plan sin
    pasos no puede aprobarse automáticamente y debe pasar por revisión
    (preserva la semántica original: solo se aprueba automáticamente si hay
    pasos Y todos tienen ``requiere_test=False``).

    Casos manejados de forma segura:
    - plan ``None`` o no-dict => ``False``
    - dict sin clave ``"pasos"`` => ``False``
    - dict con ``"pasos"`` vacío (``[]``) => ``True`` (requiere revisión)
    - dict con ``"pasos"`` que no es lista => ``False``
    - ``requiere_test`` ausente o con valor no booleano no cuenta como ``True``

    Args:
        plan_de_accion: Diccionario del plan con clave ``"pasos"`` (lista de
            dicts), o ``None``.

    Returns:
        ``True`` si al menos un paso requiere pruebas o si el plan contiene
        la clave ``"pasos"`` con lista vacía; ``False`` en caso contrario.
    """
    if not isinstance(plan_de_accion, dict):
        return False

    pasos = plan_de_accion.get("pasos")
    if not isinstance(pasos, list):
        return False
    if not pasos:
        # Clave 'pasos' presente pero lista vacía: NO hay pasos que aprobar
        # automáticamente -> requiere revisión.
        return True

    for paso in pasos:
        if isinstance(paso, dict) and paso.get("requiere_test") is True:
            return True

    return False


def detectar_errores_en_mensajes(messages: list) -> str:
    """
    Busca patrones de error en el contenido de los mensajes.

    Recorre los mensajes (objetos con atributo ``content``) y retorna el
    contenido del primer mensaje que contenga patrones de error
    (``'Error'``, ``'Traceback'``, ``'FAILED'``, ``'Exception'``,
    ``'error:'``) o cadena vacía si no hay errores. Maneja ``content``
    ``None`` y mensajes sin atributo ``content``.

    Args:
        messages: Lista de mensajes (objetos con atributo ``content``).

    Returns:
        Contenido del primer mensaje con errores, o ``""`` si no hay.
    """
    for mensaje in messages:
        content = getattr(mensaje, "content", None)
        if content is None:
            continue
        content_str = str(content)
        contenido_minusculas = content_str.lower()
        # Neutralizar la frase "sin errores" para evitar el falso positivo
        # donde el patrón 'error' matchea dentro de dicha subcadena.
        contenido_minusculas = contenido_minusculas.replace("sin errores", "")
        for patron in _PATRONES_ERROR:
            if patron in contenido_minusculas:
                return content_str
    return ""


def detectar_comando_duplicado(messages: list, comando: str) -> bool:
    """
    Detecta si un comando de terminal ya fue ejecutado previamente.

    Retorna ``True`` si el comando ya aparece en el ``content`` de algún
    mensaje previo o en los argumentos de una ``tool_call`` de terminal de
    un ``AIMessage`` previo (para evitar bucles de comandos repetidos).
    Maneja ``content`` ``None`` y mensajes sin atributo ``content``.

    Args:
        messages: Lista de mensajes previos del historial.
        comando: Representación del comando a buscar (p.ej. el string de
            los argumentos de la tool_call: ``str(args)``).

    Returns:
        ``True`` si el comando ya aparece en el historial; ``False`` si no.
    """
    if not comando:
        return False

    for mensaje in messages:
        # 1. Buscar en el content del mensaje.
        content = getattr(mensaje, "content", None)
        if content is not None and comando in str(content):
            return True

        # 2. Buscar en tool_calls de AIMessage (comandos de terminal previos).
        tool_calls = getattr(mensaje, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                if tc.get("name") == "terminal" and comando in str(tc.get("args")):
                    return True

    return False


def es_respuesta_aprobatoria(texto: str) -> bool:
    """
    Determina si un texto de respuesta del LLM sugiere aprobación.

    Retorna ``True`` si el texto (en minúsculas) contiene alguna palabra o
    frase de aprobación (``'aprobado'``, ``'correcto'``, ``'sin errores'``,
    ``'paso las pruebas'``, ``'todo bien'``, ``'exitoso'``,
    ``'funciona correctamente'``). Maneja texto ``None`` o vacío.

    Args:
        texto: Contenido de la respuesta del LLM.

    Returns:
        ``True`` si el texto sugiere aprobación; ``False`` en caso contrario.
    """
    if not texto:
        return False

    texto_minusculas = str(texto).lower()
    for palabra in _PALABRAS_APROBACION:
        if palabra in texto_minusculas:
            return True
    return False