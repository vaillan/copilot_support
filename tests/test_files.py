import pytest
from unittest.mock import patch, mock_open
from app.utils.files import File, get_custom_file_tools

def test_file_get_content_cache():
    """
    Prueba que el método get_file_content de la clase File
    utiliza la caché interna después de la primera lectura.
    """
    File._cache = {}
    
    file_util = File(directory="prompts")
    
    mock_content = "contenido de prueba"
    
    with patch("builtins.open", mock_open(read_data=mock_content)) as mock_file:
        content1 = file_util.get_file_content("test.md")
        assert content1 == mock_content
        mock_file.assert_called_once()
        
        content2 = file_util.get_file_content("test.md")
        assert content2 == mock_content
        assert mock_file.call_count == 1

def test_write_and_read_file_aliases(tmp_path):
    """
    Prueba que las herramientas write_file y read_file creadas por get_custom_file_tools
    funcionan correctamente utilizando diferentes alias de parámetros y el directorio vinculado.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    write_tool = tools["write_file"]
    read_tool = tools["read_file"]

    d = tmp_path / "sub"
    d.mkdir()
    
    # 1. Escribir usando path y content
    res_write = write_tool.invoke({"path": "sub/test.txt", "content": "Hola mundo"})
    assert "exitosamente" in res_write
    
    # Verificar que el archivo existe físicamente en tmp_path
    assert (tmp_path / "sub" / "test.txt").exists()
    assert (tmp_path / "sub" / "test.txt").read_text(encoding="utf-8") == "Hola mundo"
    
    # 2. Leer usando file_path
    res_read = read_tool.invoke({"file_path": "sub/test.txt"})
    assert res_read == "Hola mundo"

def test_list_directory_aliases(tmp_path):
    """
    Prueba que list_directory funciona correctamente con alias dir_path/path usando el directorio vinculado.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    list_tool = tools["list_directory"]

    d = tmp_path / "subdir"
    d.mkdir()
    (d / "file1.py").write_text("print(1)")
    
    res_list = list_tool.invoke({"dir_path": "subdir"})
    assert "file1.py" in res_list
