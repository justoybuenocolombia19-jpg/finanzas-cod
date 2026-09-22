"""Análisis 80/20 y rentabilidad por producto / transportadora."""
from __future__ import annotations

import pandas as pd


def pareto(df: pd.DataFrame, clave: str, valor: str, umbral: float = 0.8) -> pd.DataFrame:
    """Agrupa por `clave`, ordena de mayor a menor y marca los que suman el `umbral`."""
    cols = [clave, valor, "pct", "acumulado", "en_80"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    g = df.groupby(clave, dropna=False)[valor].sum().reset_index()
    g = g[g[valor] > 0].sort_values(valor, ascending=False).reset_index(drop=True)
    total = g[valor].sum()
    if not total:
        return pd.DataFrame(columns=cols)
    g["pct"] = g[valor] / total
    g["acumulado"] = g["pct"].cumsum()
    g["en_80"] = (g["acumulado"] - g["pct"]) < umbral  # incluye el que cruza el 80%
    return g


def pareto_utilidad(df):
    return pareto(df[df["estado"] == "ENTREGADO"], "producto", "ganancia")


def pareto_ventas(df):
    return pareto(df[df["estado"] == "ENTREGADO"], "producto", "valor_venta")


DIMENSIONES_DEVOLUCION = {"ciudad": "Ciudad", "departamento": "Departamento", "producto": "Producto",
                          "causa": "Causa (novedad / último movimiento)", "transportadora": "Transportadora"}


def pareto_devoluciones(df, dimension: str, por: str = "flete_perdido"):
    """por='flete_perdido' (plata) o 'pedidos' (cantidad de devoluciones)."""
    dev = df[df["estado"] == "DEVUELTO"].copy()
    dev["pedidos"] = 1
    return pareto(dev, dimension, por)


def rentabilidad_producto(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(["marca", "producto"]).apply(lambda d: pd.Series({
        "pedidos": len(d),
        "entregados": (d["estado"] == "ENTREGADO").sum(),
        "devueltos": (d["estado"] == "DEVUELTO").sum(),
        "recaudo": d.loc[d["estado"] == "ENTREGADO", "valor_venta"].sum(),
        "utilidad_bruta": d.loc[d["estado"] == "ENTREGADO", "ganancia"].sum(),
        "flete_perdido": d["flete_perdido"].sum(),
    }), include_groups=False).reset_index()
    g["utilidad_operativa"] = g["utilidad_bruta"] - g["flete_perdido"]
    g["margen_operativo"] = g["utilidad_operativa"] / g["recaudo"].where(g["recaudo"] > 0)
    cerrados = g["entregados"] + g["devueltos"]
    g["tasa_devolucion"] = g["devueltos"] / cerrados.where(cerrados > 0)
    return g.sort_values("utilidad_operativa", ascending=False).reset_index(drop=True)


def efectividad_transportadora(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("transportadora").apply(lambda d: pd.Series({
        "pedidos": len(d),
        "entregados": (d["estado"] == "ENTREGADO").sum(),
        "devueltos": (d["estado"] == "DEVUELTO").sum(),
        "en_oficina": (d["estado"] == "EN_OFICINA").sum(),
        "novedad": (d["estado"] == "NOVEDAD").sum(),
        "flete_perdido": d["flete_perdido"].sum(),
        "utilidad_operativa": d["utilidad_operativa"].sum(),
    }), include_groups=False).reset_index()
    cerrados = g["entregados"] + g["devueltos"]
    g["tasa_entrega"] = g["entregados"] / cerrados.where(cerrados > 0)
    g["tasa_devolucion"] = g["devueltos"] / cerrados.where(cerrados > 0)
    return g.sort_values("pedidos", ascending=False).reset_index(drop=True)


def evolucion_producto(df: pd.DataFrame, producto: str) -> pd.DataFrame:
    """Precio de venta, costo de proveedor y margen promedio de un producto, semana a semana.
    Sirve para detectar de un vistazo cuándo el proveedor subió el costo o cambió el precio de venta."""
    d = df[(df["producto"] == producto) & (df["estado"] == "ENTREGADO")]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("semana").agg(entregados=("id", "count"), precio_venta_prom=("valor_venta", "mean"),
                                costo_prom=("costo_proveedor", "mean"), ganancia_prom=("ganancia", "mean")
                                ).reset_index().sort_values("semana").reset_index(drop=True)
    g["margen_pct"] = g["ganancia_prom"] / g["precio_venta_prom"].where(g["precio_venta_prom"] > 0)
    for col, marca in [("precio_venta_prom", "cambio_precio"), ("costo_prom", "cambio_costo")]:
        previo = g[col].shift(1)
        g[marca] = previo.notna() & ((g[col] - previo).abs() / previo.replace(0, pd.NA) > 0.01).fillna(False)
    return g
