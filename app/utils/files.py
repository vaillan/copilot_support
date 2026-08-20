from pathlib import Path
import os
import shutil
from typing import Optional
from langchain_core.tools import tool
from app.utils.project_index import (
    construir_indice,
    obtener_resumen_archivo,
    formatear_indice_para_prompt,
)

class File:
    """
    Clase utilitaria para la gestión de lectura de archivos con caché.
    """
    _cache = {}

    def __init__(self, directory: str = "prompts"):
        """
        Inicializa la instancia especificando el directorio base.
        """
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name: str) -> str:
        """
        Lee y retorna el contenido completo de un archivo con sistema de caché.
        """
        cache_key = str(self.PROMPTS_DIR / file_name)
        if cache_key in File._cache:
            return File._cache[cache_key]
            
        with open(self.PROMPTS_DIR / file_name, "r", encoding="utf-8") as f:
            content = f.read()
            File._cache[cache_key] = content
        return content


def _resolver_ruta(directorio_base: str, ruta_archivo: str) -> Path:
    """
    Resuelve de forma robusta la ruta del archivo asegurando que funcione
    tanto con rutas relativas como absolutas y soporte múltiples alias.
    """
    base = Path(directorio_base).resolve() if directorio_base else Path.cwd()
    target = Path(ruta_archivo)
    if target.is_absolute():
        return target
    return (base / target).resolve()


def get_custom_file_tools(directorio: str):
    """
    Retorna la lista de herramientas personalizadas y robustas de archivos
    vinculadas al directorio de proyecto especificado usando closures.
    """
    
    @tool
    def write_file(file_path: Optional[str] = None, path: Optional[str] = None, text: Optional[str] = None, content: Optional[str] = None) -> str:
        """
        Escribe contenido en un archivo. Soporta alias ('file_path' o 'path', 'text' o 'content').
        Crea los directorios padre necesarios automáticamente.
        """
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
    def read_file(file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """
        Lee y retorna el contenido de un archivo. Soporta alias ('file_path' o 'path').
        """
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."

        try:
            ruta_completa = _resolver_ruta(directorio, ruta_relativa)
            if not ruta_completa.exists():
                return f"Error: El archivo '{ruta_relativa}' no existe en '{ruta_completa}'."
            with open(ruta_completa, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error al leer el archivo '{ruta_relativa}': {str(e)}"


    @tool
    def list_directory(dir_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """
        Lista el contenido de un directorio. Soporta alias ('dir_path' o 'path').
        """
        dir_objetivo = dir_path or path or "."
        try:
            ruta_completa = _resolver_ruta(directorio, dir_objetivo)
            if not ruta_completa.exists():
                return f"Error: El directorio '{dir_objetivo}' no existe."
            if not ruta_completa.is_dir():
                return f"Error: La ruta '{dir_objetivo}' no es un directorio."
            
            elementos = [p.name for p in ruta_completa.iterdir()]
            return f"Contenido de '{dir_objetivo}':\n" + "\n".join(elementos)
        except Exception as e:
            return f"Error al listar el directorio '{dir_objetivo}': {str(e)}"


    @tool
    def file_delete(file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """
        Elimina un archivo. Soporta alias ('file_path' o 'path').
        """
        ruta = file_path or path
        if not ruta:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            p = _resolver_ruta(directorio, ruta)
            if p.exists() and p.is_file():
                p.unlink()
                return f"Archivo '{ruta}' eliminado exitosamente."
            return f"Error: El archivo '{ruta}' no existe o no es un archivo."
        except Exception as e:
            return f"Error al eliminar '{ruta}': {str(e)}"


    @tool
    def copy_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None) -> str:
        """
        Copia un archivo. Soporta alias de origen y destino.
        """
        src = source_path or source
        dst = destination_path or destination or dest
        if not src or not dst:
            return "Error: Se requieren origen y destino."
        try:
            p_src = _resolver_ruta(directorio, src)
            p_dst = _resolver_ruta(directorio, dst)
            p_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p_src, p_dst)
            return f"Copiado de '{src}' a '{dst}' exitosamente."
        except Exception as e:
            return f"Error al copiar archivo: {str(e)}"


    @tool
    def move_file(source_path: Optional[str] = None, source: Optional[str] = None, destination_path: Optional[str] = None, destination: Optional[str] = None, dest: Optional[str] = None) -> str:
        """
        Mueve o renombra un archivo. Soporta alias de origen y destino.
        """
        src = source_path or source
        dst = destination_path or destination or dest
        if not src or not dst:
            return "Error: Se requieren origen y destino."
        try:
            p_src = _resolver_ruta(directorio, src)
            p_dst = _resolver_ruta(directorio, dst)
            p_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p_src), str(p_dst))
            return f"Movido de '{src}' a '{dst}' exitosamente."
        except Exception as e:
            return f"Error al mover archivo: {str(e)}"


    @tool
    def get_project_index() -> str:
        """
        Obtiene el Índice de Proyecto: una representación compacta de la estructura
        de directorios y resúmenes de archivos (firmas, imports, docstrings).
        LLAMA A ESTA HERRAMIENTA UNA VEZ AL INICIO en lugar de explorar con
        'list_directory' y 'read_file' repetidamente. Ahorra tokens.
        """
        try:
            indice = construir_indice(directorio)
            return formatear_indice_para_prompt(indice)
        except Exception as e:
            return f"Error al construir el índice del proyecto: {str(e)}"


    @tool
    def read_file_summary(file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """
        Lee SOLO el resumen de un archivo (firmas, imports, docstrings, claves)
        en lugar del contenido completo. ÚSALA para inspeccionar archivos antes de
        modificarlos o validarlos, ahorrando tokens. Soporta alias ('file_path' o 'path').
        """
        ruta_relativa = file_path or path
        if not ruta_relativa:
            return "Error: Debes proporcionar una ruta de archivo ('file_path' o 'path')."
        try:
            resumen = obtener_resumen_archivo(directorio, ruta_relativa)
            if resumen.get("error"):
                return resumen.get("resumen", "Error al obtener el resumen.")
            return f"📄 RESUMEN DE '{ruta_relativa}':\n{resumen.get('resumen', 'Sin resumen disponible.')}"
        except Exception as e:
            return f"Error al obtener el resumen de '{ruta_relativa}': {str(e)}"


    return [write_file, read_file, list_directory, file_delete, copy_file, move_file, get_project_index, read_file_summary]
