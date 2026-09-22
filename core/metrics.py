"""KPIs de operación y de dinero real.

Utilidad neta real = Utilidad bruta (GANANCIA de entregados)
                     − Flete perdido en devoluciones (ida + regreso)
                     − Gastos (publicidad, fijos y variables)
"""
from __future__ import annotations

import pandas as pd

from .gastos import es_publicidad


def _div(a, b):
    return a / b if b else None


def resumen_gastos(g: pd.DataFrame) -> dict:
    if g is None or g.empty:
        return {"publicidad": 0.0, "fijos": 0.0, "variables": 0.0, "total": 0.0}
    pub = g.loc[g["tipo"].map(es_publicidad), "monto"].sum()
    fijos = g.loc[g["grupo"] == "Fijo", "monto"].sum()
    var = g.loc[(g["grupo"] == "Variable") & ~g["tipo"].map(es_publicidad), "monto"].sum()
    return {"publicidad": float(pub), "fijos": float(fijos), "variables": float(var),
            "total": float(pub + fijos + var)}


def kpis(df: pd.DataFrame, gastos: pd.DataFrame) -> dict:
    est = df["estado"].value_counts() if len(df) else pd.Series(dtype=int)
    ent, dev = df[df["estado"] == "ENTREGADO"], df[df["estado"] == "DEVUELTO"]
    riesgo = df[df["estado"].isin(["EN_OFICINA", "NOVEDAD"])]
    n_ent, n_dev = len(ent), len(dev)
    g = resumen_gastos(gastos)

    recaudo = float(ent["valor_venta"].sum())
    bruta = float(ent["ganancia"].sum())
    perdido = float(dev["flete_perdido"].sum())
    neta = bruta - perdido - g["total"]
    return {
        "generados": len(df),
        "entregados": n_ent, "devueltos": n_dev,
        "en_oficina": int(est.get("EN_OFICINA", 0)), "en_transito": int(est.get("EN_TRANSITO", 0)),
        "novedad": int(est.get("NOVEDAD", 0)), "pendientes": int(est.get("PENDIENTE", 0)),
        "cancelados": int(est.get("CANCELADO", 0)), "otros": int(est.get("OTRO", 0)),
        "tasa_entrega": _div(n_ent, n_ent + n_dev), "tasa_devolucion": _div(n_dev, n_ent + n_dev),
        "recaudo": recaudo, "utilidad_bruta": bruta, "flete_perdido": perdido,
        "gastos_publicidad": g["publicidad"], "gastos_fijos": g["fijos"], "gastos_variables": g["variables"],
        "gastos_total": g["total"],
        "utilidad_neta": neta, "margen_neto": _div(neta, recaudo),
        "roas": _div(recaudo, g["publicidad"]), "cac": _div(g["publicidad"], n_ent),
        "utilidad_prom_entregado": _div(bruta, n_ent), "costo_prom_devolucion": _div(perdido, n_dev),
        "dinero_en_riesgo": float(riesgo["valor_venta"].sum()), "pedidos_en_riesgo": len(riesgo),
    }


def semanal(df: pd.DataFrame, gastos: pd.DataFrame, semanas: list) -> pd.DataFrame:
    """Una fila por semana con los KPIs principales (para tendencias y comparación)."""
    filas = []
    for s in semanas:
        d = df[df["semana"] == s] if len(df) else df
        g = gastos[gastos["semana"] == s] if len(gastos) else gastos
        k = kpis(d, g)
        k["semana"] = s
        filas.append(k)
    return pd.DataFrame(filas)


def por_marca(df: pd.DataFrame, gastos_fn, marcas: list) -> pd.DataFrame:
    """KPIs lado a lado por marca. gastos_fn(marca) -> DataFrame de gastos de esa marca."""
    filas = []
    for m in marcas:
        k = kpis(df[df["marca"] == m], gastos_fn(m))
        k["marca"] = m
        filas.append(k)
    return pd.DataFrame(filas)
