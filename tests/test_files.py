import pytest
from unittest.mock import patch, mock_open
from app.utils.files import File

def test_file_get_content_cache():
    """
    Prueba que el método get_file_content de la clase File
    utiliza la caché interna después de la primera lectura.
    """
    # Limpiar caché antes de la prueba para asegurar un estado limpio
    File._cache = {}
    
    file_util = File(directory="prompts")
    
    mock_content = "contenido de prueba"
    
    # Mockear builtins.open
    with patch("builtins.open", mock_open(read_data=mock_content)) as mock_file:
        # Primera lectura: debe abrir el archivo y leer su contenido
        content1 = file_util.get_file_content("test.md")
        assert content1 == mock_content
        mock_file.assert_called_once()
        
        # Segunda lectura: debe devolver el contenido desde la caché
        content2 = file_util.get_file_content("test.md")
        assert content2 == mock_content
        # El contador de llamadas a open no debe aumentar
        assert mock_file.call_count == 1
