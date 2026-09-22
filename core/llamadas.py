"""Lista de llamadas: pedidos EN OFICINA / EN NOVEDAD ordenados por prioridad."""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

RESULTADOS = ["", "Contestó · va a reclamar", "Contestó · reprogramar entrega", "Contestó · no lo quiere",
              "No contesta", "Número errado", "Otro"]


def _whatsapp(tel: str) -> str:
    d = re.sub(r"\D", "", str(tel or ""))
    if len(d) == 10 and d.startswith("3"):
        d = "57" + d
    return f"https://wa.me/{d}" if len(d) >= 10 else ""


def lista(con, df: pd.DataFrame) -> pd.DataFrame:
    """`df` debe traer todos los pedidos (de la marca elegida), sin filtrar por semana."""
    r = df[df["estado"].isin(["EN_OFICINA", "NOVEDAD"])].copy()
    cols = ["prioridad", "dias", "valor_venta", "cliente", "telefono", "whatsapp", "ciudad", "departamento",
            "transportadora", "estado", "causa", "vendedor", "guia", "id", "marca", "llamado", "resultado", "nota"]
    if r.empty:
        return pd.DataFrame(columns=cols)
    # más días sin resolver y más plata = más urgente
    r["puntaje"] = 0.6 * r["dias"].rank(pct=True) + 0.4 * r["valor_venta"].rank(pct=True)
    r["prioridad"] = pd.cut(r["dias"], [-1, 3, 6, 10**6], labels=["Normal", "Alta", "Urgente"]).astype(str)
    r["whatsapp"] = r["telefono"].map(_whatsapp)

    gestion = pd.read_sql_query("SELECT pedido_id AS id, llamado, resultado, nota FROM llamadas", con)
    r = r.merge(gestion, on="id", how="left")
    r["llamado"] = pd.to_numeric(r["llamado"]).fillna(0).astype(bool)
    r["resultado"] = r["resultado"].fillna("")
    r["nota"] = r["nota"].fillna("")
    return r.sort_values(["llamado", "puntaje"], ascending=[True, False])[cols].reset_index(drop=True)


def guardar_gestion(con, filas: list) -> int:
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for f in filas:
        con.execute(
            """INSERT INTO llamadas(pedido_id, llamado, resultado, nota, fecha_llamada) VALUES (?,?,?,?,?)
               ON CONFLICT(pedido_id) DO UPDATE SET llamado=excluded.llamado, resultado=excluded.resultado,
                 nota=excluded.nota, fecha_llamada=CASE WHEN excluded.llamado=1 THEN excluded.fecha_llamada
                 ELSE llamadas.fecha_llamada END""",
            (f["id"], int(bool(f["llamado"])), f.get("resultado") or "", f.get("nota") or "", ahora))
        n += 1
    con.commit()
    return n
