"""Utilidades de Git para el servidor MCP.

Este módulo contiene la función pura (sin dependencia del grafo LangGraph)
encargada de obtener el diff de git o los archivos modificados en un directorio,
de forma segura y tolerante a fallos.
"""

import os
import subprocess


def obtener_git_diff(directorio: str) -> str:
    """Intenta obtener el diff de git o los archivos modificados en el directorio especificado."""
    if not directorio or not os.path.exists(directorio):
        return ""
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
            return res.stdout.strip()

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