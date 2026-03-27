from pathlib import Path

class File:
    """
    Clase utilitaria para la gestión de lectura de archivos, principalmente para prompts.
    """
    def __init__(self, directory: str):
        """
        Inicializa la instancia especificando el directorio base.
        """
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name) -> str:
        """
        Lee y retorna el contenido completo de un archivo dentro del directorio configurado.
        """
        with open(self.PROMPTS_DIR / file_name, "r", encoding="utf-8") as f:
            system_message_content = f.read()
        return system_message_content