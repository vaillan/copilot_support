"""
Mecanismo de regeneración de pruebas tras un cambio completado en disco (anti-bucle).

Evalúa, al completarse el bloque `CodigoCompletado` del agente codificador, si debe
exigirse la actualización/creación de pruebas unitarias para los archivos modificados.

Garantías anti-bucle:
  1. Los archivos bajo directorios excluidos (por defecto `tests/`) NUNCA disparan
     la regeneración: las salidas del propio mecanismo no lo re-disparan.
  2. Solo se dispara ante cambios REALES verificados por hash SHA-256 del contenido.
  3. Cooldown (debounce) configurable entre regeneraciones consecutivas.
  4. Tope máximo de regeneraciones por tarea; al alcanzarlo el mecanismo se detiene.
  5. Nunca lanza excepciones: ante cualquier fallo devuelve "no disparar".
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage

from app.settings.settings import Settings

# Instancia de módulo (mismo patrón que app/utils/files.py); permite monkeypatch en tests.
settings = Settings()

# Herramientas que realizan una escritura física en disco.
# Duplicado localmente para evitar importación circular con agente_codificador.py.
_HERRAMIENTAS_MODIFICACION = {"write_file", "edit_file", "copy_file", "move_file", "file_delete"}


def calcular_hash_archivo(ruta: Path) -> str:
    """
    Calcula el hash SHA-256 del contenido de un archivo.

    Args:
        ruta: Ruta del archivo (Path).

    Returns:
        str: Hash hexadecimal de 64 caracteres, o cadena vacía si el archivo no
        existe o ocurre un OSError (nunca lanza excepción).
    """
    try:
        if not ruta.is_file():
            return ""
        return hashlib.sha256(ruta.read_bytes()).hexdigest()
    except OSError:
        return ""


def _es_ruta_excluida(ruta_relativa: str, directorios_excluidos: tuple[str, ...]) -> bool:
    """
    Determina si una ruta relativa pertenece a alguno de los directorios excluidos.

    Comprueba si algún componente de la ruta coincide con un directorio excluido,
    cubriendo tanto `tests/test_x.py` como `app/tests/y.py`.

    Args:
        ruta_relativa: Ruta relativa del archivo (str).
        directorios_excluidos: Tupla de nombres de directorio excluidos (tuple[str, ...]).

    Returns:
        bool: True si la ruta está excluida; False si la tupla está vacía o no coincide.
    """
    if not directorios_excluidos:
        return False
    partes = Path(ruta_relativa).parts
    return any(parte in directorios_excluidos for parte in partes)


def _extraer_ruta_de_args(nombre_herramienta: str, args: dict[str, Any]) -> str:
    """
    Extrae la ruta del archivo objetivo desde los argumentos de una tool_call.

    Args:
        nombre_herramienta: Nombre de la herramienta de modificación (str).
        args: Diccionario de argumentos de la tool_call (dict).

    Returns:
        str: Ruta relativa extraída, o cadena vacía si no se encuentra.
    """
    if nombre_herramienta in ("copy_file", "move_file"):
        origen = args.get("source_path") or args.get("source") or ""
        destino = args.get("destination_path") or args.get("destination") or args.get("dest") or ""
        # Priorizar el destino: es donde queda el contenido modificado.
        return str(destino or origen)
    return str(args.get("file_path") or args.get("path") or "")


def _extraer_archivos_modificados(msgs: list[AnyMessage], respuesta: AIMessage) -> list[str]:
    """
    Extrae las rutas de archivos modificados desde las tool_calls del historial y la respuesta.

    Args:
        msgs: Historial de mensajes del estado (list[AnyMessage]); puede ser None o vacío.
        respuesta: AIMessage actual del codificador (AIMessage).

    Returns:
        list[str]: Rutas relativas sin duplicados, preservando el orden de aparición.
    """
    rutas: list[str] = []
    vistos: set[str] = set()
    candidatos = list(msgs or []) + [respuesta]
    for mensaje in candidatos:
        # Duck-typing: solo se requiere el atributo tool_calls (facilita el testeo
        # con dobles de prueba y tolera mensajes de otros tipos).
        tool_calls = getattr(mensaje, "tool_calls", None)
        if not tool_calls:
            continue
        for tc in tool_calls:
            if tc.get("name") not in _HERRAMIENTAS_MODIFICACION:
                continue
            args = tc.get("args")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError, ValueError):
                    args = {}
            if not isinstance(args, dict):
                args = {}
            ruta = _extraer_ruta_de_args(str(tc.get("name")), args)
            if ruta and ruta not in vistos:
                vistos.add(ruta)
                rutas.append(ruta)
    return rutas


def _resultado(
    disparar: bool,
    archivos: list[str],
    razon: str,
    hashes: dict[str, str],
    last_ts: float,
) -> dict[str, Any]:
    """Construye el diccionario de resultado con la estructura uniforme del evaluador."""
    return {
        "disparar": disparar,
        "archivos_modificados": archivos,
        "razon": razon,
        "hashes_actualizados": hashes,
        "last_ts": last_ts,
    }


def evaluar_regeneracion_tests(
    directorio: str,
    msgs: list[AnyMessage],
    respuesta: AIMessage,
    estado: dict,
) -> dict[str, Any]:
    """
    Evalúa si debe dispararse la regeneración de pruebas tras un cambio completado.

    Orden de evaluación (cortocircuito en el primer "no disparar"):
      1. Mecanismo deshabilitado por configuración.
      2. Sin archivos modificados fuera de los directorios excluidos.
      3. Sin cambios reales (todos los hashes coinciden con los conocidos).
      4. Cooldown activo (escrituras múltiples en menos de COOLDOWN_SECONDS).
      5. Tope de iteraciones alcanzado (MAX_ITERATIONS).
      6. Disparar.

    Args:
        directorio: Directorio raíz del proyecto (str).
        msgs: Historial de mensajes del estado (list[AnyMessage]).
        respuesta: AIMessage actual del codificador (AIMessage).
        estado: Estado global del grafo (dict); usa las claves
            `test_regeneration_hashes`, `test_regeneration_last_ts` y
            `test_regeneration_count`.

    Returns:
        dict[str, Any]: {"disparar": bool, "archivos_modificados": list[str],
        "razon": str, "hashes_actualizados": dict[str, str], "last_ts": float}.
    """
    try:
        if not settings.TEST_REGENERATION_ENABLED:
            return _resultado(False, [], "deshabilitado", {}, 0.0)

        excluidos = tuple(
            d.strip() for d in str(settings.TEST_REGENERATION_EXCLUDED_DIRS).split(",") if d.strip()
        )
        archivos = [
            r for r in _extraer_archivos_modificados(msgs, respuesta)
            if not _es_ruta_excluida(r, excluidos)
        ]
        if not archivos:
            return _resultado(False, [], "sin_archivos", {}, 0.0)

        base = Path(directorio).resolve() if directorio else Path.cwd()
        hashes_actuales = {ruta: calcular_hash_archivo(base / ruta) for ruta in archivos}
        hashes_previos = estado.get("test_regeneration_hashes") or {}
        # Cambio real = el archivo EXISTE en disco (hash no vacío) Y su hash difiere
        # del conocido. Un archivo inexistente/borrado (hash "") nunca dispara la
        # regeneración: no hay contenido nuevo que probar.
        cambios_reales = {
            ruta: h for ruta, h in hashes_actuales.items()
            if h and hashes_previos.get(ruta) != h
        }
        if not cambios_reales:
            return _resultado(False, archivos, "sin_cambios_reales", hashes_actuales, 0.0)

        ultima = float(estado.get("test_regeneration_last_ts") or 0.0)
        if time.time() - ultima < settings.TEST_REGENERATION_COOLDOWN_SECONDS:
            return _resultado(False, archivos, "cooldown", hashes_actuales, 0.0)

        contador = int(estado.get("test_regeneration_count") or 0)
        if contador >= settings.TEST_REGENERATION_MAX_ITERATIONS:
            return _resultado(False, archivos, "tope_alcanzado", hashes_actuales, 0.0)

        return _resultado(True, archivos, "ok", hashes_actuales, time.time())
    except Exception:
        # Tolerancia a fallos: ante cualquier error inesperado, no disparar y no colgar el flujo.
        return _resultado(False, [], "error_interno", {}, 0.0)
