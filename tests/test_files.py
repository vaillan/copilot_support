import pytest
from unittest.mock import patch, mock_open
from app.utils.files import File, get_custom_file_tools, _resolver_ruta

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


def test_get_project_index_tool(tmp_path):
    """
    Prueba que la herramienta get_project_index devuelve el índice del proyecto.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    index_tool = tools["get_project_index"]

    (tmp_path / "main.py").write_text(
        '"""Módulo principal."""\n\ndef crear_grafo():\n    """Compila el grafo."""\n    return None\n',
        encoding="utf-8",
    )

    res = index_tool.invoke({})
    assert "ESTRUCTURA DEL PROYECTO" in res
    assert "main.py" in res


def test_read_file_summary_tool(tmp_path):
    """
    Prueba que la herramienta read_file_summary devuelve el resumen de un archivo.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    summary_tool = tools["read_file_summary"]

    (tmp_path / "mod.py").write_text(
        '"""Docstring."""\n\nimport os\n\ndef funcion():\n    """Docstring de función."""\n    return 1\n',
        encoding="utf-8",
    )

    res = summary_tool.invoke({"file_path": "mod.py"})
    assert "RESUMEN" in res
    assert "import os" in res
    assert "def funcion" in res

    # Archivo inexistente
    res_err = summary_tool.invoke({"file_path": "no_existe.py"})
    assert "Error" in res_err


def test_edit_file_reemplazo_texto(tmp_path):
    """
    Prueba que edit_file reemplaza todas las ocurrencias de old_text por new_text
    en un archivo existente y devuelve confirmación de éxito.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    write_tool = tools["write_file"]
    edit_tool = tools["edit_file"]

    # Crear archivo inicial
    res_write = write_tool.invoke({"path": "app.py", "content": "print('hola')\nprint('hola')\nprint('mundo')\n"})
    assert "exitosamente" in res_write

    # Editar por texto: reemplaza TODAS las ocurrencias
    res_edit = edit_tool.invoke({
        "path": "app.py",
        "old_text": "print('hola')",
        "new_text": "print('adiós')",
    })
    assert "editado exitosamente" in res_edit

    contenido = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "print('adiós')" in contenido
    assert "print('hola')" not in contenido
    assert contenido.count("print('adiós')") == 2


def test_edit_file_reemplazo_lineas(tmp_path):
    """
    Prueba que edit_file reemplaza un rango de líneas (1-indexado, inclusivo)
    por el texto de replacement y verifica el contenido resultante en disco.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    write_tool = tools["write_file"]
    edit_tool = tools["edit_file"]

    contenido_inicial = "linea1\nlinea2\nlinea3\nlinea4\nlinea5\n"
    res_write = write_tool.invoke({"path": "datos.txt", "content": contenido_inicial})
    assert "exitosamente" in res_write

    # Reemplazar líneas 2..4 por un bloque nuevo
    res_edit = edit_tool.invoke({
        "path": "datos.txt",
        "line_start": 2,
        "line_end": 4,
        "replacement": "NUEVA_A\nNUEVA_B",
    })
    assert "editado exitosamente" in res_edit

    contenido = (tmp_path / "datos.txt").read_text(encoding="utf-8")
    assert contenido == "linea1\nNUEVA_A\nNUEVA_B\nlinea5\n"

    # Eliminar líneas (replacement None): eliminar la línea 2
    res_edit2 = edit_tool.invoke({
        "path": "datos.txt",
        "line_start": 2,
        "line_end": 2,
    })
    assert "editado exitosamente" in res_edit2
    contenido2 = (tmp_path / "datos.txt").read_text(encoding="utf-8")
    assert contenido2 == "linea1\nNUEVA_B\nlinea5\n"


def test_edit_file_reemplazo_lineas_edge_cases(tmp_path):
    """
    Prueba de regresión para los casos borde del modo de reemplazo por líneas:
    (a) replacement que termina en '\n' no debe generar doble salto de línea.
    (b) replacement None (eliminar líneas) debe concatenar limpiamente sin salto fantasma.
    (c) reemplazo de la última línea no debe agregar salto de línea extra al final.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    write_tool = tools["write_file"]
    edit_tool = tools["edit_file"]

    # (a) replacement termina en '\n' → sin doble salto de línea
    res_write = write_tool.invoke({"path": "a.txt", "content": "linea1\nlinea2\nlinea3\nlinea4\nlinea5\n"})
    assert "exitosamente" in res_write
    res_edit = edit_tool.invoke({
        "path": "a.txt",
        "line_start": 2,
        "line_end": 4,
        "replacement": "NUEVA_A\nNUEVA_B\n",
    })
    assert "editado exitosamente" in res_edit
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "linea1\nNUEVA_A\nNUEVA_B\nlinea5\n"

    # (b) replacement None multi-línea → eliminación limpia sin salto fantasma
    res_write = write_tool.invoke({"path": "b.txt", "content": "linea1\nlinea2\nlinea3\nlinea4\nlinea5\n"})
    assert "exitosamente" in res_write
    res_edit = edit_tool.invoke({
        "path": "b.txt",
        "line_start": 2,
        "line_end": 4,
    })
    assert "editado exitosamente" in res_edit
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "linea1\nlinea5\n"

    # (c) reemplazo de la última línea → sin salto de línea extra al final
    res_write = write_tool.invoke({"path": "c.txt", "content": "linea1\nlinea2\nlinea3\n"})
    assert "exitosamente" in res_write
    res_edit = edit_tool.invoke({
        "path": "c.txt",
        "line_start": 3,
        "line_end": 3,
        "replacement": "NUEVA_ULTIMA",
    })
    assert "editado exitosamente" in res_edit
    assert (tmp_path / "c.txt").read_text(encoding="utf-8") == "linea1\nlinea2\nNUEVA_ULTIMA"


def test_edit_file_errores(tmp_path):
    """
    Prueba los casos de error de edit_file: archivo inexistente, old_text no
    encontrado, line_start fuera de rango y parámetros faltantes.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    write_tool = tools["write_file"]
    edit_tool = tools["edit_file"]

    # 1. Archivo inexistente
    res = edit_tool.invoke({"path": "no_existe.txt", "old_text": "x", "new_text": "y"})
    assert "Error" in res
    assert "no existe" in res

    # 2. old_text no encontrado
    write_tool.invoke({"path": "existe.txt", "content": "contenido original\n"})
    res = edit_tool.invoke({"path": "existe.txt", "old_text": "texto_que_no_esta", "new_text": "y"})
    assert "Error" in res
    assert "No se encontró el texto a reemplazar" in res

    # 3. line_start fuera de rango (mayor que el número de líneas)
    res = edit_tool.invoke({"path": "existe.txt", "line_start": 99, "line_end": 100, "replacement": "z"})
    assert "Error" in res

    # 4. Parámetros faltantes: sin ruta
    res = edit_tool.invoke({"old_text": "x", "new_text": "y"})
    assert "Error" in res

    # 5. Parámetros faltantes: old_text sin new_text
    res = edit_tool.invoke({"path": "existe.txt", "old_text": "contenido"})
    assert "Error" in res

    # 6. Parámetros faltantes: sin old_text ni line_start
    res = edit_tool.invoke({"path": "existe.txt", "new_text": "y"})
    assert "Error" in res


def test_read_file_truncado_por_max_lines(tmp_path):
    """
    Prueba que read_file trunca el contenido a las primeras N líneas cuando
    se pasa 'max_lines', añadiendo el marcador de truncado al final.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    read_tool = tools["read_file"]

    contenido = "\n".join(f"linea_{i}" for i in range(1, 11)) + "\n"
    (tmp_path / "largo.txt").write_text(contenido, encoding="utf-8")

    # Sin max_lines: devuelve todo el contenido
    res_completo = read_tool.invoke({"file_path": "largo.txt"})
    assert "linea_10" in res_completo
    assert "truncado" not in res_completo

    # Con max_lines=3: trunca a las primeras 3 líneas
    res_truncado = read_tool.invoke({"file_path": "largo.txt", "max_lines": 3})
    assert "linea_1" in res_truncado
    assert "linea_2" in res_truncado
    assert "linea_3" in res_truncado
    assert "linea_4" not in res_truncado
    assert "[...truncado a 3 líneas]" in res_truncado

    # max_lines mayor que el número de líneas: no trunca
    res_sin_truncar = read_tool.invoke({"file_path": "largo.txt", "max_lines": 100})
    assert "linea_10" in res_sin_truncar
    assert "truncado" not in res_sin_truncar


def test_confinamiento_ruta_relativa_normal(tmp_path):
    """
    Prueba que write_file con una ruta relativa dentro del directorio base
    (con subdirectorios) escribe correctamente en disco.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    res = tools["write_file"].invoke({"path": "sub/dir/archivo.txt", "content": "ok"})
    assert "exitosamente" in res
    assert (tmp_path / "sub" / "dir" / "archivo.txt").exists()
    assert (tmp_path / "sub" / "dir" / "archivo.txt").read_text(encoding="utf-8") == "ok"


def test_confinamiento_ruta_relativa_escape_bloqueada(tmp_path):
    """
    Prueba que una ruta relativa con '..' que escapa del directorio base es
    rechazada por write_file y read_file sin lanzar excepción (protege el ToolNode).
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    res_write = tools["write_file"].invoke({"path": "../fuera.txt", "content": "x"})
    assert "Error" in res_write
    assert "escapa del directorio" in res_write
    assert not (tmp_path.parent / "fuera.txt").exists()

    res_read = tools["read_file"].invoke({"file_path": "../fuera.txt"})
    assert "Error" in res_read
    assert "escapa del directorio" in res_read


def test_confinamiento_ruta_absoluta_dentro_ok(tmp_path):
    """
    Prueba que una ruta absoluta que resuelve dentro del directorio base es aceptada.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    ruta_abs = str(tmp_path / "abs.txt")
    res = tools["write_file"].invoke({"path": ruta_abs, "content": "ok"})
    assert "exitosamente" in res
    assert (tmp_path / "abs.txt").read_text(encoding="utf-8") == "ok"


def test_confinamiento_ruta_absoluta_fuera_bloqueada(tmp_path):
    """
    Prueba que una ruta absoluta fuera del directorio base es rechazada
    y no se crea ningún archivo en el directorio objetivo.
    """
    tools = {t.name: t for t in get_custom_file_tools(str(tmp_path))}
    ruta_fuera = tmp_path.parent / "fuera_abs.txt"
    res = tools["write_file"].invoke({"path": str(ruta_fuera), "content": "x"})
    assert "Error" in res
    assert "escapa del directorio" in res
    assert not ruta_fuera.exists()


def test_resolver_ruta_lanza_valueerror(tmp_path):
    """
    Prueba unitaria de _resolver_ruta: lanza ValueError al escapar del base
    y resuelve correctamente una ruta absoluta interna.
    """
    with pytest.raises(ValueError, match="escapa del directorio"):
        _resolver_ruta(str(tmp_path), "../fuera.txt")
    assert _resolver_ruta(str(tmp_path), str(tmp_path / "a.txt")) == (tmp_path / "a.txt").resolve()