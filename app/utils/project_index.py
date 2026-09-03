"""
Módulo de Índice de Proyecto con Caché Incremental.

Construye una representación compacta del proyecto (árbol de directorios +
resúmenes por archivo) para evitar que los agentes lean archivos completos
repetidamente y así ahorrar tokens en cada implementación.

El índice se persiste en disco y se invalida incrementalmente mediante
hashes de contenido (sha256 + mtime + tamaño), de modo que solo se
recalculan los archivos que realmente cambiaron.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.settings.settings import Settings
from app.utils.i18n import obtener_mensaje

settings = Settings()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

INDEX_VERSION = 1
INDEX_FILENAME = ".project_index.json"

# Directorios y archivos que nunca deben indexarse (basura / dependencias)
EXCLUDED_DIRS: Set[str] = {
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "vendor",
    ".git",
    ".next",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".project_index",
    "coverage",
    "htmlcov",
    ".tox",
    ".eggs",
    "*.egg-info",
}

EXCLUDED_FILES: Set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
    INDEX_FILENAME,
}

# Extensiones de archivos binarios o no textuales que se omiten
BINARY_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".pyc", ".pyo",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".db", ".sqlite", ".sqlite3", ".lock",
}

# Extensiones de archivos de código fuente que se resumen con detalle
CODE_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c",
    ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".ps1", ".sql", ".html", ".css", ".scss",
    ".sass", ".less", ".vue", ".svelte",
}

# Extensiones de configuración / datos que se resumen por claves
CONFIG_EXTENSIONS: Set[str] = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".xml", ".properties",
}

# Extensiones de documentación
DOC_EXTENSIONS: Set[str] = {
    ".md", ".rst", ".txt", ".adoc",
}


def _hash_archivo(ruta: Path) -> Dict[str, Any]:
    """Calcula sha256 + mtime + tamaño de un archivo para invalidación incremental."""
    stat = ruta.stat()
    mtime = int(stat.st_mtime)
    tamano = stat.st_size
    sha = ""
    try:
        with open(ruta, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
    except Exception:
        sha = ""
    return {"hash": sha, "mtime": mtime, "mtime_ns": stat.st_mtime_ns, "tamano": tamano}


def _leer_contenido_y_hash(ruta: Path) -> Tuple[str, Dict[str, Any]]:
    """Lee un archivo UNA sola vez en binario y devuelve su contenido + metadatos.

    Evita la doble lectura de disco que ocurría al llamar secuencialmente a
    `_hash_archivo` (lectura binaria para sha256) y a `resumir_archivo` (que
    releía el archivo en texto). Aquí se leen los bytes una única vez y se
    calculan simultáneamente el hash sha256, el mtime (segundos), el mtime_ns
    (nanosegundos, para detectar cambios dentro del mismo segundo) y el tamaño.

    Returns:
        Tupla (contenido, info_hash) donde `contenido` es el texto decodificado
        con utf-8 (errors='replace') e `info_hash` contiene las claves:
        'hash', 'mtime', 'mtime_ns' y 'tamano'.
    """
    with open(ruta, "rb") as f:
        datos = f.read()
    stat = ruta.stat()
    sha = hashlib.sha256(datos).hexdigest()
    contenido = datos.decode("utf-8", errors="replace")
    info_hash = {
        "hash": sha,
        "mtime": int(stat.st_mtime),
        "mtime_ns": stat.st_mtime_ns,
        "tamano": stat.st_size,
    }
    return contenido, info_hash


def _es_excluido(nombre: str, es_dir: bool) -> bool:
    """Determina si un nombre de archivo/directorio debe excluirse del índice."""
    if es_dir:
        return nombre in EXCLUDED_DIRS or nombre.endswith(".egg-info")
    if nombre in EXCLUDED_FILES:
        return True
    ext = Path(nombre).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return True
    # Archivos de bloqueo de dependencias por patrón
    if re.search(r"(lock|\.lock)$", nombre, re.IGNORECASE):
        return True
    return False


def _resumir_python(contenido: str, max_tokens: int) -> Dict[str, Any]:
    """Genera resumen de un archivo Python: docstrings, firmas, imports."""
    lineas = contenido.splitlines()
    imports: List[str] = []
    firmas: List[str] = []
    docstrings: List[str] = []
    clases: List[str] = []
    funciones: List[str] = []

    for i, linea in enumerate(lineas):
        linea_strip = linea.strip()
        if not linea_strip:
            continue
        if linea_strip.startswith(("import ", "from ")):
            imports.append(linea_strip)
        elif linea_strip.startswith(("def ", "async def ")):
            firmas.append(linea_strip[:120])
            funciones.append(linea_strip)
        elif linea_strip.startswith("class "):
            firmas.append(linea_strip[:120])
            clases.append(linea_strip)
        elif linea_strip.startswith('"""') or linea_strip.startswith("'''"):
            # Docstring de módulo/clase/función: capturar hasta 3 líneas
            bloque = [linea_strip]
            j = i + 1
            while j < len(lineas) and j < i + 4:
                bloque.append(lineas[j].strip())
                j += 1
            docstrings.append(" ".join(bloque)[:200])

    # Limitar a max_tokens aproximados (1 token ≈ 4 caracteres)
    limite_caracteres = max_tokens * 4

    resumen_parts: List[str] = []
    if imports:
        resumen_parts.append("IMPORTS:\n" + "\n".join(imports[:30]))
    if firmas:
        resumen_parts.append("FIRMAS:\n" + "\n".join(firmas[:40]))
    if docstrings:
        resumen_parts.append("DOCSTRINGS:\n" + "\n".join(docstrings[:10]))

    resumen = "\n\n".join(resumen_parts)
    if len(resumen) > limite_caracteres:
        resumen = resumen[:limite_caracteres] + "\n...[truncado]"

    return {
        "resumen": resumen,
        "imports": imports[:30],
        "firmas": firmas[:40],
        "clases": clases[:20],
        "funciones": funciones[:40],
    }


def _resumir_js_ts(contenido: str, max_tokens: int) -> Dict[str, Any]:
    """Genera resumen de archivos JS/TS: exports, firmas, imports."""
    lineas = contenido.splitlines()
    imports: List[str] = []
    firmas: List[str] = []

    for linea in lineas:
        linea_strip = linea.strip()
        if not linea_strip:
            continue
        if linea_strip.startswith(("import ", "export ", "const ", "function ", "class ")):
            if linea_strip.startswith(("import ", "export ")):
                firmas.append(linea_strip[:120])
            if linea_strip.startswith("import "):
                imports.append(linea_strip[:120])

    limite_caracteres = max_tokens * 4
    resumen_parts: List[str] = []
    if imports:
        resumen_parts.append("IMPORTS:\n" + "\n".join(imports[:30]))
    if firmas:
        resumen_parts.append("DECLARACIONES:\n" + "\n".join(firmas[:40]))

    resumen = "\n\n".join(resumen_parts)
    if len(resumen) > limite_caracteres:
        resumen = resumen[:limite_caracteres] + "\n...[truncado]"

    return {
        "resumen": resumen,
        "imports": imports[:30],
        "firmas": firmas[:40],
    }


def _resumir_config(contenido: str, max_tokens: int) -> Dict[str, Any]:
    """Genera resumen de archivos de configuración: claves de primer nivel."""
    claves: List[str] = []

    # Para JSON en una sola línea, extraer claves con regex
    if contenido.strip().startswith("{"):
        for m in re.finditer(r'"([^"]+)"\s*:', contenido):
            clave = m.group(1)
            if clave and clave not in claves:
                claves.append(clave[:80])
            if len(claves) >= 50:
                break

    if not claves:
        lineas = contenido.splitlines()
        for linea in lineas:
            linea_strip = linea.strip()
            if not linea_strip or linea_strip.startswith(("#", "//", "/*", "*")):
                continue
            # Capturar clave de primer nivel (antes de ':' o '=')
            if ":" in linea_strip or "=" in linea_strip:
                clave = linea_strip.split(":", 1)[0].split("=", 1)[0].strip()
                if clave and clave not in claves:
                    claves.append(clave[:80])
            if len(claves) >= 50:
                break

    limite_caracteres = max_tokens * 4
    resumen = "CLAVES:\n" + "\n".join(claves)
    if len(resumen) > limite_caracteres:
        resumen = resumen[:limite_caracteres] + "\n...[truncado]"

    return {"resumen": resumen, "claves": claves}


def _resumir_doc(contenido: str, max_tokens: int) -> Dict[str, Any]:
    """Genera resumen de documentación: encabezados + primeras líneas."""
    lineas = contenido.splitlines()
    encabezados: List[str] = []
    for linea in lineas:
        linea_strip = linea.strip()
        if linea_strip.startswith("#"):
            encabezados.append(linea_strip[:100])
        if len(encabezados) >= 20:
            break

    limite_caracteres = max_tokens * 4
    resumen_parts: List[str] = []
    if encabezados:
        resumen_parts.append("ENCABEZADOS:\n" + "\n".join(encabezados))
    # Primeras líneas del contenido
    primeras = "\n".join(lineas[:15])
    resumen_parts.append("INICIO:\n" + primeras[:500])

    resumen = "\n\n".join(resumen_parts)
    if len(resumen) > limite_caracteres:
        resumen = resumen[:limite_caracteres] + "\n...[truncado]"

    return {"resumen": resumen, "encabezados": encabezados}


def _resumir_generico(contenido: str, max_tokens: int) -> Dict[str, Any]:
    """Resumen genérico: primeras líneas del archivo."""
    limite_caracteres = max_tokens * 4
    lineas = contenido.splitlines()
    resumen = "\n".join(lineas[:20])
    if len(resumen) > limite_caracteres:
        resumen = resumen[:limite_caracteres] + "\n...[truncado]"
    return {"resumen": resumen}


def resumir_archivo(ruta: Path, max_tokens: int = 400, contenido: Optional[str] = None) -> Dict[str, Any]:
    """
    Genera un resumen compacto de un archivo según su extensión.
    Devuelve dict con 'resumen' (texto) y metadatos adicionales.

    Args:
        ruta: Ruta del archivo a resumir.
        max_tokens: Límite aproximado de tokens del resumen.
        contenido: Contenido ya leído del archivo (opcional). Si se pasa,
            no se vuelve a leer el archivo de disco (evita doble lectura).
    """
    ext = ruta.suffix.lower()
    if contenido is None:
        try:
            contenido = ruta.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {"resumen": obtener_mensaje("index.error_lectura"), "error": True}

    if ext == ".py":
        return _resumir_python(contenido, max_tokens)
    if ext in (".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte"):
        return _resumir_js_ts(contenido, max_tokens)
    if ext in CONFIG_EXTENSIONS:
        return _resumir_config(contenido, max_tokens)
    if ext in DOC_EXTENSIONS:
        return _resumir_doc(contenido, max_tokens)
    return _resumir_generico(contenido, max_tokens)


def _ruta_cache(directorio: str) -> Path:
    """Devuelve la ruta del archivo de caché del índice.

    Respeta la configuración PROJECT_INDEX_CACHE_DIR: si está definida,
    la caché se guarda en <directorio>/<PROJECT_INDEX_CACHE_DIR>/INDEX_FILENAME;
    en caso contrario, en la raíz del proyecto (comportamiento legacy).
    """
    base = Path(directorio)
    cache_dir = (getattr(settings, "PROJECT_INDEX_CACHE_DIR", "") or "").strip()
    if cache_dir:
        return base / cache_dir / INDEX_FILENAME
    return base / INDEX_FILENAME


def cargar_indice(directorio: str) -> Optional[Dict[str, Any]]:
    """Carga el índice cacheado en disco si existe y es válido."""
    ruta = _ruta_cache(directorio)
    if not ruta.exists():
        # Migración transparente: si la nueva ubicación no existe, intentar
        # la ruta legacy (raíz del proyecto) para cachés antiguas.
        ruta_legacy = Path(directorio) / INDEX_FILENAME
        if ruta_legacy != ruta and ruta_legacy.exists():
            ruta = ruta_legacy
        else:
            return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            indice = json.load(f)
        if indice.get("version") != INDEX_VERSION:
            return None
        if indice.get("directorio") != str(Path(directorio).resolve()):
            return None
        return indice
    except Exception:
        return None


def guardar_indice(directorio: str, indice: Dict[str, Any]) -> None:
    """Persiste el índice en disco."""
    try:
        ruta = _ruta_cache(directorio)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _es_archivo_indexable(ruta: Path) -> bool:
    """Determina si un archivo debe incluirse en el índice."""
    if _es_excluido(ruta.name, es_dir=False):
        return False
    if not ruta.is_file():
        return False
    # Omitir archivos muy grandes (> 1 MB)
    try:
        if ruta.stat().st_size > 1024 * 1024:
            return False
    except Exception:
        return False
    return True


def _recorrer_arbol(
    directorio: Path,
    max_tokens_por_archivo: int,
    indice_existente: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Recorre el árbol de directorios construyendo el índice.
    Usa el índice existente para no recalcular archivos sin cambios.

    Optimización: primero compara mtime + tamaño contra el índice previo;
    solo calcula sha256 (vía `_hash_archivo`) cuando mtime/tamaño cambiaron.
    """
    resumenes: Dict[str, Any] = {}
    arbol: Dict[str, Any] = {}

    resumenes_previos = (indice_existente or {}).get("resumenes", {})

    def _walk(dir_actual: Path, nodo_arbol: Dict[str, Any]) -> None:
        try:
            entradas = sorted(dir_actual.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return

        for entrada in entradas:
            nombre = entrada.name
            if _es_excluido(nombre, es_dir=entrada.is_dir()):
                continue

            if entrada.is_dir():
                hijos: Dict[str, Any] = {}
                nodo_arbol[nombre] = {"tipo": "dir", "hijos": hijos}
                _walk(entrada, hijos)
            elif entrada.is_file() and _es_archivo_indexable(entrada):
                rel = str(entrada.relative_to(directorio)).replace("\\", "/")
                previo = resumenes_previos.get(rel)

                # 1) Comparación barata: mtime_ns (con fallback a mtime) + tamaño
                #    contra el índice previo. Si coinciden, el archivo NO cambió:
                #    reutilizamos el resumen sin leer el contenido ni calcular sha256.
                try:
                    stat = entrada.stat()
                    mtime_ns_actual = stat.st_mtime_ns
                    mtime_actual = int(stat.st_mtime)
                    tamano_actual = stat.st_size
                except Exception:
                    mtime_ns_actual = 0
                    mtime_actual = 0
                    tamano_actual = 0

                # mtime_ns como criterio primario; fallback a mtime para cachés legacy
                if previo and previo.get("mtime_ns") is not None:
                    mtime_coincide = previo.get("mtime_ns") == mtime_ns_actual
                else:
                    mtime_coincide = bool(previo) and previo.get("mtime") == mtime_actual

                if (
                    previo
                    and mtime_coincide
                    and previo.get("tamano") == tamano_actual
                ):
                    resumen = previo
                    info_hash = {
                        "hash": previo.get("hash", ""),
                        "mtime": mtime_actual,
                        "mtime_ns": mtime_ns_actual,
                        "tamano": tamano_actual,
                    }
                else:
                    # 2) Solo aquí leemos el archivo (una única vez) y calculamos sha256
                    contenido, info_hash = _leer_contenido_y_hash(entrada)
                    resumen = resumir_archivo(entrada, max_tokens_por_archivo, contenido=contenido)
                    resumen.update(info_hash)

                resumenes[rel] = resumen
                nodo_arbol[nombre] = {
                    "tipo": "archivo",
                    "resumen": resumen.get("resumen", "")[:200],
                    "hash": info_hash["hash"],
                    "tamano": info_hash["tamano"],
                }

    _walk(directorio, arbol)

    return {"arbol": arbol, "resumenes": resumenes}


def construir_indice(
    directorio: str,
    max_tokens_por_archivo: Optional[int] = None,
    usar_cache: bool = True,
    idioma: str = "es",
) -> Dict[str, Any]:
    """
    Construye (o carga de caché) el índice del proyecto.

    Args:
        directorio: Ruta del proyecto a indexar.
        max_tokens_por_archivo: Límite de tokens por resumen de archivo.
        usar_cache: Si True, reutiliza el índice en disco cuando es válido.
        idioma: Idioma de los mensajes de error ('es' o 'en').

    Returns:
        Dict con la estructura del índice.
    """
    if max_tokens_por_archivo is None:
        max_tokens_por_archivo = int(getattr(settings, "PROJECT_INDEX_MAX_TOKENS_PER_FILE", 400))

    dir_resuelto = str(Path(directorio).resolve())
    if not os.path.isdir(dir_resuelto):
        return {
            "version": INDEX_VERSION,
            "directorio": dir_resuelto,
            "generado_en": "",
            "arbol": {},
            "resumenes": {},
            "error": obtener_mensaje("index.directorio_no_existe", idioma, directorio=directorio),
        }

    indice_existente = cargar_indice(dir_resuelto) if usar_cache else None

    datos = _recorrer_arbol(Path(dir_resuelto), max_tokens_por_archivo, indice_existente)

    indice = {
        "version": INDEX_VERSION,
        "directorio": dir_resuelto,
        "generado_en": __import__("datetime").datetime.now().isoformat(),
        "arbol": datos["arbol"],
        "resumenes": datos["resumenes"],
    }

    if usar_cache:
        guardar_indice(dir_resuelto, indice)

    return indice


def indice_es_valido(directorio: str, indice: Optional[Dict[str, Any]]) -> bool:
    """
    Verifica que el índice sigue siendo válido comparando hashes/mtime
    de los archivos indexados con el estado actual en disco.
    """
    if not indice or not isinstance(indice, dict):
        return False
    if indice.get("directorio") != str(Path(directorio).resolve()):
        return False

    resumenes = indice.get("resumenes", {})
    for rel, info in resumenes.items():
        ruta = Path(directorio) / rel
        if not ruta.exists():
            return False
        try:
            stat = ruta.stat()
            # mtime_ns como criterio primario; fallback a mtime para cachés legacy
            if info.get("mtime_ns") is not None:
                if stat.st_mtime_ns != info.get("mtime_ns"):
                    return False
            else:
                if int(stat.st_mtime) != info.get("mtime"):
                    return False
            if stat.st_size != info.get("tamano"):
                return False
        except Exception:
            return False
    return True


def actualizar_indice_incremental(directorio: str, indice: Optional[Dict[str, Any]], idioma: str = "es") -> Dict[str, Any]:
    """
    Actualiza el índice de forma incremental: solo recalcula los archivos
    cuyo hash/mtime cambió. Si el índice no existe, lo construye completo.
    """
    if not indice or not isinstance(indice, dict):
        return construir_indice(directorio, idioma=idioma)

    dir_resuelto = str(Path(directorio).resolve())
    if indice.get("directorio") != dir_resuelto:
        return construir_indice(directorio, idioma=idioma)

    max_tokens = int(getattr(settings, "PROJECT_INDEX_MAX_TOKENS_PER_FILE", 400))
    datos = _recorrer_arbol(Path(dir_resuelto), max_tokens, indice)

    indice_actualizado = {
        "version": INDEX_VERSION,
        "directorio": dir_resuelto,
        "generado_en": __import__("datetime").datetime.now().isoformat(),
        "arbol": datos["arbol"],
        "resumenes": datos["resumenes"],
    }
    guardar_indice(dir_resuelto, indice_actualizado)
    return indice_actualizado


def obtener_resumen_archivo(
    directorio: str,
    ruta_relativa: str,
    indice: Optional[Dict[str, Any]] = None,
    idioma: str = "es",
) -> Dict[str, Any]:
    """
    Obtiene el resumen de un archivo concreto desde el índice.
    Si el archivo cambió, actualiza el índice incrementalmente.

    Args:
        directorio: Ruta del proyecto.
        ruta_relativa: Ruta relativa del archivo (ej. 'app/main.py').
        indice: Índice actual (opcional). Si no se pasa, se carga de caché.
        idioma: Idioma de los mensajes de error ('es' o 'en').

    Returns:
        Dict con el resumen del archivo o un mensaje de error.
    """
    dir_resuelto = str(Path(directorio).resolve())
    ruta_completa = (Path(dir_resuelto) / ruta_relativa).resolve()

    # Seguridad: evitar path traversal fuera del directorio del proyecto.
    # Se usa Path.is_relative_to (el antiguo startswith fallaba con directorios
    # hermanos cuyo nombre es prefijo del proyecto, p.ej. 'proyecto' vs 'proyecto_hermano').
    if ruta_completa == Path(dir_resuelto):
        return {"resumen": obtener_mensaje("index.ruta_directorio_propio", idioma, ruta=ruta_relativa), "error": True}
    if not ruta_completa.is_relative_to(Path(dir_resuelto)):
        return {"resumen": obtener_mensaje("index.ruta_fuera_proyecto", idioma, ruta=ruta_relativa), "error": True}

    if not ruta_completa.exists() or not ruta_completa.is_file():
        return {"resumen": obtener_mensaje("index.archivo_no_existe", idioma, ruta=ruta_relativa), "error": True}

    if indice is None:
        indice = cargar_indice(dir_resuelto)

    rel = ruta_relativa.replace("\\", "/")
    # Lectura única en binario: contenido + hash sha256 + mtime/mtime_ns/tamaño
    contenido, info_hash = _leer_contenido_y_hash(ruta_completa)

    if indice and isinstance(indice, dict):
        resumenes = indice.get("resumenes", {})
        previo = resumenes.get(rel)
        if previo:
            # mtime_ns como criterio primario; fallback a mtime para cachés legacy
            if previo.get("mtime_ns") is not None:
                mtime_coincide = previo.get("mtime_ns") == info_hash["mtime_ns"]
            else:
                mtime_coincide = previo.get("mtime") == info_hash["mtime"]
            if previo.get("hash") == info_hash["hash"] and mtime_coincide:
                return previo

    # El archivo cambió o no está en el índice: recalcular y actualizar índice
    resumen = resumir_archivo(ruta_completa, contenido=contenido)
    resumen.update(info_hash)

    if indice and isinstance(indice, dict):
        indice.setdefault("resumenes", {})[rel] = resumen
        guardar_indice(dir_resuelto, indice)

    return resumen


def extraer_archivos_relevantes(texto: str, indice: Optional[Dict[str, Any]]) -> List[str]:
    """Devuelve las rutas de indice['resumenes'] mencionadas en el texto (o [] si no hay coincidencias)."""
    if not texto or not isinstance(indice, dict):
        return []
    resumenes = indice.get("resumenes")
    if not isinstance(resumenes, dict) or not resumenes:
        return []
    texto = texto.replace("\\", "/")
    resultado: List[str] = []
    for rel in resumenes.keys():
        # Bordes con lookbehind/lookahead: evita prefijos (src/...) y permite sufijos (:123, paréntesis)
        patron = r"(?<![\w./\-])" + re.escape(rel) + r"(?![\w])"
        if re.search(patron, texto):
            resultado.append(rel)
    return resultado


def formatear_indice_para_prompt(
    indice: Dict[str, Any],
    max_archivos: int = 25,
    archivos_relevantes: Optional[List[str]] = None,
) -> str:
    """
    Formatea el índice como texto compacto para inyectar en el prompt del LLM.
    Incluye el árbol de directorios y los resúmenes de los archivos más relevantes.

    Args:
        indice: Índice del proyecto (dict con 'arbol' y 'resumenes').
        max_archivos: Máximo de resúmenes de archivos a incluir (default 25).
        archivos_relevantes: Lista opcional de rutas relativas. Si se pasa,
            solo se incluyen esos archivos, priorizándolos en el orden dado.
    """
    if not indice or not isinstance(indice, dict):
        return "Índice de proyecto no disponible."

    arbol = indice.get("arbol", {})
    resumenes = indice.get("resumenes", {})

    lineas: List[str] = []
    lineas.append("📂 ESTRUCTURA DEL PROYECTO (Índice):")

    def _dibujar_arbol(nodo: Dict[str, Any], prefijo: str = "", profundidad: int = 0) -> None:
        if profundidad > 4:
            return
        for nombre, info in sorted(nodo.items()):
            if info.get("tipo") == "dir":
                lineas.append(f"{prefijo}{nombre}/")
                _dibujar_arbol(info.get("hijos", {}), prefijo + "  ", profundidad + 1)
            else:
                lineas.append(f"{prefijo}{nombre}")

    _dibujar_arbol(arbol)

    # Resúmenes de archivos (limitado)
    if resumenes:
        lineas.append("\n📄 RESUMENES DE ARCHIVOS:")
        if archivos_relevantes:
            # Filtrar solo los archivos relevantes, priorizándolos en el orden dado
            archivos = [rel for rel in archivos_relevantes if rel in resumenes]
        else:
            archivos = sorted(resumenes.keys())
        for rel in archivos[:max_archivos]:
            info = resumenes[rel]
            resumen = info.get("resumen", "")
            if resumen:
                lineas.append(f"\n### {rel}")
                lineas.append(resumen[:400])

    return "\n".join(lineas)
