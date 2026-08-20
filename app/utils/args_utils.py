"""
Utilidades para parsear de forma segura los argumentos de las tool_calls.

El LLM (p.ej. deepseek) puede devolver `tool_call["args"]` como un `dict`
o como un STRING JSON. Este helper normaliza ambos casos para evitar el bug
bloqueante `'str' object has no attribute 'get'`.
"""

import json
from typing import Any, Dict


def _get_args(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae los argumentos de una tool_call de forma segura.

    - Si `args` es un dict, lo devuelve tal cual.
    - Si `args` es un str, intenta `json.loads(args)` y devuelve el dict resultante.
    - Si el parseo falla (o el tipo no es dict/str), devuelve `{}`.

    Args:
        tool_call: Diccionario de la tool_call (debe contener la clave 'args').

    Returns:
        Dict con los argumentos parseados (nunca None).
    """
    args = tool_call.get("args", {})
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except Exception:
            return {}
    return {}