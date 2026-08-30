from pathlib import Path
import os
import shutil
from typing import Optional
from langchain_core.tools import tool
from app.utils.i18n import obtener_mensaje
from app.utils.project_index import (
    actualizar_indice_incremental,
    cargar_indice,
    construir_indice,
    obtener_resumen_archivo,
    formatear_indice_para_prompt,
)
from app.settings.settings import Settings

settings = Settings()


class File:
    """Clase utilitaria para la gestion de lectura de archivos con cache."""

    _cache = {}

    def __init__(self, directory: str = "prompts"):
        """Inicializa la instancia especificando el directorio base."""
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name: str) -> str:
        """Lee y retorna el contenido completo de un archivo con cache."""
        cache_key = str(self.PROMPTS_DIR / file_name)
        if cache_key in File._cache:
            return File._cache[cache_key]
        with open(self.PROMPTS_DIR / file_name, "r", encoding="utf-8") as f:
            content = f.read()
            File._cache[cache_key] = content
        return content


def _resolver_ruta(directorio_base: str, ruta_archivo: str, idioma: str = "es") -> Path:
    """Resuelve la ruta contra el directorio base y rechaza rutas que escapen de él."""
    base = Path(directorio_base).resolve() if directorio_base else Path.cwd()
    target = Path(ruta_archivo)
    ruta_resuelta = target.resolve() if target.is_absolute() else (base / target).resolve()
    try:
        ruta_resuelta.relative_to(base)
    except ValueError:
        raise ValueError(
            obtener_mensaje("files.ruta_escapa", idioma, ruta=ruta_archivo, base=str(base))
        )
    return ruta_resuelta


def get_custom_file_tools(directorio: str):
    """Retorna las herramientas personalizadas de archivos vinculadas al directorio."""

    @tool
    def write_file(file_path: Optional[str] = None, path: Optional[str] = None, text: Optional[str] = None, content: Optional[str] = None, idioma: str = "es") -> str:
        """Escribe contenido en un archivo. Soporta alias ('file_path' o 'path', 'text' o 'content')."""
        ruta_relativa = file_path or path
        contenido = text if text is not None else content
        if not ruta_relativa:
            return obtener_mensaje("files.ruta_requerida", idioma)
        if contenido is None:
            return obtener_mensaje("files.contenido_requerido", idioma)
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            ruta_completa.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(contenido)
            return obtener_mensaje("files.escrito_ok", idioma, ruta=ruta_relativa, ruta_completa=str(ruta_completa))
        except Exception as e:
            return obtener_mensaje("files.error_escribir", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def edit_file(file_path: Optional[str] = None, path: Optional[str] = None, old_text: Optional[str] = None, new_text: Optional[str] = None, line_start: Optional[int] = None, line_end: Optional[int] = None, replacement: Optional[str] = None, idioma: str = "es") -> str:
        """Edita un archivo existente. Modo texto (old_text/new_text) o modo lineas (line_start/line_end/replacement)."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return obtener_mensaje("files.ruta_requerida", idioma)
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            if not ruta_completa.exists():
                return obtener_mensaje("files.no_existe_ruta", idioma, ruta=ruta_relativa, ruta_completa=str(ruta_completa))
            with open(ruta_completa, "r", encoding="utf-8") as f:
                contenido = f.read()
            if old_text is not None:
                if new_text is None:
                    return obtener_mensaje("files.new_text_requerido", idioma)
                if old_text not in contenido:
                    return obtener_mensaje("files.texto_no_encontrado", idioma, ruta=ruta_relativa)
                nuevo_contenido = contenido.replace(old_text, new_text)
            elif line_start is not None:
                lineas = contenido.splitlines(keepends=True)
                if line_start < 1 or line_start > len(lineas):
                    return obtener_mensaje("files.line_start_fuera_rango", idioma, line_start=line_start, total=len(lineas))
                line_end_efectivo = line_end if line_end is not None else line_start
                if line_end_efectivo < line_start or line_end_efectivo > len(lineas):
                    return obtener_mensaje("files.line_end_fuera_rango", idioma, line_end=line_end_efectivo, total=len(lineas))
                reemplazo = replacement if replacement is not None else ""
                if reemplazo and not reemplazo.endswith("\n") and line_end_efectivo < len(lineas):
                    reemplazo += "\n"
                nuevo_contenido = "".join(lineas[:line_start - 1]) + reemplazo + "".join(lineas[line_end_efectivo:])
            else:
                return obtener_mensaje("files.modo_requerido", idioma)
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(nuevo_contenido)
            return obtener_mensaje("files.editado_ok", idioma, ruta=ruta_relativa)
        except Exception as e:
            return obtener_mensaje("files.error_editar", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def read_file(file_path: Optional[str] = None, path: Optional[str] = None, max_lines: Optional[int] = 200, idioma: str = "es") -> str:
        """Lee un archivo en disco y retorna su contenido. Soporta alias ('file_path' o 'path').
        Si se omite 'max_lines', se truncan las primeras 200 líneas para limitar el costo de tokens."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return obtener_mensaje("files.ruta_requerida", idioma)
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            if not ruta_completa.exists():
                return obtener_mensaje("files.no_existe_ruta", idioma, ruta=ruta_relativa, ruta_completa=str(ruta_completa))
            with open(ruta_completa, "r", encoding="utf-8") as f:
                lineas = f.readlines()
            if max_lines is not None and max_lines > 0 and len(lineas) > max_lines:
                contenido = "".join(lineas[:max_lines])
                contenido += obtener_mensaje("files.truncado", idioma, max_lines=max_lines)
                return contenido
            return "".join(lineas)
        except Exception as e:
            return obtener_mensaje("files.error_leer", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def list_directory(dir_path: Optional[str] = None, path: Optional[str] = None, idioma: str = "es") -> str:
        """Lista el contenido de un directorio. Soporta alias ('dir_path' o 'path')."""
        ruta_relativa = dir_path or path or "."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            if not ruta_completa.exists():
                return obtener_mensaje("files.directorio_no_existe", idioma, ruta=ruta_relativa)
            if not ruta_completa.is_dir():
                return obtener_mensaje("files.no_es_directorio", idioma, ruta=ruta_relativa)
            items = sorted(os.listdir(ruta_completa))
            if not items:
                return obtener_mensaje("files.directorio_vacio", idioma, ruta=ruta_relativa)
            return "\n".join(items)
        except Exception as e:
            return obtener_mensaje("files.error_listar", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def get_project_index(idioma: str = "es") -> str:
        """Devuelve el indice actual del proyecto: estructura y resumenes de archivos."""
        try:
            if not settings.PROJECT_INDEX_ENABLED:
                indice_cacheado = cargar_indice(directorio)
                if indice_cacheado:
                    return formatear_indice_para_prompt(indice_cacheado)
                return obtener_mensaje("files.indice_deshabilitado", idioma)
            indice_previo = cargar_indice(directorio)
            if indice_previo:
                indice = actualizar_indice_incremental(directorio, indice_previo, idioma=idioma)
            else:
                indice = construir_indice(directorio, idioma=idioma)
            return formatear_indice_para_prompt(indice)
        except Exception as e:
            return obtener_mensaje("files.error_indice", idioma, error=str(e))

    @tool
    def read_file_summary(file_path: Optional[str] = None, path: Optional[str] = None, idioma: str = "es") -> str:
        """Lee SOLO el resumen de un archivo (firmas, imports, docstrings). Soporta alias."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return obtener_mensaje("files.ruta_requerida", idioma)
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            if not ruta_completa.exists():
                return obtener_mensaje("files.no_existe", idioma, ruta=ruta_relativa)
            resumen = obtener_resumen_archivo(directorio, ruta_relativa, idioma=idioma)
            texto_resumen = resumen.get("resumen", str(resumen)) if isinstance(resumen, dict) else str(resumen)
            return obtener_mensaje("files.resumen_ok", idioma, ruta=ruta_relativa, texto_resumen=texto_resumen)
        except Exception as e:
            return obtener_mensaje("files.error_resumir", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def file_delete(file_path: Optional[str] = None, path: Optional[str] = None, idioma: str = "es") -> str:
        """Elimina un archivo del disco. Soporta alias ('file_path' o 'path')."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return obtener_mensaje("files.ruta_requerida", idioma)
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa, idioma)
            if not ruta_completa.exists():
                return obtener_mensaje("files.no_existe_ruta", idioma, ruta=ruta_relativa, ruta_completa=str(ruta_completa))
            if ruta_completa.is_dir():
                return obtener_mensaje("files.es_directorio", idioma, ruta=ruta_relativa)
            os.remove(ruta_completa)
            return obtener_mensaje("files.eliminado_ok", idioma, ruta=ruta_relativa)
        except Exception as e:
            return obtener_mensaje("files.error_eliminar", idioma, ruta=ruta_relativa, error=str(e))

    @tool
    def copy_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None, idioma: str = "es") -> str:
        """Copia un archivo a otra ubicación. Soporta alias ('source_path' o 'source', 'destination_path' o 'destination' o 'dest')."""
        origen = source_path or source
        destino = destination_path or destination or dest
        if not origen:
            return obtener_mensaje("files.origen_requerido", idioma)
        if not destino:
            return obtener_mensaje("files.destino_requerido", idioma)
        try:
            ruta_origen = _resolver_ruta(directorio, origen, idioma)
            ruta_destino = _resolver_ruta(directorio, destino, idioma)
            if not ruta_origen.exists():
                return obtener_mensaje("files.no_existe_ruta", idioma, ruta=origen, ruta_completa=str(ruta_origen))
            if ruta_origen.is_dir():
                return obtener_mensaje("files.es_directorio", idioma, ruta=origen)
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ruta_origen, ruta_destino)
            return obtener_mensaje("files.copiado_ok", idioma, origen=origen, destino=destino)
        except Exception as e:
            return obtener_mensaje("files.error_copiar", idioma, origen=origen, destino=destino, error=str(e))

    @tool
    def move_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None, idioma: str = "es") -> str:
        """Mueve un archivo a otra ubicación. Soporta alias ('source_path' o 'source', 'destination_path' o 'destination' o 'dest')."""
        origen = source_path or source
        destino = destination_path or destination or dest
        if not origen:
            return obtener_mensaje("files.origen_requerido", idioma)
        if not destino:
            return obtener_mensaje("files.destino_requerido", idioma)
        try:
            ruta_origen = _resolver_ruta(directorio, origen, idioma)
            ruta_destino = _resolver_ruta(directorio, destino, idioma)
            if not ruta_origen.exists():
                return obtener_mensaje("files.no_existe_ruta", idioma, ruta=origen, ruta_completa=str(ruta_origen))
            if ruta_origen.is_dir():
                return obtener_mensaje("files.es_directorio", idioma, ruta=origen)
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(ruta_origen, ruta_destino)
            return obtener_mensaje("files.movido_ok", idioma, origen=origen, destino=destino)
        except Exception as e:
            return obtener_mensaje("files.error_mover", idioma, origen=origen, destino=destino, error=str(e))

    return [write_file, edit_file, read_file, list_directory, get_project_index, read_file_summary, file_delete, copy_file, move_file]