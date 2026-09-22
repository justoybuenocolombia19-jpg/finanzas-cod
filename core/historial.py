"""Historial: una fila por semana o por mes para volver a ver qué pasó en cada período."""
from __future__ import annotations

import pandas as pd

from . import metrics, notas
from .semanas import etiqueta, etiqueta_mes, mes_de


def grupos(semanas: list, modo: str) -> list:
    """[(clave, [semanas])] en orden cronológico. modo: 'semana' | 'mes'."""
    if modo == "semana":
        return [(s, [s]) for s in semanas]
    por_mes = {}
    for s in semanas:
        por_mes.setdefault(mes_de(s), []).append(s)
    return list(por_mes.items())


def etiqueta_periodo(clave: str) -> str:
    return etiqueta(clave) if "W" in clave else etiqueta_mes(clave)


def kpis_periodo(ctx, semanas: list) -> dict:
    d = ctx.df[ctx.df["semana"].isin(semanas)] if len(ctx.df) else ctx.df
    g = ctx.gastos[ctx.gastos["semana"].isin(semanas)]
    return metrics.kpis(d, g)


def periodos(ctx, modo: str) -> pd.DataFrame:
    """Resumen de cada período (el más reciente primero). `ctx` debe cubrir todo el rango."""
    n_notas = notas.conteo(ctx.con)
    archivos = {r["semana"]: r["n"] for r in ctx.con.execute("SELECT semana, COUNT(*) n FROM cargas GROUP BY semana")}
    filas = []
    for clave, ws in grupos(ctx.semanas, modo):
        k = kpis_periodo(ctx, ws)
        g = ctx.gastos[ctx.gastos["semana"].isin(ws)]
        k.update(periodo=clave, etiqueta=etiqueta_periodo(clave), semanas=len(ws),
                 gastos_ok="✓" if (g["grupo"] == "Variable").any() else "—",
                 archivos=sum(archivos.get(s, 0) for s in ws),
                 notas=n_notas.get(clave, 0) + (sum(n_notas.get(s, 0) for s in ws) if modo == "mes" else 0),
                 aviso="⚠️ sin pedidos" if k["generados"] == 0 else "")
        filas.append(k)
    return pd.DataFrame(filas).iloc[::-1].reset_index(drop=True) if filas else pd.DataFrame()
