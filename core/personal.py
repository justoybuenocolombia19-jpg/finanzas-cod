"""Panel personal: ingresos y gastos por semana y mes, con balance."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import historial, notas
from .semanas import semana_de

CATEGORIAS_GASTO = ["Vivienda", "Alimentación", "Transporte", "Salud", "Educación", "Servicios y suscripciones",
                    "Ocio y salidas", "Deudas y créditos", "Ahorro e inversión", "Otros gastos"]
CATEGORIAS_INGRESO = ["Retiro del negocio / sueldo", "Ventas", "Otros ingresos"]
TIPOS = ["ingreso", "gasto"]
COLUMNAS = ["id", "fecha", "semana", "mes", "tipo", "categoria", "monto", "nota"]


def categorias(tipo: str) -> list:
    return CATEGORIAS_INGRESO if tipo == "ingreso" else CATEGORIAS_GASTO


def cargar(con) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT id, fecha, tipo, categoria, monto, COALESCE(nota, '') AS nota "
                           "FROM movimientos ORDER BY fecha, id", con)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["semana"] = df["fecha"].map(lambda d: semana_de(d.date()))
    df["mes"] = df["fecha"].dt.strftime("%Y-%m")
    return df[COLUMNAS]


def agregar(con, fecha, tipo: str, categoria: str, monto: float, nota: str = "") -> None:
    if not monto or monto <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    con.execute("INSERT INTO movimientos(fecha, tipo, categoria, monto, nota) VALUES (?,?,?,?,?)",
                (pd.to_datetime(fecha).strftime("%Y-%m-%d"), tipo, categoria, float(monto), (nota or "").strip() or None))
    con.commit()


def guardar_mes(con, mes: str, df: pd.DataFrame) -> None:
    """Reemplaza todos los movimientos del mes 'YYYY-MM' por los de la tabla editada."""
    con.execute("DELETE FROM movimientos WHERE substr(fecha, 1, 7) = ?", (mes,))
    for r in df.to_dict("records"):
        monto = r.get("monto")
        if monto is None or pd.isna(monto) or not monto:
            continue
        fecha = r.get("fecha")
        fecha = f"{mes}-01" if fecha is None or pd.isna(fecha) else pd.to_datetime(fecha).strftime("%Y-%m-%d")
        tipo = r.get("tipo") if r.get("tipo") in TIPOS else "gasto"
        con.execute("INSERT INTO movimientos(fecha, tipo, categoria, monto, nota) VALUES (?,?,?,?,?)",
                    (fecha, tipo, r.get("categoria") or categorias(tipo)[-1], abs(float(monto)),
                     str(r.get("nota") or "").strip() or None))
    con.commit()


def totales(df: pd.DataFrame) -> dict:
    ing = float(df.loc[df["tipo"] == "ingreso", "monto"].sum()) if len(df) else 0.0
    gas = float(df.loc[df["tipo"] == "gasto", "monto"].sum()) if len(df) else 0.0
    return {"ingresos": ing, "gastos": gas, "balance": ing - gas, "ahorro": (ing - gas) / ing if ing else None}


def por_categoria(df: pd.DataFrame, tipo: str = "gasto") -> pd.DataFrame:
    d = df[df["tipo"] == tipo]
    return d.groupby("categoria", as_index=False)["monto"].sum().sort_values("monto", ascending=False)


def periodos(con, df: pd.DataFrame, modo: str) -> pd.DataFrame:
    """Una fila por semana ('semana') o mes ('mes'), el más reciente primero."""
    if df.empty:
        return pd.DataFrame()
    n_notas = notas.conteo(con)
    filas = []
    for clave, d in df.groupby("semana" if modo == "semana" else "mes"):
        t = totales(d)
        t.update(periodo=clave, etiqueta=historial.etiqueta_periodo(clave), movimientos=len(d),
                 notas=n_notas.get(clave, 0))
        filas.append(t)
    return pd.DataFrame(filas).sort_values("periodo", ascending=False).reset_index(drop=True)


def mes_actual() -> str:
    return dt.date.today().strftime("%Y-%m")
