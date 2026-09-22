"""Gastos que NO vienen en los reportes de la plataforma.

Fijos mensuales (apps, nómina, administrativos…): se prorratean por días en cada semana.
Variables por semana (publicidad, empaques…): se registran semana a semana.
Un gasto sin marca es 'Compartido' y se reparte entre marcas según su recaudo.
"""
from __future__ import annotations

import calendar
import datetime as dt

import pandas as pd

from .semanas import rango

CATEGORIAS_FIJOS = ["Apps y suscripciones", "Nómina (empleados)", "Administrativos",
                    "Arriendo y servicios", "Otros fijos"]
TIPOS_VARIABLES = ["Publicidad Meta", "Publicidad TikTok", "Publicidad Google", "Empaques",
                   "Comisión de plataforma", "Otros"]
COMPARTIDO = "Compartido"
COLUMNAS = ["semana", "grupo", "tipo", "concepto", "marca", "monto"]


def es_publicidad(tipo) -> bool:
    return str(tipo).startswith("Publicidad")


def fijos_por_semana(con, semanas: list) -> pd.DataFrame:
    filas = con.execute(
        """SELECT g.*, m.nombre AS marca FROM gastos_fijos g
           LEFT JOIN marcas m ON m.id = g.marca_id WHERE g.activo = 1""").fetchall()
    out = []
    for sem in semanas:
        lunes, _ = rango(sem)
        for g in filas:
            desde = dt.date.fromisoformat(g["desde"]) if g["desde"] else dt.date.min
            hasta = dt.date.fromisoformat(g["hasta"]) if g["hasta"] else dt.date.max
            total = 0.0
            for i in range(7):
                d = lunes + dt.timedelta(days=i)
                if desde <= d <= hasta:
                    total += g["monto_mensual"] / calendar.monthrange(d.year, d.month)[1]
            if total:
                out.append({"semana": sem, "grupo": "Fijo", "tipo": g["categoria"], "concepto": g["concepto"],
                            "marca": g["marca"] or COMPARTIDO, "monto": total})
    return pd.DataFrame(out, columns=COLUMNAS)


def variables_por_semana(con, semanas: list) -> pd.DataFrame:
    if not semanas:
        return pd.DataFrame(columns=COLUMNAS)
    q = ",".join("?" * len(semanas))
    filas = con.execute(
        f"""SELECT g.semana, g.tipo, g.nota, g.monto, m.nombre AS marca FROM gastos_semana g
            LEFT JOIN marcas m ON m.id = g.marca_id WHERE g.semana IN ({q})""", semanas).fetchall()
    return pd.DataFrame(
        [{"semana": f["semana"], "grupo": "Variable", "tipo": f["tipo"], "concepto": f["nota"] or f["tipo"],
          "marca": f["marca"] or COMPARTIDO, "monto": f["monto"]} for f in filas], columns=COLUMNAS)


def gastos_semanales(con, semanas: list, marca: str | None = None, factor_compartido: float = 1.0) -> pd.DataFrame:
    """Gastos de las semanas dadas. Con `marca`, incluye los propios de esa marca más su
    parte (factor_compartido, 0-1) de los compartidos."""
    df = pd.concat([fijos_por_semana(con, semanas), variables_por_semana(con, semanas)], ignore_index=True)
    if df.empty or not marca:
        return df
    propios = df[df["marca"] == marca]
    comp = df[df["marca"] == COMPARTIDO].copy()
    comp["monto"] = comp["monto"] * factor_compartido
    return pd.concat([propios, comp], ignore_index=True)


def factor_compartido(df_pedidos: pd.DataFrame, marca: str, marcas_activas: list) -> float:
    """Parte de los gastos compartidos que le toca a `marca`: su porción del recaudo
    (o de los pedidos si no hay recaudo; o partes iguales si no hay nada)."""
    ent = df_pedidos[df_pedidos["estado"] == "ENTREGADO"]
    total = ent["valor_venta"].sum()
    if total > 0:
        return float(ent.loc[ent["marca"] == marca, "valor_venta"].sum() / total)
    if len(df_pedidos):
        return float((df_pedidos["marca"] == marca).mean())
    return 1.0 / max(len(marcas_activas), 1)


# ---- persistencia de gastos fijos y variables

def listar_fijos(con) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT g.id, g.concepto, g.categoria, g.monto_mensual, COALESCE(m.nombre, ?) AS marca,
                  g.desde, g.hasta, g.activo
           FROM gastos_fijos g LEFT JOIN marcas m ON m.id = g.marca_id ORDER BY g.categoria, g.concepto""",
        con, params=(COMPARTIDO,))


def _marca_id(con, nombre):
    if not nombre or nombre == COMPARTIDO:
        return None
    r = con.execute("SELECT id FROM marcas WHERE nombre=?", (nombre,)).fetchone()
    return r["id"] if r else None


def _iso(x):
    if x is None or (isinstance(x, float) and x != x) or str(x).strip() in ("", "NaT", "None"):
        return None
    return pd.to_datetime(x).strftime("%Y-%m-%d")


def guardar_fijos(con, df: pd.DataFrame) -> None:
    con.execute("DELETE FROM gastos_fijos")
    for r in df.to_dict("records"):
        monto = r.get("monto_mensual")
        if not str(r.get("concepto") or "").strip() or monto is None or pd.isna(monto) or not monto:
            continue
        con.execute(
            """INSERT INTO gastos_fijos(concepto, categoria, monto_mensual, marca_id, desde, hasta, activo)
               VALUES (?,?,?,?,?,?,?)""",
            (str(r["concepto"]).strip(), r.get("categoria") or "Otros fijos", float(r["monto_mensual"]),
             _marca_id(con, r.get("marca")), _iso(r.get("desde")), _iso(r.get("hasta")),
             0 if r.get("activo") in (False, 0) else 1))
    con.commit()


def listar_variables(con, semana: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT g.tipo, COALESCE(m.nombre, ?) AS marca, g.monto, COALESCE(g.nota, '') AS nota
           FROM gastos_semana g LEFT JOIN marcas m ON m.id = g.marca_id
           WHERE g.semana = ? ORDER BY g.id""", con, params=(COMPARTIDO, semana))


def guardar_variables(con, semana: str, df: pd.DataFrame) -> None:
    con.execute("DELETE FROM gastos_semana WHERE semana=?", (semana,))
    for r in df.to_dict("records"):
        if r.get("monto") is None or pd.isna(r.get("monto")) or not r.get("monto"):
            continue
        con.execute("INSERT INTO gastos_semana(semana, tipo, marca_id, monto, nota) VALUES (?,?,?,?,?)",
                    (semana, r.get("tipo") or "Otros", _marca_id(con, r.get("marca")), float(r["monto"]),
                     (str(r.get("nota") or "")).strip() or None))
    con.commit()


def semanas_con_gastos(con) -> list:
    return [r["semana"] for r in con.execute("SELECT DISTINCT semana FROM gastos_semana ORDER BY semana")]
