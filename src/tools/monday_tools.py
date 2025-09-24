from langchain_core.tools import tool
from pydantic import BaseModel, Field
from ..utils.extract_monday_data import ExtractData
import json

class DataExtractorBoardToolInput(BaseModel):
    """Input schema for Monday Tools inputs."""
    board_name: str = Field(..., description="Nombre del tablero")
    text_search: str = Field(..., description="texto a buscar") 
    
class DataExtractorTimelineBoardToolInput(BaseModel):
    """Input schema for Monday Tools inputs."""
    board_name: str = Field(..., description="Nombre del tablero")
    start_date: str = Field(..., description="Fecha de inicio para la extraccion")
    end_date: str = Field(..., description="Fecha de fin para la extraccion") 


@tool("data_extractor_board_tool", args_schema=DataExtractorBoardToolInput, return_direct=True)
def data_extractor_board_tool(board_name:str, text_search: str) -> str:
    # Se instancia ExtractData para utilizar sus métodos de extracción.
    """Ejecuta la extracción de datos de Monday.com para el tablero y texto de búsqueda especificados.
        Instancia la clase ExtractData y utiliza su método extract_board_data.

    Args:
        board_name: str
        text_search: str
    """
    data_extractor = ExtractData()
    extracted_data = data_extractor.extract_board_data(board_name=board_name, text_search=text_search)
    
    # Convierte los datos extraídos a una cadena JSON para la salida de la herramienta.
    if extracted_data:
        return json.dumps(extracted_data, indent=2, ensure_ascii=False)
    else:
        return "No se encontraron datos o hubo un error al extraerlos del tablero especificado."

@tool("extract_board_data_by_timeline_tool", args_schema=DataExtractorTimelineBoardToolInput, return_direct=True)
def extract_board_data_by_timeline_tool(board_name: str, start_date: str, end_date: str) -> list:
    """Extrae todos los ítems de un tablero específico que fueron actualizados dentro de un rango de fechas.

    Args:
        board_name: str
        start_date: str
        end_date: str
    """
    data_extractor = ExtractData()
    extracted_data = data_extractor.extract_board_data_by_timeline(board_name=board_name, timeline=[start_date, end_date])

    if extracted_data:
        return extracted_data
    else:
        return []
