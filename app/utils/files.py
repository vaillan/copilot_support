from pathlib import Path

class File:
    def __init__(self, directory: str):
        self.PROMPTS_DIR = Path(__file__).parent.parent / directory

    def get_file_content(self, file_name) -> str:
        with open(self.PROMPTS_DIR / file_name, "r", encoding="utf-8") as f:
            system_message_content = f.read()
        return system_message_content