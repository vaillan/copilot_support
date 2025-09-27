from ..utils.extract_monday_data import ExtractData
from langchain_core.tools import tool

extractData = ExtractData()

@tool
def list_boards():
    """
    Llama a esta herramienta para obtener una lista de todos los nombres de los tableros de monday.com disponibles.
    Es útil cuando el usuario necesita saber qué tableros existen antes de realizar una búsqueda.
    """
    print("--- Llamando a la herramienta: list_monday_boards ---")
    boards = extractData._extract_all_boards()
    return [board['name'] for board in boards]
