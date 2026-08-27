"""Cargador e inyector de skills para enriquecer los prompts de los agentes."""
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.utils.prompt_utils import escapar_llaves

logger = logging.getLogger(__name__)

# Ubicaciones estándar de skills (Claude Code, Zoo Code, Cursor, editores y asistentes)
DIRECTORIOS_SKILLS: tuple[str, ...] = (
    ".skills",
    ".claude/skills",
    ".zoo/skills",
    ".cursor/skills",
    ".windsurf/skills",
    ".gemini/skills",
    ".codex/skills",
    ".github/copilot/skills",
    ".vscode/skills",
    ".zed/skills",
    ".roo/skills",
    ".clinerules/skills",
    ".aider/skills",
    ".opencode/skills",
    ".continue/skills",
    ".kilo/skills",
    ".codeium/skills",
    ".tabnine/skills",
    ".warp/skills",
)

EXTENSIONES_SKILL: tuple[str, ...] = (".md", ".json", ".yaml", ".yml")


class Skill(BaseModel):
    """Skill descubierta y parseada lista para inyección en un prompt."""

    nombre: str
    descripcion: str = ""
    contenido: str
    origen: str  # ruta relativa del archivo


def _extraer_frontmatter(texto: str) -> tuple[dict[str, str], str]:
    """Extrae frontmatter YAML simple (--- ... ---) y devuelve (metadatos, contenido)."""
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return {}, texto
    metadatos: dict[str, str] = {}
    for i, linea in enumerate(lineas[1:], start=1):
        if linea.strip() == "---":
            resto = "\n".join(lineas[i + 1:])
            return metadatos, resto
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            clave = clave.strip()
            valor = valor.strip().strip("'\"")
            if clave and valor:
                metadatos[clave] = valor
    return metadatos, texto


def _parsear_skill_md(ruta: Path, directorio: Path) -> Optional[Skill]:
    """Parsea una skill en formato Markdown con frontmatter opcional."""
    texto = ruta.read_text(encoding="utf-8")
    metadatos, contenido = _extraer_frontmatter(texto)
    nombre = metadatos.get("name") or ruta.stem
    descripcion = metadatos.get("description") or next(
        (l.strip() for l in contenido.splitlines() if l.strip()), ""
    )
    return Skill(nombre=nombre, descripcion=descripcion, contenido=contenido, origen=str(ruta.relative_to(directorio)))


def _parsear_skill_json(ruta: Path, directorio: Path) -> Optional[Skill]:
    """Parsea una skill en formato JSON con claves name/description/content."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nombre = datos.get("name")
    contenido = datos.get("content") or datos.get("instructions")
    if not nombre or not isinstance(contenido, str):
        return None
    return Skill(
        nombre=nombre,
        descripcion=datos.get("description", ""),
        contenido=contenido,
        origen=str(ruta.relative_to(directorio)),
    )


def _parsear_skill_yaml(ruta: Path, directorio: Path) -> Optional[Skill]:
    """Parsea una skill YAML simple (name/description/content) sin PyYAML."""
    texto = ruta.read_text(encoding="utf-8")
    metadatos, resto = _extraer_frontmatter(texto)
    nombre = metadatos.get("name") or ruta.stem
    descripcion = metadatos.get("description", "")
    contenido = metadatos.get("content") or metadatos.get("instructions") or resto
    return Skill(nombre=nombre, descripcion=descripcion, contenido=contenido, origen=str(ruta.relative_to(directorio)))


def _parsear_skill(ruta: Path, directorio: Path) -> Optional[Skill]:
    """Despacha el parsing según la extensión del archivo."""
    try:
        ext = ruta.suffix.lower()
        if ext == ".md":
            return _parsear_skill_md(ruta, directorio)
        if ext == ".json":
            return _parsear_skill_json(ruta, directorio)
        if ext in (".yaml", ".yml"):
            return _parsear_skill_yaml(ruta, directorio)
        return None
    except Exception as e:  # noqa: BLE001 - cualquier error de formato omite la skill
        logger.warning("Skill omitida por error de formato: %s - %s", ruta, e)
        return None


def descubrir_skills(directorio: str) -> list[Skill]:
    """Descubre y parsea las skills disponibles bajo el directorio base."""
    base = Path(directorio).resolve()
    skills: list[Skill] = []
    if not base.exists():
        return skills
    for subdir in DIRECTORIOS_SKILLS:
        dir_skills = base / subdir
        if not dir_skills.is_dir():
            continue
        for ruta in sorted(dir_skills.iterdir()):
            if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES_SKILL:
                skill = _parsear_skill(ruta, base)
                if skill is not None:
                    skills.append(skill)
    return skills


def formatear_skills_para_prompt(skills: list[Skill]) -> str:
    """Formatea las skills como un bloque Markdown para inyección en prompts."""
    if not skills:
        return ""
    bloques = ["=== SKILLS DISPONIBLES (inyectadas dinámicamente) ==="]
    for skill in skills:
        # Escapar llaves para que ChatPromptTemplate no las interprete como variables.
        nombre_escapado = escapar_llaves(skill.nombre)
        descripcion_escapada = escapar_llaves(skill.descripcion)
        contenido_escapado = escapar_llaves(skill.contenido)
        bloques.append(f"### Skill: {nombre_escapado}")
        if descripcion_escapada:
            bloques.append(f"Descripción: {descripcion_escapada}")
        bloques.append(f"Contenido:\n{contenido_escapado}")
    return "\n\n".join(bloques)


def cargar_skills_para_prompt(directorio: str) -> str:
    """Retorna la sección de skills formateada o cadena vacía si no hay ninguna."""
    return formatear_skills_para_prompt(descubrir_skills(directorio))