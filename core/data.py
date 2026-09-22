"""Lectura de pedidos ya enriquecidos con producto y marca, listos para analizar."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import db

MODOS_SEMANA = {
    "estado": "Semana del reporte en que el pedido llegó a su estado (recomendado)",
    "pedido": "Semana de la fecha del pedido",
    "movimiento": "Semana del último movimiento de la transportadora",
}


def cargar_pedidos(con) -> pd.DataFrame:
    modo = db.get_config(con, "modo_semana", "estado")
    nombres = [r["nombre"] for r in con.execute("SELECT nombre FROM marcas")]
    por_defecto = nombres[0] if len(nombres) == 1 else "Sin asignar"  # panel de una sola marca
    df = pd.read_sql_query(
        """SELECT p.*, pr.id AS producto_id, COALESCE(pr.nombre, '(sin producto)') AS producto,
                  COALESCE(m1.nombre, m2.nombre, ?) AS marca
           FROM pedidos p
           LEFT JOIN producto_precios pp ON pp.precio = CAST(ROUND(p.valor_venta) AS INTEGER)
           LEFT JOIN productos pr ON pr.id = pp.producto_id
           LEFT JOIN marcas m1 ON m1.id = pr.marca_id
           LEFT JOIN tiendas t ON t.tienda_id = p.tienda_id
           LEFT JOIN marcas m2 ON m2.id = t.marca_id""", con, params=(por_defecto,))
    if df.empty:
        return df.assign(semana=[], flete_perdido=[], utilidad_operativa=[], causa=[], dias=[])
    df["semana"] = df[f"semana_{modo}"]
    df["vendedor"] = df["vendedor"].replace("", "(sin asignar)")
    df["transportadora"] = df["transportadora"].replace("", "(sin dato)")
    df["ciudad"] = df["ciudad"].replace("", "(sin dato)")
    df["departamento"] = df["departamento"].replace("", "(sin dato)")

    dev = df["estado"] == "DEVUELTO"
    ent = df["estado"] == "ENTREGADO"
    # Lo que se pierde en un pedido devuelto: el flete de ida y el de regreso.
    df["flete_perdido"] = (df["flete_ida"] + df["flete_devolucion"]).where(dev, 0.0)
    # GANANCIA de Dropi ya descuenta el flete de ida en los entregados.
    df["utilidad_operativa"] = df["ganancia"].where(ent, 0.0) - df["flete_perdido"]
    df["causa"] = df["novedad"].where(df["novedad"] != "", df["concepto_ultimo_mov"]).replace("", "(sin causa)")

    for c in ("fecha_pedido", "fecha_reporte", "fecha_ultimo_mov"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    ref = df["fecha_ultimo_mov"].fillna(df["fecha_pedido"]).fillna(df["fecha_reporte"])
    df["dias"] = (pd.Timestamp(dt.date.today()) - ref).dt.days.clip(lower=0)
    return df


def resumen_base(con) -> dict:
    r = con.execute("SELECT COUNT(*) n, MIN(semana_estado) a, MAX(semana_estado) b FROM pedidos").fetchone()
    c = con.execute("SELECT COUNT(*) n FROM cargas").fetchone()
    return {"pedidos": r["n"], "desde": r["a"], "hasta": r["b"], "cargas": c["n"]}
