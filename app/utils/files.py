from pathlib import Path

class File:
    """
    Clase utilitaria para la gestión de lectura de archivos con caché.
    """
    _cache = {}

    def __init__(self, directory: str):
        """
        Inicializa la instancia especificando el directorio base.
        """
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name: str) -> str:
        """
        Lee y retorna el contenido completo de un archivo con sistema de caché.
        """
        cache_key = str(self.PROMPTS_DIR / file_name)
        if cache_key in self._cache:
            return self._cache[cache_key]
            
        with open(self.PROMPTS_DIR / file_name, "r", encoding="utf-8") as f:
            content = f.read()
            self._cache[cache_key] = content
        return content