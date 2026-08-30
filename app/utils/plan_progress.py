"""Utilidades deterministas de parseo del plan de acción y seguimiento de progreso."""

import re
from typing import Any, Dict, List, Optional

_PATRON_PASO = re.compile(r"\*\*Paso\s+(\d+):\s*([^*]+?)\*\*", re.IGNORECASE)


def parsear_pasos_plan(plan: Any) -> List[Dict[str, Any]]:
    """Parsea el plan de acción y devuelve los pasos como dicts (numero, titulo, cuerpo); lista vacía si el formato no es válido."""
    try:
        if isinstance(plan, str):
            coincidencias = list(_PATRON_PASO.finditer(plan))
            pasos: List[Dict[str, Any]] = []
            for indice, coincidencia in enumerate(coincidencias):
                inicio_cuerpo = coincidencia.end()
                fin_cuerpo = coincidencias[indice + 1].start() if indice + 1 < len(coincidencias) else len(plan)
                pasos.append({
                    "numero": int(coincidencia.group(1)),
                    "titulo": coincidencia.group(2).strip(),
                    "cuerpo": plan[inicio_cuerpo:fin_cuerpo].strip(),
                })
            return pasos

        if isinstance(plan, dict):
            items = plan.get("pasos")
            if not isinstance(items, list):
                return []
            pasos = []
            for indice, item in enumerate(items, start=1):
                if isinstance(item, dict):
                    tarea = str(item.get("tarea", ""))
                    coincidencia = _PATRON_PASO.search(tarea)
                    pasos.append({
                        "numero": int(coincidencia.group(1)) if coincidencia else indice,
                        "titulo": coincidencia.group(2).strip() if coincidencia else str(item.get("archivo", f"Paso {indice}")),
                        "cuerpo": tarea,
                    })
                elif isinstance(item, str):
                    pasos.append({"numero": indice, "titulo": f"Paso {indice}", "cuerpo": item})
            return pasos

        return []
    except Exception:
        return []


def inicializar_progreso(total_pasos: int) -> Dict[str, Any]:
    """Crea el estado inicial de progreso del plan."""
    return {"pasos_completados": [], "paso_actual": 1, "total_pasos": total_pasos}


def avanzar_progreso(progreso: Optional[Dict[str, Any]], numero_paso: int, total_pasos: int) -> Dict[str, Any]:
    """Actualiza el progreso de forma determinista e idempotente: marca numero_paso y fija paso_actual al siguiente pendiente."""
    if total_pasos <= 0:
        return dict(progreso) if progreso else inicializar_progreso(0)

    completados: set = set()
    if progreso and isinstance(progreso.get("pasos_completados"), list):
        completados = {n for n in progreso["pasos_completados"] if isinstance(n, int)}
    if 1 <= numero_paso <= total_pasos:
        completados.add(numero_paso)

    ordenados = sorted(completados)
    paso_actual = max(ordenados) + 1 if ordenados else 1
    return {"pasos_completados": ordenados, "paso_actual": paso_actual, "total_pasos": total_pasos}


def construir_ledger(progreso: Dict[str, Any]) -> str:
    """Construye el ledger compacto del progreso, p. ej. «Pasos completos: 1, 2 · Paso actual: 3 de 5 · Pendientes: 4, 5»."""
    completados = [n for n in progreso.get("pasos_completados", []) if isinstance(n, int)]
    paso_actual = progreso.get("paso_actual", 1)
    total = progreso.get("total_pasos", 0)
    texto_completados = ", ".join(str(n) for n in completados) if completados else "ninguno"

    if paso_actual > total:
        return f"Pasos completos: {texto_completados} · Todos los pasos completos ({total} de {total}) · Pendientes: ninguno"

    pendientes = [n for n in range(1, total + 1) if n not in completados and n != paso_actual]
    texto_pendientes = ", ".join(str(n) for n in pendientes) if pendientes else "ninguno"
    return f"Pasos completos: {texto_completados} · Paso actual: {paso_actual} de {total} · Pendientes: {texto_pendientes}"


def construir_contexto_compacto(plan: Any, progreso: Optional[Dict[str, Any]]) -> Optional[str]:
    """Devuelve el ledger junto al cuerpo del paso actual para inyectar en el prompt, o None si debe usarse el plan completo."""
    pasos = parsear_pasos_plan(plan)
    if not pasos or not isinstance(progreso, dict):
        return None

    completados = progreso.get("pasos_completados")
    paso_actual = progreso.get("paso_actual")
    if not isinstance(completados, list) or not isinstance(paso_actual, int):
        return None

    ledger = construir_ledger(progreso)
    total = len(pasos)

    if paso_actual > total:
        return f"{ledger}\n\nTodos los pasos están completos y verificados. Si ya escribiste todos los archivos en disco, invoca CodigoCompletado."

    cuerpo = next((p["cuerpo"] for p in pasos if p["numero"] == paso_actual), None)
    if cuerpo is None:
        return None
    return f"{ledger}\n\n--- PASO ACTUAL ({paso_actual} de {total}) ---\n{cuerpo}"


def construir_plan_pruebas(plan: Any) -> str:
    """Devuelve el plan limitado a los pasos con requiere_test=True (para el revisor), reutilizando parsear_pasos_plan."""
    # try/except defensivo: nunca debe interrumpir el flujo de revisión por un formato inesperado.
    try:
        if isinstance(plan, dict) and isinstance(plan.get("pasos"), list):
            pasos_test = [
                p for p in plan["pasos"]
                if isinstance(p, dict) and p.get("requiere_test") is True
            ]
            if not pasos_test:
                return "Ningún paso del plan requiere pruebas."
            pasos = parsear_pasos_plan({"pasos": pasos_test})
            return "\n\n".join(p["cuerpo"] for p in pasos)
        return str(plan) if plan else "Sin plan."
    except Exception:
        return str(plan) if plan else "Sin plan."