"""Tool de terminal compartida por los agentes (Revisor y Codificador).

Extrae la tool ``terminal`` que antes vivía privada en
``app/agents/agente_revisor.py`` para que el Agente Codificador también pueda
ejecutar comandos (p. ej. ``pytest``) y auto-validar los tests antes de
entregar el código. Esto elimina la fuente del bucle de rechazo QA →
codificador por tests sin validar.

Garantías de seguridad (inalteradas): los comandos se ejecutan únicamente
dentro del directorio del proyecto (cwd), se filtran patrones peligrosos vía
``app.utils.shell_safety.validar_comando`` y hay un timeout configurable por
comando (``TERMINAL_TIMEOUT_SECONDS``).
"""

import os
import subprocess
import sys
from typing import Optional

from langchain_core.tools import tool

from app.settings.settings import Settings
from app.utils.shell_safety import validar_comando

settings = Settings()

# Directorio del proyecto actual, propagado desde state["directorio_proyecto"]
# vía configurar_directorio(). Se usa como cwd por defecto en la tool terminal().
_ACTUAL_DIRECTORIO_PROYECTO: str = os.getcwd()


def configurar_directorio(directorio: str) -> None:
    """Fija el directorio de trabajo por defecto de la tool terminal.

    Args:
        directorio: Ruta del directorio del proyecto. Solo se aplica si existe
            y es accesible.
    """
    global _ACTUAL_DIRECTORIO_PROYECTO
    if directorio and os.path.isdir(directorio):
        _ACTUAL_DIRECTORIO_PROYECTO = directorio


def _detectar_shell() -> str:
    """Detecta el shell o comando del sistema operativo actual.

    Returns:
        str: Nombre descriptivo del shell detectado ("Windows (cmd.exe)",
            "macOS (shell POSIX)" o "Linux/Unix (shell POSIX)").
    """
    if sys.platform == "win32":
        return "Windows (cmd.exe)"
    if sys.platform == "darwin":
        return "macOS (shell POSIX)"
    return "Linux/Unix (shell POSIX)"


@tool
def terminal(commands: list[str] | str, cwd: Optional[str] = None) -> str:
    """Ejecuta comandos en la terminal del proyecto con confinamiento de directorio.

    Pasa una lista de comandos o una cadena de comando (ej. "pytest" o ["pytest"]).
    El parámetro opcional `cwd` fuerza un directorio de trabajo concreto; si se
    omite (None), se usa el directorio del proyecto actual.

    Garantías de seguridad: los comandos se ejecutan únicamente dentro del
    directorio del proyecto (cwd), se filtran patrones peligrosos (borrado
    destructivo, descarga+ejecución, git destructivo, variables críticas, rutas
    sensibles, fork bombs, shutdown) antes de ejecutarse, y hay un timeout
    configurable por comando.

    Advertencia: NO es un sandbox real del sistema operativo. En entornos de
    producción o compartidos el uso de esta herramienta debe estar restringido
    y supervisado, ya que un comando permitido aún puede modificar archivos
    dentro del proyecto o consumir recursos del host.

    Args:
        commands (list[str] | str): Lista de comandos o cadena de comando a ejecutar.
        cwd (str | None): Directorio de trabajo concreto; por defecto None (se usa
            el directorio del proyecto actual).

    Returns:
        str: Salida formateada por comando con su código de salida, STDOUT/STDERR
            o mensajes de error/bloqueo.
    """
    if cwd is None:
        cwd = _ACTUAL_DIRECTORIO_PROYECTO
    if not os.path.isdir(cwd):
        return f"Error: El directorio de trabajo '{cwd}' no existe o no es accesible. Comandos no ejecutados."

    if isinstance(commands, str):
        lista_comandos = [commands]
    elif isinstance(commands, list):
        lista_comandos = commands
    else:
        return "Error: Formato de comandos inválido. Proporciona una cadena o lista de cadenas."

    resultados = []
    shell_detectado = _detectar_shell()
    for cmd in lista_comandos:
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        permitido, motivo_bloqueo = validar_comando(cmd, cwd)
        if not permitido:
            resultados.append(f"$ {cmd}\n🚨 Comando bloqueado: {motivo_bloqueo}")
            continue
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.TERMINAL_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL
            )
            stdout = res.stdout.strip() if res.stdout else ""
            stderr = res.stderr.strip() if res.stderr else ""
            salida = []
            if stdout:
                salida.append(f"STDOUT:\n{stdout}")
            if stderr:
                salida.append(f"STDERR:\n{stderr}")
            if not salida:
                salida.append(f"Comando '{cmd}' ejecutado con código de salida {res.returncode} (sin salida).")
            resultados.append(f"$ {cmd}\nCódigo de salida: {res.returncode}\n" + "\n".join(salida))
        except subprocess.TimeoutExpired:
            resultados.append(f"$ {cmd}\n🚨 Timeout: El comando excedió el tiempo límite de {settings.TERMINAL_TIMEOUT_SECONDS} segundos.")
        except BaseException as e:
            mensaje_error = str(e)
            if "not recognized" in mensaje_error.lower() or "command not found" in mensaje_error.lower() or "is not recognized" in mensaje_error.lower():
                resultados.append(
                    f"$ {cmd}\n🚨 Error al ejecutar comando: {mensaje_error}\n"
                    f"Shell detectado: {shell_detectado}. El comando puede no ser compatible con esta plataforma."
                )
            else:
                resultados.append(f"$ {cmd}\n🚨 Error al ejecutar comando ({shell_detectado}): {mensaje_error}")

    return "\n\n---\n\n".join(resultados) if resultados else "No se ejecutaron comandos válidos."
