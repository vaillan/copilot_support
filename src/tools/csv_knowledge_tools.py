from langchain_core.tools import tool
import os
import pandas as pd # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Ajusta esta ruta si tu estructura de ejecución es diferente.
CSV_FILE_PATH = os.path.join(os.getcwd(), 'src', 'knowledge_base', 'knowledge_base.csv')

class AppendToKnowledgeCsvToolInput(BaseModel):
    data: dict = Field(..., description="Datos de conocimiento destilados")

@tool('append_to_knowledge_csv_tool', args_schema=AppendToKnowledgeCsvToolInput, return_direct=True)
def append_to_knowledge_csv_tool(data: dict):
    """Añade una nueva fila de conocimiento estructurado al archivo CSV de la base de conocimiento.
    
    Args
        data: dict
    """
    file_path = CSV_FILE_PATH
    columns = ['item_id', 'board_name', 'item_name', 'problem_summary', 'root_cause', 'solution_applied', 'keywords', 'source_date']
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # Cargar el DataFrame existente o crear uno nuevo si el archivo no existe
    if os.path.exists(CSV_FILE_PATH):
        try:
            df = pd.read_csv(CSV_FILE_PATH)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(columns=columns)
    
    df = pd.read_csv(file_path) if os.path.exists(file_path) else pd.DataFrame(columns=columns)
    
    # Asegurarnos que item_id sea string para la comparación
    df['item_id'] = df['item_id'].astype(str)
    if str(data['item_id']) in df['item_id'].values:
        return f"Error: El conocimiento para el item_id {data['item_id']} ya existe."

     # Validar que todos los campos esperados estén en los datos de entrada
    missing_keys = [col for col in columns if col not in data]
    if missing_keys:
        return f"Error: Faltan las siguientes claves en los datos proporcionados: {', '.join(missing_keys)}"

    # Verificar si el item_id ya existe
    if str(data['item_id']) in df['item_id'].values:
        return f"Advertencia: El conocimiento para el item_id {data['item_id']} ya existe en el CSV. No se añadió duplicado."

    # Crear una nueva fila y concatenarla
    new_row = pd.DataFrame([data], columns=columns) # Asegurar el orden de las columnas
    df = pd.concat([df, new_row], ignore_index=True)
    
    # Guardar el DataFrame actualizado
    df.to_csv(CSV_FILE_PATH, index=False, encoding='utf-8')
    return f"Conocimiento para item_id {data['item_id']} añadido exitosamente al CSV."