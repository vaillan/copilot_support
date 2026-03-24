from pathlib import Path

class File:
    def __init__(self, directory: str):
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name) -> str:
        file_path = self.PROMPTS_DIR / file_name
        if not file_path.exists():
            raise FileNotFoundError(f"Error: El archivo de prompt '{file_name}' no existe en {self.PROMPTS_DIR}")
        with open(file_path, "r", encoding="utf-8") as f:
            system_message_content = f.read()
        return system_message_content
