"""Utilidades de Git para el servidor MCP.

Este módulo contiene la función pura (sin dependencia del grafo LangGraph)
encargada de obtener el diff de git o los archivos modificados en un directorio,
de forma segura y tolerante a fallos.
"""

import os
import re
import subprocess
from typing import Optional

from app.settings.settings import Settings

settings = Settings()

_MAX_TAMANO_ARCHIVO_DIFF = 1024 * 1024


def _es_seccion_binaria(seccion: str) -> bool:
    """Devuelve True si la sección del diff corresponde a un archivo binario."""
    return any(
        linea.startswith("Binary files ") or linea.startswith("GIT binary patch")
        for linea in seccion.splitlines()
    )


def _tamano_seccion(seccion: str, directorio: str, max_bytes: int) -> int:
    """Estima el tamaño de la sección del diff en bytes.

    Si el archivo modificado existe en disco, se usa su tamaño real
    (``os.path.getsize``); en cualquier otro caso (directorio vacío, ruta no
    encontrada, archivo inexistente o error de lectura) se usa la longitud de
    la propia sección como fallback.
    """
    match = re.search(r"^diff --git a/(\S+) b/", seccion, flags=re.MULTILINE)
    if match and directorio:
        ruta = os.path.join(directorio, match.group(1))
        if os.path.isfile(ruta):
            try:
                return os.path.getsize(ruta)
            except Exception:
                pass
    return len(seccion)


def _filtrar_diff(
    diff: str,
    directorio: str = "",
    max_bytes: int = _MAX_TAMANO_ARCHIVO_DIFF,
) -> str:
    """Filtra un diff de git descartando secciones binarias o demasiado grandes."""
    if not diff or not diff.strip():
        return ""
    secciones = []
    inicio = None
    for match in re.finditer(r"^diff --git ", diff, flags=re.MULTILINE):
        if inicio is not None:
            secciones.append(diff[inicio : match.start()])
        inicio = match.start()
    if inicio is not None:
        secciones.append(diff[inicio:])
    if not secciones:
        return diff.strip()
    secciones_filtradas = [
        seccion
        for seccion in secciones
        if not _es_seccion_binaria(seccion)
        and _tamano_seccion(seccion, directorio, max_bytes) <= max_bytes
    ]
    if not secciones_filtradas:
        return diff.strip()
    return "\n".join(secciones_filtradas).strip()


def obtener_git_diff(directorio: str, max_bytes_por_archivo: Optional[int] = None) -> str:
    """Intenta obtener el diff de git o los archivos modificados en el directorio especificado."""
    if not directorio or not os.path.exists(directorio):
        return ""
    max_bytes = max_bytes_por_archivo or int(
        getattr(settings, "GIT_DIFF_MAX_FILE_SIZE", _MAX_TAMANO_ARCHIVO_DIFF)
    )
    try:
        res = subprocess.run(
            ["git", "diff"],
            cwd=directorio,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if res.returncode == 0 and res.stdout.strip():
            return _filtrar_diff(res.stdout.strip(), directorio=directorio, max_bytes=max_bytes)

        res_stat = subprocess.run(
            ["git", "status", "-s"],
            cwd=directorio,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if res_stat.returncode == 0 and res_stat.stdout.strip():
            stdout_clean = res_stat.stdout.strip()
            return f"Archivos modificados/creados (git status):\n{stdout_clean}"
    except Exception:
        pass
    return ""