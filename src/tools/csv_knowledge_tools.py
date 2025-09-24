from langchain_core.tools import tool
import os
import pandas as pd # type: ignore
from pydantic import BaseModel, Field # type: ignore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_FILE_PATH = os.path.join(BASE_DIR, 'src', 'knowledge_base', 'knowledge_base.csv')

class AppendToKnowledgeCsvToolInput(BaseModel):
    """Input schema for appending data to the knowledge CSV."""
    data: dict = Field(..., description="Datos de conocimiento destilados en formato de diccionario. "
                                        "Debe contener: item_id, board_name, item_name, problem_summary, "
                                        "root_cause, solution_applied, keywords, source_date.")

@tool('append_to_knowledge_csv_tool', args_schema=AppendToKnowledgeCsvToolInput, return_direct=True)
def append_to_knowledge_csv_tool(data: dict) -> str:
    """
    Añade una nueva fila de conocimiento estructurado al archivo CSV de la base de conocimiento.
    Verifica si el item_id ya existe para evitar duplicados.
    Maneja la creación del archivo y la escritura de encabezados si no existe.
    
    Args:
        data: dict - Un diccionario con los datos del ticket a añadir.
    Returns:
        str: Un mensaje indicando el resultado de la operación.
    """
    columns = ['item_id', 'board_name', 'item_name', 'problem_summary', 'root_cause', 'solution_applied', 'keywords', 'source_date']
    
    # Asegurarse de que el directorio exista
    os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)

    # Validar que todos los campos esperados estén en los datos de entrada
    missing_keys = [col for col in columns if col not in data]
    if missing_keys:
        return f"Error: Faltan las siguientes claves en los datos proporcionados: {', '.join(missing_keys)}"

    try:
        # Si el archivo no existe, lo creamos con los encabezados
        if not os.path.exists(CSV_FILE_PATH):
            df = pd.DataFrame(columns=columns)
            df.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8')

        df = pd.read_csv(CSV_FILE_PATH)

    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=columns)
        df.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8')
    
    # Asegurarnos que item_id sea string para la comparación
    if 'item_id' in df.columns and not df.empty:
        df['item_id'] = df['item_id'].astype(str)
    else:
        # Si el DataFrame está vacío, no hay nada que convertir
        pass

    # Verificar si el item_id ya existe
    if not df.empty and str(data['item_id']) in df['item_id'].values:
        return f"Advertencia: El conocimiento para el item_id {data['item_id']} ya existe en el CSV. No se añadió duplicado."

    # Crear una nueva fila y concatenarla
    new_row = pd.DataFrame([data], columns=columns) # Asegurar el orden de las columnas
    df = pd.concat([df, new_row], ignore_index=True)
    
    # Guardar el DataFrame actualizado
    df.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8')
    return f"Conocimiento para item_id {data['item_id']} añadido exitosamente al CSV."