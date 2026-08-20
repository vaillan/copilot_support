from pathlib import Path

from app.utils.project_index import (
    construir_indice,
    cargar_indice,
    guardar_indice,
    indice_es_valido,
    actualizar_indice_incremental,
    obtener_resumen_archivo,
    resumir_archivo,
    formatear_indice_para_prompt,
    _hash_archivo,
    INDEX_FILENAME,
)


def _crear(tmp_path: Path) -> Path:
    """Crea una estructura de proyecto de prueba."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(
        '"""Módulo principal."""\n\nimport os\nfrom typing import Optional\n\n\ndef crear_grafo():\n    """Compila el grafo."""\n    return None\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Proyecto de prueba\n\nDescripción.", encoding="utf-8")
    (tmp_path / "config.json").write_text('{"nombre": "test", "version": "1.0"}', encoding="utf-8")
    # Archivos que deben excluirse
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("ignorar", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_construir_indice_estructura(tmp_path):
    """Verifica que construir_indice genera el árbol y resúmenes correctamente."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    assert indice["version"] == 1
    assert indice["directorio"] == str(proyecto.resolve())

    # El árbol debe contener app/ y README.md
    arbol = indice["arbol"]
    assert "app" in arbol
    assert "README.md" in arbol
    assert "config.json" in arbol

    # Los excluidos no deben aparecer
    assert "node_modules" not in arbol
    assert "package-lock.json" not in arbol

    # Resúmenes
    resumenes = indice["resumenes"]
    assert "app/main.py" in resumenes
    assert "README.md" in resumenes
    assert "config.json" in resumenes


def test_resumir_archivo_python(tmp_path):
    """Test que el resumen de Python captura imports, firmas y docstrings."""
    archivo = tmp_path / "mod.py"
    contenido = (
        '"""Docstring del módulo."""\n\n'
        "import os\nfrom typing import List\n\n\n"
        "def funcion(x: int) -> str:\n"
        '    """Docstring de función."""\n'
        "    return str(x)\n\n\n"
        "class MiClase:\n"
        '    """Docstring de clase."""\n'
        "    pass\n"
    )
    archivo.write_text(contenido, encoding="utf-8")
    resumen = resumir_archivo(archivo, max_tokens=400)

    assert "import os" in resumen["resumen"]
    assert "from typing import List" in resumen["resumen"]
    assert "def funcion" in resumen["resumen"]
    assert "class MiClase" in resumen["resumen"]
    assert "Docstring del módulo" in resumen["resumen"]


def test_resumir_archivo_config(tmp_path):
    """Test que el resumen de config extrae claves."""
    archivo = tmp_path / "config.json"
    archivo.write_text('{"nombre": "test", "version": "1.0", "dependencias": ["a", "b"]}', encoding="utf-8")
    resumen = resumir_archivo(archivo, max_tokens=400)

    assert "nombre" in resumen["resumen"]
    assert "version" in resumen["resumen"]


def test_cargar_y_guardar_indice(tmp_path):
    """Test que guardar_indice persiste y cargar_indice lo recupera."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    guardar_indice(str(proyecto), indice)
    assert (proyecto / INDEX_FILENAME).exists()

    cargado = cargar_indice(str(proyecto))
    assert cargado is not None
    assert cargado["directorio"] == indice["directorio"]
    assert "app/main.py" in cargado["resumenes"]


def test_indice_es_valido(tmp_path):
    """Test que indice_es_valido detecta cambios en archivos."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    assert indice_es_valido(str(proyecto), indice) is True

    # Modificar un archivo indexado
    (proyecto / "app" / "main.py").write_text("# cambio\n", encoding="utf-8")
    assert indice_es_valido(str(proyecto), indice) is False


def test_actualizar_indice_incremental(tmp_path):
    """Test que actualizar_indice_incremental recalcula solo archivos cambiados."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    # Modificar un archivo
    (proyecto / "app" / "main.py").write_text(
        '"""Nuevo módulo."""\n\ndef nueva_funcion():\n    """Nueva función."""\n    return 1\n',
        encoding="utf-8",
    )

    indice_actualizado = actualizar_indice_incremental(str(proyecto), indice)
    assert indice_actualizado["resumenes"]["app/main.py"]["resumen"] != indice["resumenes"]["app/main.py"]["resumen"]
    assert "nueva_funcion" in indice_actualizado["resumenes"]["app/main.py"]["resumen"]


def test_obtener_resumen_archivo(tmp_path):
    """Test que obtener_resumen_archivo devuelve el resumen de un archivo."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    resumen = obtener_resumen_archivo(str(proyecto), "app/main.py", indice)
    assert "crear_grafo" in resumen["resumen"]

    # Archivo inexistente
    resumen_err = obtener_resumen_archivo(str(proyecto), "no_existe.py", indice)
    assert resumen_err.get("error") is True


def test_obtener_resumen_archivo_path_traversal(tmp_path):
    """Test que previene path traversal fuera del directorio."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    resumen = obtener_resumen_archivo(str(proyecto), "../outside.py", indice)
    assert resumen.get("error") is True


def test_formatear_indice_para_prompt(tmp_path):
    """Test que formatear_indice_para_prompt genera texto legible."""
    proyecto = _crear(tmp_path)
    indice = construir_indice(str(proyecto), usar_cache=False)

    texto = formatear_indice_para_prompt(indice)
    assert "ESTRUCTURA DEL PROYECTO" in texto
    assert "app" in texto
    assert "README.md" in texto


def test_hash_archivo(tmp_path):
    """Test que _hash_archivo calcula hash, mtime y tamaño."""
    archivo = tmp_path / "test.txt"
    archivo.write_text("contenido", encoding="utf-8")

    info = _hash_archivo(archivo)
    assert info["hash"]
    assert info["mtime"] > 0
    assert info["tamano"] > 0
