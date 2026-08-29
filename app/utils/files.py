from pathlib import Path
import os
import shutil
from typing import Optional
from langchain_core.tools import tool
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


def _resolver_ruta(directorio_base: str, ruta_archivo: str) -> Path:
    """Resuelve la ruta contra el directorio base y rechaza rutas que escapen de él."""
    base = Path(directorio_base).resolve() if directorio_base else Path.cwd()
    target = Path(ruta_archivo)
    ruta_resuelta = target.resolve() if target.is_absolute() else (base / target).resolve()
    try:
        ruta_resuelta.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Error: la ruta '{ruta_archivo}' escapa del directorio del proyecto ('{base}')."
        )
    return ruta_resuelta


def get_custom_file_tools(directorio: str):
    """Retorna las herramientas personalizadas de archivos vinculadas al directorio."""

    @tool
    def write_file(file_path: Optional[str] = None, path: Optional[str] = None, text: Optional[str] = None, content: Optional[str] = None) -> str:
        """Escribe contenido en un archivo. Soporta alias ('file_path' o 'path', 'text' o 'content')."""
        ruta_relativa = file_path or path
        contenido = text if text is not None else content
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        if contenido is None:
            return "Error: Debes proporcionar el contenido del archivo ('text' o 'content')."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            ruta_completa.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(contenido)
            return f"Archivo '{ruta_relativa}' escrito exitosamente en '{ruta_completa}'."
        except Exception as e:
            return f"Error al escribir el archivo '{ruta_relativa}': {str(e)}"

    @tool
    def edit_file(file_path: Optional[str] = None, path: Optional[str] = None, old_text: Optional[str] = None, new_text: Optional[str] = None, line_start: Optional[int] = None, line_end: Optional[int] = None, replacement: Optional[str] = None) -> str:
        """Edita un archivo existente. Modo texto (old_text/new_text) o modo lineas (line_start/line_end/replacement)."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El archivo '{ruta_relativa}' no existe en '{ruta_completa}'."
            with open(ruta_completa, "r", encoding="utf-8") as f:
                contenido = f.read()
            if old_text is not None:
                if new_text is None:
                    return "Error: Debes proporcionar 'new_text' cuando usas 'old_text'."
                if old_text not in contenido:
                    return f"Error: No se encontr\u00f3 el texto a reemplazar en '{ruta_relativa}'."
                nuevo_contenido = contenido.replace(old_text, new_text)
            elif line_start is not None:
                lineas = contenido.splitlines(keepends=True)
                if line_start < 1 or line_start > len(lineas):
                    return f"Error: 'line_start' ({line_start}) fuera de rango (1..{len(lineas)})."
                line_end_efectivo = line_end if line_end is not None else line_start
                if line_end_efectivo < line_start or line_end_efectivo > len(lineas):
                    return f"Error: 'line_end' ({line_end_efectivo}) fuera de rango (1..{len(lineas)})."
                reemplazo = replacement if replacement is not None else ""
                if reemplazo and not reemplazo.endswith("\n") and line_end_efectivo < len(lineas):
                    reemplazo += "\n"
                nuevo_contenido = "".join(lineas[:line_start - 1]) + reemplazo + "".join(lineas[line_end_efectivo:])
            else:
                return "Error: Debes proporcionar 'old_text' o 'line_start' para editar el archivo."
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(nuevo_contenido)
            return f"Archivo '{ruta_relativa}' editado exitosamente."
        except Exception as e:
            return f"Error al editar el archivo '{ruta_relativa}': {str(e)}"

    @tool
    def read_file(file_path: Optional[str] = None, path: Optional[str] = None, max_lines: Optional[int] = 200) -> str:
        """Lee un archivo en disco y retorna su contenido. Soporta alias ('file_path' o 'path').
        Si se omite 'max_lines', se truncan las primeras 200 líneas para limitar el costo de tokens."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El archivo '{ruta_relativa}' no existe en '{ruta_completa}'."
            with open(ruta_completa, "r", encoding="utf-8") as f:
                lineas = f.readlines()
            if max_lines is not None and max_lines > 0 and len(lineas) > max_lines:
                contenido = "".join(lineas[:max_lines])
                contenido += f"\n[...truncado a {max_lines} líneas]"
                return contenido
            return "".join(lineas)
        except Exception as e:
            return f"Error al leer el archivo '{ruta_relativa}': {str(e)}"

    @tool
    def list_directory(dir_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """Lista el contenido de un directorio. Soporta alias ('dir_path' o 'path')."""
        ruta_relativa = dir_path or path or "."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El directorio '{ruta_relativa}' no existe."
            if not ruta_completa.is_dir():
                return f"Error: '{ruta_relativa}' no es un directorio."
            items = sorted(os.listdir(ruta_completa))
            if not items:
                return f"El directorio '{ruta_relativa}' esta vacio."
            return "\n".join(items)
        except Exception as e:
            return f"Error al listar el directorio '{ruta_relativa}': {str(e)}"

    @tool
    def get_project_index() -> str:
        """Devuelve el indice actual del proyecto: estructura y resumenes de archivos."""
        try:
            if not settings.PROJECT_INDEX_ENABLED:
                indice_cacheado = cargar_indice(directorio)
                if indice_cacheado:
                    return formatear_indice_para_prompt(indice_cacheado)
                return "Índice del proyecto deshabilitado (PROJECT_INDEX_ENABLED=False)."
            indice_previo = cargar_indice(directorio)
            if indice_previo:
                indice = actualizar_indice_incremental(directorio, indice_previo)
            else:
                indice = construir_indice(directorio)
            return formatear_indice_para_prompt(indice)
        except Exception as e:
            return f"Error al construir el indice del proyecto: {str(e)}"

    @tool
    def read_file_summary(file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """Lee SOLO el resumen de un archivo (firmas, imports, docstrings). Soporta alias."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El archivo '{ruta_relativa}' no existe."
            resumen = obtener_resumen_archivo(directorio, ruta_relativa)
            texto_resumen = resumen.get("resumen", str(resumen)) if isinstance(resumen, dict) else str(resumen)
            return f"RESUMEN del archivo '{ruta_relativa}':\n\n{texto_resumen}"
        except Exception as e:
            return f"Error al resumir el archivo '{ruta_relativa}': {str(e)}"

    @tool
    def file_delete(file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """Elimina un archivo del disco. Soporta alias ('file_path' o 'path')."""
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El archivo '{ruta_relativa}' no existe en '{ruta_completa}'."
            if ruta_completa.is_dir():
                return f"Error: '{ruta_relativa}' es un directorio, no un archivo."
            os.remove(ruta_completa)
            return f"Archivo '{ruta_relativa}' eliminado exitosamente."
        except Exception as e:
            return f"Error al eliminar el archivo '{ruta_relativa}': {str(e)}"

    @tool
    def copy_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None) -> str:
        """Copia un archivo a otra ubicación. Soporta alias ('source_path' o 'source', 'destination_path' o 'destination' o 'dest')."""
        origen = source_path or source
        destino = destination_path or destination or dest
        if not origen:
            return "Error: Debes proporcionar el archivo origen ('source_path' o 'source')."
        if not destino:
            return "Error: Debes proporcionar el destino ('destination_path', 'destination' o 'dest')."
        try:
            ruta_origen = _resolver_ruta(directorio, origen)
            ruta_destino = _resolver_ruta(directorio, destino)
            if not ruta_origen.exists():
                return f"Error: El archivo origen '{origen}' no existe en '{ruta_origen}'."
            if ruta_origen.is_dir():
                return f"Error: '{origen}' es un directorio, no un archivo."
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ruta_origen, ruta_destino)
            return f"Copiado de '{origen}' a '{destino}' exitosamente."
        except Exception as e:
            return f"Error al copiar de '{origen}' a '{destino}': {str(e)}"

    @tool
    def move_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None) -> str:
        """Mueve un archivo a otra ubicación. Soporta alias ('source_path' o 'source', 'destination_path' o 'destination' o 'dest')."""
        origen = source_path or source
        destino = destination_path or destination or dest
        if not origen:
            return "Error: Debes proporcionar el archivo origen ('source_path' o 'source')."
        if not destino:
            return "Error: Debes proporcionar el destino ('destination_path', 'destination' o 'dest')."
        try:
            ruta_origen = _resolver_ruta(directorio, origen)
            ruta_destino = _resolver_ruta(directorio, destino)
            if not ruta_origen.exists():
                return f"Error: El archivo origen '{origen}' no existe en '{ruta_origen}'."
            if ruta_origen.is_dir():
                return f"Error: '{origen}' es un directorio, no un archivo."
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(ruta_origen, ruta_destino)
            return f"Movido de '{origen}' a '{destino}' exitosamente."
        except Exception as e:
            return f"Error al mover de '{origen}' a '{destino}': {str(e)}"

    return [write_file, edit_file, read_file, list_directory, get_project_index, read_file_summary, file_delete, copy_file, move_file]