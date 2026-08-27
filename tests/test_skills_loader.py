"""Pruebas unitarias del cargador de skills."""
import json

import pytest
from langchain_core.prompts import ChatPromptTemplate

from app.utils.skills_loader import (
    DIRECTORIOS_SKILLS,
    _extraer_frontmatter,
    cargar_skills_para_prompt,
    descubrir_skills,
    formatear_skills_para_prompt,
)


def _escribir(tmp_path, relativa: str, contenido: str):
    ruta = tmp_path / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_descubrimiento_en_todas_las_ubicaciones(tmp_path):
    for i, directorio in enumerate(DIRECTORIOS_SKILLS):
        _escribir(
            tmp_path,
            f"{directorio}/skill_{i}.md",
            f"---\nname: Skill{i}\n---\ncontenido {i}",
        )
    skills = descubrir_skills(str(tmp_path))
    nombres = {s.nombre for s in skills}
    assert nombres == {f"Skill{i}" for i in range(len(DIRECTORIOS_SKILLS))}


def test_parsing_md_con_frontmatter(tmp_path):
    _escribir(tmp_path, ".skills/x.md", "---\nname: X\ndescription: Desc X\n---\ncuerpo")
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "X"
    assert skills[0].descripcion == "Desc X"
    assert skills[0].contenido == "cuerpo"


def test_parsing_md_sin_frontmatter(tmp_path):
    _escribir(tmp_path, ".skills/mi_skill.md", "Primera linea\nresto")
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "mi_skill"
    assert skills[0].descripcion == "Primera linea"


def test_parsing_json_valida(tmp_path):
    _escribir(
        tmp_path,
        ".skills/s.json",
        '{"name": "J", "description": "Desc J", "content": "instrucciones"}',
    )
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "J"
    assert skills[0].contenido == "instrucciones"


def test_parsing_json_invalida_se_omite(tmp_path):
    _escribir(tmp_path, ".skills/sin_name.json", '{"description": "x", "content": "y"}')
    _escribir(tmp_path, ".skills/sin_content.json", '{"name": "x"}')
    skills = descubrir_skills(str(tmp_path))
    assert skills == []


def test_parsing_yaml(tmp_path):
    _escribir(
        tmp_path,
        ".skills/y.yaml",
        "---\nname: Y\ndescription: Desc Y\ncontent: cuerpo yaml\n---\n",
    )
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "Y"
    assert skills[0].descripcion == "Desc Y"
    assert skills[0].contenido == "cuerpo yaml"


def test_parsing_md_con_frontmatter_content(tmp_path):
    _escribir(
        tmp_path,
        ".skills/x.md",
        "---\nname: X\ndescription: Desc X\ncontent: cuerpo\n---\nresto",
    )
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "X"
    assert skills[0].contenido == "resto"


def test_parsing_yaml_con_instructions(tmp_path):
    _escribir(
        tmp_path,
        ".skills/y.yaml",
        "---\nname: Y\ninstructions: instrucciones yaml\n---\n",
    )
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "Y"
    assert skills[0].contenido == "instrucciones yaml"


def test_frontmatter_sin_cierre(tmp_path):
    _escribir(tmp_path, ".skills/z.md", "---\nname: Z\n")
    skills = descubrir_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].nombre == "Z"
    assert skills[0].contenido == "---\nname: Z\n"


def test_frontmatter_multiclave():
    metadatos, resto = _extraer_frontmatter(
        "---\nname: 'N'\ndescription: \"D\"\ncontent: C\ninstructions: I\n---\nresto"
    )
    assert metadatos == {
        "name": "N",
        "description": "D",
        "content": "C",
        "instructions": "I",
    }
    assert resto == "resto"


def test_frontmatter_claves_sin_valor_se_omiten():
    metadatos, _ = _extraer_frontmatter("---\nname: X\nclave_vacia:\n---\nresto")
    assert metadatos == {"name": "X"}


def test_formateo_bloque_y_vacio():
    from app.utils.skills_loader import Skill

    skills = [Skill(nombre="S1", descripcion="D1", contenido="C1", origen=".skills/s1.md")]
    bloque = formatear_skills_para_prompt(skills)
    assert "=== SKILLS DISPONIBLES (inyectadas dinámicamente) ===" in bloque
    assert "### Skill: S1" in bloque
    assert "Descripción: D1" in bloque
    assert "Contenido:" in bloque
    assert formatear_skills_para_prompt([]) == ""


def test_formateo_escapa_llaves():
    from app.utils.skills_loader import Skill

    skill = Skill(
        nombre="tpl",
        descripcion="usa {var}",
        contenido="código: {x} y {y} fin",
        origen="x.md",
    )
    bloque = formatear_skills_para_prompt([skill])
    assert "{{var}}" in bloque
    assert "{{x}}" in bloque
    # `{{var}}` contiene `{var}` como subcadena, por lo que se verifica que no
    # quede ningún `{var}` sin escapar (no precedido por otra llave).
    assert "{var}" not in bloque.replace("{{var}}", "")
    assert "{x}" not in bloque.replace("{{x}}", "")
    # Las llaves deben estar balanceadas: todo `{` escapado tiene su `}`.
    assert bloque.count("{") == bloque.count("}")
    # El bloque escapado debe ser inyectable sin error en un ChatPromptTemplate.
    ChatPromptTemplate.from_messages([("system", bloque)])


def test_formateo_skill_sin_llaves_no_duplica():
    from app.utils.skills_loader import Skill

    skill = Skill(nombre="plano", descripcion="sin llaves", contenido="texto plano", origen="x.md")
    bloque = formatear_skills_para_prompt([skill])
    assert "### Skill: plano" in bloque
    assert "sin llaves" in bloque
    assert "texto plano" in bloque
    assert "{{" not in bloque


def test_directorio_ausente_retorna_vacio(tmp_path):
    assert cargar_skills_para_prompt(str(tmp_path / "no_existe")) == ""


def test_errores_sintacticos_se_omiten_y_avisan(tmp_path, caplog):
    _escribir(tmp_path, ".skills/mal.json", "{json invalido")
    _escribir(tmp_path, ".skills/bien.md", "---\nname: OK\n---\ncontenido")
    with caplog.at_level("WARNING", logger="app.utils.skills_loader"):
        skills = descubrir_skills(str(tmp_path))
    assert [s.nombre for s in skills] == ["OK"]
    assert any("Skill omitida por error de formato" in r.message for r in caplog.records)