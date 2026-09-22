"""Exportes a Excel (varias hojas) y PDF (resumen ejecutivo)."""
from __future__ import annotations

import io

import pandas as pd

from . import llamadas, metrics, pareto
from .fmt import cop, dmy, num, pct, veces
from .semanas import etiqueta_corta, texto_rango

# (clave, etiqueta, formato)
FILAS_RESUMEN = [
    ("generados", "Pedidos generados", "n"), ("entregados", "Entregados", "n"), ("devueltos", "Devueltos", "n"),
    ("en_oficina", "En oficina (reclame)", "n"), ("en_transito", "En tránsito", "n"), ("novedad", "En novedad", "n"),
    ("tasa_entrega", "Tasa de entrega", "p"), ("tasa_devolucion", "Tasa de devolución", "p"),
    ("recaudo", "Recaudo cobrado", "$"), ("utilidad_bruta", "Utilidad bruta", "$"),
    ("flete_perdido", "Flete perdido en devoluciones", "$"), ("gastos_publicidad", "Publicidad", "$"),
    ("gastos_fijos", "Gastos fijos (prorrateados)", "$"), ("gastos_variables", "Otros gastos variables", "$"),
    ("utilidad_neta", "UTILIDAD NETA REAL", "$"), ("margen_neto", "Margen neto", "p"),
    ("roas", "ROAS", "x"), ("cac", "CAC (publicidad / entregado)", "$"),
    ("utilidad_prom_entregado", "Utilidad promedio por entregado", "$"),
    ("costo_prom_devolucion", "Costo promedio por devolución", "$"),
    ("dinero_en_riesgo", "Dinero en riesgo (oficina + novedad)", "$"),
]
_FMT = {"n": num, "p": pct, "$": cop, "x": veces}


def valor_fmt(k: dict, clave: str, fmt: str) -> str:
    return _FMT[fmt](k.get(clave))


def _tablas(ctx):
    k = metrics.kpis(ctx.df, ctx.gastos)
    sem = metrics.semanal(ctx.df, ctx.gastos, ctx.semanas)
    return k, sem


def excel_bytes(ctx) -> bytes:
    k, sem = _tablas(ctx)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        f_cop = wb.add_format({"num_format": "$#,##0"})
        f_pct = wb.add_format({"num_format": "0.0%"})
        f_x = wb.add_format({"num_format": '0.00"x"'})
        f_h = wb.add_format({"bold": True, "bg_color": "#036850", "font_color": "white"})

        def hoja(nombre, df, cop_cols=(), pct_cols=(), x_cols=()):
            df = df.copy()
            df.to_excel(xw, sheet_name=nombre, index=False)
            ws = xw.sheets[nombre]
            for i, c in enumerate(df.columns):
                ws.write(0, i, c, f_h)
                fmt = f_cop if c in cop_cols else f_pct if c in pct_cols else f_x if c in x_cols else None
                ancho = max(12, min(40, int(df[c].astype(str).str.len().max() if len(df) else 12) + 2, len(c) + 6))
                ws.set_column(i, i, ancho, fmt)
            ws.freeze_panes(1, 0)

        resumen = pd.DataFrame([{"Indicador": et, "Valor": k.get(cl)} for cl, et, _ in FILAS_RESUMEN])
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        ws = xw.sheets["Resumen"]
        ws.set_column(0, 0, 42)
        ws.set_column(1, 1, 20)
        for i, (cl, et, f) in enumerate(FILAS_RESUMEN, start=1):
            ws.write(i, 1, k.get(cl) if k.get(cl) is not None else "",
                     {"$": f_cop, "p": f_pct, "x": f_x}.get(f))
        ws.write(0, 0, "Indicador", f_h)
        ws.write(0, 1, f"{ctx.titulo} · {texto_rango(ctx.semanas)}", f_h)

        cols_sem = ["semana", "generados", "entregados", "devueltos", "tasa_entrega", "tasa_devolucion", "recaudo",
                    "utilidad_bruta", "flete_perdido", "gastos_publicidad", "gastos_fijos", "gastos_variables",
                    "utilidad_neta", "margen_neto", "roas", "cac"]
        hoja("Semanas", sem[cols_sem], cop_cols=[c for c in cols_sem if c in (
            "recaudo", "utilidad_bruta", "flete_perdido", "gastos_publicidad", "gastos_fijos", "gastos_variables",
            "utilidad_neta", "cac")], pct_cols=["tasa_entrega", "tasa_devolucion", "margen_neto"], x_cols=["roas"])

        rp = pareto.rentabilidad_producto(ctx.df)
        if len(rp):
            hoja("Productos", rp, cop_cols=["recaudo", "utilidad_bruta", "flete_perdido", "utilidad_operativa"],
                 pct_cols=["margen_operativo", "tasa_devolucion"])
        for nombre, g, clave, valor in [("Pareto utilidad", pareto.pareto_utilidad(ctx.df), "producto", "ganancia"),
                                        ("Pareto ventas", pareto.pareto_ventas(ctx.df), "producto", "valor_venta")]:
            if len(g):
                hoja(nombre, g, cop_cols=[valor], pct_cols=["pct", "acumulado"])
        for dim in ("ciudad", "producto", "causa"):
            g = pareto.pareto_devoluciones(ctx.df, dim)
            if len(g):
                hoja(f"Devoluciones por {dim}"[:31], g, cop_cols=["flete_perdido"], pct_cols=["pct", "acumulado"])
        tr = pareto.efectividad_transportadora(ctx.df)
        if len(tr):
            hoja("Transportadoras", tr, cop_cols=["flete_perdido", "utilidad_operativa"],
                 pct_cols=["tasa_entrega", "tasa_devolucion"])
        if len(ctx.gastos):
            hoja("Gastos", ctx.gastos, cop_cols=["monto"])
        ll = llamadas.lista(ctx.con, ctx.df_marca)
        if len(ll):
            hoja("Llamadas", ll.drop(columns=["whatsapp"]), cop_cols=["valor_venta"])
        det = ctx.df[["id", "fecha_pedido", "semana", "estado", "estatus_original", "marca", "producto", "ciudad",
                      "departamento", "transportadora", "vendedor", "valor_venta", "costo_proveedor", "ganancia",
                      "flete_ida", "flete_devolucion", "utilidad_operativa"]].copy()
        for c in ("fecha_pedido",):
            det[c] = det[c].dt.strftime("%d-%m-%Y")
        hoja("Pedidos", det, cop_cols=["valor_venta", "costo_proveedor", "ganancia", "flete_ida",
                                       "flete_devolucion", "utilidad_operativa"])
    return buf.getvalue()


def excel_llamadas(df_llamadas: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    d = df_llamadas.drop(columns=["whatsapp", "marca"], errors="ignore")
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        d.to_excel(xw, sheet_name="Llamadas", index=False)
        ws = xw.sheets["Llamadas"]
        ws.set_column(0, len(d.columns), 18)
        ws.freeze_panes(1, 0)
    return buf.getvalue()


def pdf_bytes(ctx) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    k, sem = _tablas(ctx)
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title="Reporte financiero")
    verde = colors.HexColor("#036850")

    def tabla(datos, anchos=None, cabecera=True):
        t = Table(datos, colWidths=anchos, repeatRows=1 if cabecera else 0)
        estilo = [("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F6")])]
        if cabecera:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), verde), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        t.setStyle(TableStyle(estilo))
        return t

    rango_txt = texto_rango(ctx.semanas)
    el = [Paragraph(f"Reporte financiero · {ctx.titulo}", st["Title"]), Paragraph(rango_txt, st["Normal"]),
          Spacer(1, 0.4 * cm)]
    el.append(tabla([["Indicador", "Valor"]] + [[et, valor_fmt(k, cl, f)] for cl, et, f in FILAS_RESUMEN],
                    [10 * cm, 5 * cm]))
    if len(sem):
        el += [Spacer(1, 0.5 * cm), Paragraph("Evolución semanal", st["Heading3"])]
        datos = [["Semana", "Entreg.", "Dev.", "% dev.", "Recaudo", "U. bruta", "Gastos", "U. neta", "Margen"]]
        for _, r in sem.iterrows():
            datos.append([etiqueta_corta(r["semana"]), num(r["entregados"]), num(r["devueltos"]),
                          pct(r["tasa_devolucion"]), cop(r["recaudo"]), cop(r["utilidad_bruta"]),
                          cop(r["gastos_total"] + r["flete_perdido"]), cop(r["utilidad_neta"]), pct(r["margen_neto"])])
        el.append(tabla(datos))
    rp = pareto.rentabilidad_producto(ctx.df)
    if len(rp):
        el += [Spacer(1, 0.5 * cm), Paragraph("Rentabilidad por producto (antes de gastos)", st["Heading3"])]
        datos = [["Producto", "Entreg.", "Dev.", "Recaudo", "U. operativa", "Margen"]]
        for _, r in rp.head(15).iterrows():
            datos.append([str(r["producto"])[:34], num(r["entregados"]), num(r["devueltos"]), cop(r["recaudo"]),
                          cop(r["utilidad_operativa"]), pct(r["margen_operativo"])])
        el.append(tabla(datos))
    doc.build(el)
    return buf.getvalue()
