"""Semanas ISO (lunes a domingo) y utilidades de calendario."""
from __future__ import annotations

import datetime as dt

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def semana_de(d) -> str:
    """'2026-W38' para una fecha."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def lunes(sem: str) -> dt.date:
    y, w = sem.split("-W")
    return dt.date.fromisocalendar(int(y), int(w), 1)


def rango(sem: str):
    l = lunes(sem)
    return l, l + dt.timedelta(days=6)


def etiqueta(sem: str) -> str:
    l, d = rango(sem)
    return f"Sem {int(sem[-2:])} · {l.day:02d} {MESES[l.month - 1]} – {d.day:02d} {MESES[d.month - 1]} {d.year}"


def etiqueta_corta(sem: str) -> str:
    l, _ = rango(sem)
    return f"S{int(sem[-2:])} ({l.day:02d} {MESES[l.month - 1]})"


def semanas_entre(a: str, b: str) -> list:
    """Todas las semanas entre a y b, ambas incluidas."""
    out, cur, fin = [], lunes(a), lunes(b)
    while cur <= fin:
        out.append(semana_de(cur))
        cur += dt.timedelta(days=7)
    return out


def semana_de_reporte(fecha_reporte: dt.date) -> str:
    """El reporte refleja el estado al cierre del día anterior: un reporte
    exportado un lunes pertenece a la semana que acaba de terminar."""
    return semana_de(fecha_reporte - dt.timedelta(days=1))


MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
               "octubre", "noviembre", "diciembre"]


def mes_de(sem: str) -> str:
    """'2026-09'. Una semana pertenece al mes en que cae su jueves (convención ISO)."""
    j = lunes(sem) + dt.timedelta(days=3)
    return f"{j.year}-{j.month:02d}"


def etiqueta_mes(mes: str) -> str:
    y, m = mes.split("-")
    return f"{MESES_LARGO[int(m) - 1].capitalize()} {y}"


def es_continua(semanas: list) -> bool:
    """True si `semanas` (en cualquier orden) forma un rango sin huecos."""
    if len(semanas) < 2:
        return True
    return sorted(semanas) == semanas_entre(min(semanas), max(semanas))


def texto_rango(semanas: list, maximo: int = 6) -> str:
    """Descripción legible de un conjunto de semanas: un rango si son continuas,
    o un listado corto si el usuario armó una selección suelta (no continua)."""
    if not semanas:
        return "Sin semanas seleccionadas"
    ordenadas = sorted(semanas)
    if es_continua(ordenadas):
        return etiqueta(ordenadas[0]) if len(ordenadas) == 1 else f"{etiqueta(ordenadas[0])}  →  {etiqueta(ordenadas[-1])}"
    vistas = ", ".join(etiqueta_corta(s) for s in ordenadas[:maximo])
    extra = f" y {len(ordenadas) - maximo} más" if len(ordenadas) > maximo else ""
    return f"{len(ordenadas)} semanas elegidas: {vistas}{extra}"


def slug_rango(semanas: list) -> str:
    """Para nombres de archivo: el rango si es continuo, o 'Nsemanas' si es una selección suelta."""
    if not semanas:
        return "sin_semanas"
    ordenadas = sorted(semanas)
    if es_continua(ordenadas):
        return ordenadas[0] if len(ordenadas) == 1 else f"{ordenadas[0]}_{ordenadas[-1]}"
    return f"{len(ordenadas)}semanas_{ordenadas[-1]}"
