"""
Herramienta de terminal segura para el Agente Revisor.

Este módulo extrae la herramienta ``terminal`` del agente revisor a un helper
puro y reutilizable, añadiendo medidas de seguridad:

- **Whitelist de comandos**: solo se permiten prefijos de comandos seguros
  (pytest, python, pip, git status/diff/log, ls, cat, find, grep, echo, mkdir,
  touch, cp, mv, ``rm`` restringido a archivos dentro del proyecto, php,
  artisan, composer, go, mvn, java, javac, gradle, npm, node, jest, npx y
  cargo).
- **Anti-inyección**: se rechazan operadores de shell peligrosos
  (``;``, ``&&``, ``||``, ``|``, ``>``, ``<``, `` ` ``, ``$(``).
- **Restricción del directorio de trabajo**: el comando se ejecuta con
  ``cwd`` fijado a un directorio existente y resuelto.
- **Límite de salida**: la salida se trunca a 4000 caracteres para evitar
  saturar el contexto del LLM.
- **Timeout configurable**: evita procesos colgados.

Todas las funciones auxiliares son puras (sin dependencias de LangChain ni
del grafo) para permitir pruebas unitarias aisladas.
"""

import shlex
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from langchain_core.tools import tool
from app.settings.settings import Settings

# Instancia module-level de configuración (patrón de project_index.py).
# settings.py no importa terminal.py, por lo que no hay ciclo de import.
settings = Settings()

# Prefijos de comandos seguros permitidos. Un comando es válido si coincide
# exactamente con un prefijo o si comienza con el prefijo seguido de un
# espacio (para evitar falsos positivos como 'git statuses').
_VALIDAR_COMANDOS_PERMITIDOS: Tuple[str, ...] = (
    "pytest",
    "python",
    "python3",
    "pip",
    "pip3",
    "git status",
    "git diff",
    "git log",
    "ls",
    "cat",
    "find",
    "grep",
    "echo",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
    # Laravel/PHP
    "php",
    "artisan",
    "composer",
    # Go
    "go",
    # Java
    "mvn",
    "java",
    "javac",
    "gradle",
    # Node.js
    "npm",
    "node",
    "jest",
    "npx",
    # Cargo/Rust
    "cargo",
)

# Operadores/constructores de shell que indican posible inyección de comandos.
# Se rechazan incluso si aparecen dentro de comillas: la seguridad prima sobre
# la comodidad (un falso positivo es preferible a una inyección).
_OPERADORES_PELIGROSOS: Tuple[str, ...] = (
    ";",
    "&&",
    "||",
    "|",
    ">",
    "<",
    "`",
    "$(",
)

# Flags de 'rm' que no representan rutas (se ignoran al validar rutas).
_FLAGS_RM: Tuple[str, ...] = (
    "-r",
    "-f",
    "-rf",
    "-fr",
    "-i",
    "-v",
    "-d",
    "-R",
    "--recursive",
    "--force",
    "--verbose",
    "--dir",
    "--interactive",
)

# Límite por defecto de caracteres de salida.
_MAX_SALIDA_DEFAULT: int = 4000

# Límite por defecto de líneas de salida conservadas.
_MAX_SALIDA_LINEAS_DEFAULT: int = 200

# Límite por defecto de caracteres por línea de salida.
_MAX_CARACTERES_POR_LINEA_DEFAULT: int = 500

# Timeout por defecto en segundos.
_TIMEOUT_DEFAULT: int = 30


def _validar_comando(comando: str) -> Tuple[bool, str]:
    """
    Valida que un comando sea seguro para ejecutar.

    Retorna ``(True, '')`` si el comando comienza con un prefijo permitido y
    no contiene operadores de shell peligrosos; en caso contrario retorna
    ``(False, mensaje_de_error)``.

    Args:
        comando: Cadena de comando a validar (p.ej. ``"pytest tests/"``).

    Returns:
        Tupla ``(valido, mensaje_error)``.
    """
    if not comando or not comando.strip():
        return False, "Error: El comando está vacío."

    comando_normalizado = comando.strip()

    # 1. Rechazar operadores de shell que permitan encadenar/redirigir comandos.
    for op in _OPERADORES_PELIGROSOS:
        if op in comando_normalizado:
            return False, (
                f"Error: El comando contiene el operador '{op}' que no está "
                "permitido para prevenir inyección de comandos."
            )

    # 2. Verificar que el comando coincida con un prefijo permitido.
    for prefijo in _VALIDAR_COMANDOS_PERMITIDOS:
        if comando_normalizado == prefijo or comando_normalizado.startswith(prefijo + " "):
            # 3. Regla especial para 'rm': solo archivos dentro del proyecto.
            if prefijo == "rm":
                valido_rm, error_rm = _validar_rutas_rm(comando_normalizado)
                if not valido_rm:
                    return False, error_rm
            return True, ""

    return False, (
        f"Error: El comando '{comando_normalizado}' no está en la whitelist "
        "de comandos permitidos."
    )


def _validar_rutas_rm(comando: str) -> Tuple[bool, str]:
    """
    Valida que las rutas de un comando ``rm`` no sean absolutas ni contengan
    ``..`` (path traversal), restringiendo su uso a archivos relativos.

    Args:
        comando: Comando ``rm`` completo (p.ej. ``"rm -rf build/"``).

    Returns:
        Tupla ``(valido, mensaje_error)``.
    """
    try:
        argumentos = shlex.split(comando)
    except ValueError as e:
        return False, f"Error: No se pudo parsear el comando 'rm': {str(e)}"

    for arg in argumentos[1:]:
        if arg.startswith("-") or arg in _FLAGS_RM:
            continue
        if arg == "/" or arg.startswith("/") or ".." in arg:
            return False, (
                f"Error: 'rm' solo puede operar sobre archivos dentro del "
                f"directorio del proyecto: '{arg}'."
            )
    return True, ""


def _limitar_salida(
    salida: str,
    max_chars: int = _MAX_SALIDA_DEFAULT,
    max_lineas: Optional[int] = None,
    max_caracteres_por_linea: Optional[int] = None,
) -> str:
    """
    Trunca la salida por líneas, por caracteres por línea y por caracteres.

    El orden de aplicación es: (1) límite de líneas, (2) límite de caracteres
    por línea y (3) límite global de caracteres. Con ``max_lineas=None`` y
    ``max_caracteres_por_linea=None`` el comportamiento es exactamente el
    original (solo el cap ``max_chars``), preservando la retrocompatibilidad.

    Args:
        salida: Salida cruda del comando.
        max_chars: Número máximo de caracteres totales a conservar.
        max_lineas: Número máximo de líneas a conservar (``None`` = sin límite).
        max_caracteres_por_linea: Número máximo de caracteres por línea
            (``None`` = sin límite).

    Returns:
        Salida truncada (o la original si no excede los límites).
    """
    if not salida:
        return ""

    # 1. Límite de líneas.
    if max_lineas is not None:
        lineas = salida.splitlines()
        if max_lineas <= 0:
            lineas = []
        elif len(lineas) > max_lineas:
            omitidas = len(lineas) - max_lineas
            lineas = lineas[:max_lineas]
            lineas.append(f"[lineas restantes omitidas: {omitidas}]")
        salida = "\n".join(lineas)

    # 2. Límite de caracteres por línea.
    if max_caracteres_por_linea is not None:
        if max_caracteres_por_linea <= 0:
            salida = ""
        else:
            lineas = salida.splitlines()
            lineas = [
                # El marcador de líneas omitidas es información crítica de
                # resumen y debe conservarse intacto (no se trunca ni se le
                # añade el sufijo '[...]').
                linea
                if linea.startswith("[lineas restantes omitidas:")
                else (
                    linea[:max_caracteres_por_linea] + "[...]"
                    if len(linea) > max_caracteres_por_linea
                    else linea
                )
                for linea in lineas
            ]
            salida = "\n".join(lineas)

    # 3. Límite global de caracteres.
    if len(salida) > max_chars:
        salida = salida[:max_chars] + "[...salida truncada...]"

    return salida


def _ejecutar_comando(comando: str, directorio: str, timeout: int = _TIMEOUT_DEFAULT) -> str:
    """
    Ejecuta un comando de forma segura (``shell=False``) y retorna su salida.

    Usa ``shlex.split`` para convertir la cadena en una lista de argumentos y
    ``subprocess.run`` con ``shell=False``, ``cwd=directorio`` y
    ``capture_output=True``. Retorna stdout+stderr combinados o un mensaje de
    error controlado en caso de timeout, ejecutable no encontrado o excepción
    genérica.

    Args:
        comando: Cadena de comando a ejecutar.
        directorio: Directorio de trabajo (cwd) para el subproceso.
        timeout: Tiempo límite de ejecución en segundos.

    Returns:
        Salida combinada (stdout+stderr) o mensaje de error controlado.
    """
    try:
        argumentos = shlex.split(comando)
        if not argumentos:
            return f"$ {comando}\nError: No se pudo parsear el comando en argumentos."

        res = subprocess.run(
            argumentos,
            shell=False,
            cwd=directorio,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        stdout = res.stdout.strip() if res.stdout else ""
        stderr = res.stderr.strip() if res.stderr else ""
        salida = []
        if stdout:
            salida.append(f"STDOUT:\n{stdout}")
        if stderr:
            salida.append(f"STDERR:\n{stderr}")
        if not salida:
            salida.append(
                f"Comando '{comando}' ejecutado con código de salida "
                f"{res.returncode} (sin salida)."
            )
        return f"$ {comando}\nCódigo de salida: {res.returncode}\n" + "\n".join(salida)

    except subprocess.TimeoutExpired:
        return (
            f"$ {comando}\n🚨 Timeout: El comando '{comando}' excedió el "
            f"tiempo límite de {timeout} segundos."
        )
    except FileNotFoundError as e:
        return f"$ {comando}\n🚨 Error: No se encontró el ejecutable del comando: {str(e)}"
    except BaseException as e:  # noqa: BLE001 - error controlado para el LLM
        return f"$ {comando}\n🚨 Error al ejecutar comando: {str(e)}"


@tool
def terminal(comando: str, directorio: str = ".") -> str:
    """
    Ejecuta un comando seguro en la terminal del proyecto.

    Solo se permiten comandos de la whitelist (pytest, python, pip, git
    status/diff/log, ls, cat, find, grep, echo, mkdir, touch, cp, mv, rm
    restringido a archivos del proyecto, php, artisan, composer, go, mvn,
    java, javac, gradle, npm, node, jest, npx y cargo). Se rechazan operadores
    de shell peligrosos (;, &&, ||, |, >, <, `, $()).

    Args:
        comando: Comando a ejecutar (p.ej. "pytest tests/").
        directorio: Directorio de trabajo del proyecto (por defecto '.').

    Returns:
        Salida del comando (limitada a 4000 caracteres) o mensaje de error.
    """
    # 1. Validar el comando contra la whitelist y operadores peligrosos.
    valido, mensaje_error = _validar_comando(comando)
    if not valido:
        return mensaje_error

    # 2. Resolver y verificar el directorio de trabajo.
    try:
        ruta_directorio = Path(directorio).resolve()
    except BaseException as e:  # noqa: BLE001 - error controlado
        return f"Error: No se pudo resolver el directorio '{directorio}': {str(e)}"

    if not ruta_directorio.exists() or not ruta_directorio.is_dir():
        return (
            f"Error: El directorio '{directorio}' no existe o no es un "
            "directorio válido."
        )

    # 3. Validación adicional para 'rm': las rutas deben resolverse dentro
    #    del directorio del proyecto (protección contra path traversal).
    if comando.strip().startswith("rm"):
        valido_rm, error_rm = _validar_rutas_rm_dentro_de(comando, ruta_directorio)
        if not valido_rm:
            return error_rm

    # 4. Ejecutar con timeout y limitar la salida.
    salida = _ejecutar_comando(comando, str(ruta_directorio), timeout=_TIMEOUT_DEFAULT)
    return _limitar_salida(
        salida,
        max_lineas=int(
            getattr(settings, "TERMINAL_MAX_OUTPUT_LINES", _MAX_SALIDA_LINEAS_DEFAULT)
        ),
        max_caracteres_por_linea=int(
            getattr(settings, "TERMINAL_MAX_CHARS_PER_LINE", _MAX_CARACTERES_POR_LINEA_DEFAULT)
        ),
    )


def _validar_rutas_rm_dentro_de(comando: str, directorio: Path) -> Tuple[bool, str]:
    """
    Verifica que las rutas relativas de un comando ``rm`` se resuelvan dentro
    del directorio del proyecto (protección contra ``..`` y symlinks).

    Args:
        comando: Comando ``rm`` completo.
        directorio: Directorio base del proyecto (resuelto).

    Returns:
        Tupla ``(valido, mensaje_error)``.
    """
    try:
        argumentos = shlex.split(comando)
    except ValueError as e:
        return False, f"Error: No se pudo parsear el comando 'rm': {str(e)}"

    base_str = str(directorio)
    for arg in argumentos[1:]:
        if arg.startswith("-") or arg in _FLAGS_RM:
            continue
        ruta_resuelta = (directorio / arg).resolve()
        if not str(ruta_resuelta).startswith(base_str):
            return False, (
                f"Error: 'rm' solo puede operar sobre archivos dentro del "
                f"directorio del proyecto: '{arg}'."
            )
    return True, ""