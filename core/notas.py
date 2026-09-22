"""Bitácora de notas por semana ('2026-W38') o mes ('2026-09')."""
from __future__ import annotations

import datetime as dt


def listar(con, periodos) -> list:
    periodos = [periodos] if isinstance(periodos, str) else list(periodos)
    if not periodos:
        return []
    q = ",".join("?" * len(periodos))
    return [dict(r) for r in con.execute(
        f"SELECT id, periodo, texto, creado_en FROM notas WHERE periodo IN ({q}) ORDER BY id DESC", periodos)]


def agregar(con, periodo: str, texto: str) -> None:
    if texto.strip():
        con.execute("INSERT INTO notas(periodo, texto, creado_en) VALUES (?,?,?)",
                    (periodo, texto.strip(), dt.datetime.now().isoformat(timespec="minutes")))
        con.commit()


def borrar(con, nota_id: int) -> None:
    con.execute("DELETE FROM notas WHERE id=?", (nota_id,))
    con.commit()


def conteo(con) -> dict:
    return {r["periodo"]: r["n"] for r in con.execute("SELECT periodo, COUNT(*) n FROM notas GROUP BY periodo")}
