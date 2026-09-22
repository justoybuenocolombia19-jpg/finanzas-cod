"""Gráficas Plotly con la paleta de Rayzen."""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .fmt import cop, pct
from .semanas import etiqueta_corta

VERDE, VERDE_CLARO, AMARILLO, NARANJA, CAFE = "#036850", "#129C4D", "#F4E600", "#F1AD0E", "#402F16"
ROJO = "#C0392B"
GRIS = "#9AA5A0"
MARCAS = {"Rayzen": VERDE_CLARO, "Dropshipping": NARANJA, "Sin asignar": GRIS}


def _base(fig, titulo="", alto=380):
    fig.update_layout(title=titulo, height=alto, margin=dict(l=10, r=10, t=50 if titulo else 20, b=10),
                      legend=dict(orientation="h", y=-0.2), hovermode="x unified")
    return fig


def fig_pareto(g, clave, valor, titulo, formato="cop", alto=420):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colores = [VERDE_CLARO if e else GRIS for e in g["en_80"]]
    txt = [cop(v) if formato == "cop" else f"{v:,.0f}".replace(",", ".") for v in g[valor]]
    fig.add_bar(x=g[clave].astype(str), y=g[valor], marker_color=colores, text=txt, textposition="outside",
                name="Valor", hovertemplate="%{x}<br>%{text}<extra></extra>")
    fig.add_scatter(x=g[clave].astype(str), y=g["acumulado"] * 100, mode="lines+markers", name="% acumulado",
                    line=dict(color=CAFE), secondary_y=True, hovertemplate="%{y:.1f}%<extra></extra>")
    fig.add_hline(y=80, line_dash="dot", line_color=NARANJA, secondary_y=True)
    fig.update_yaxes(title_text="", secondary_y=False, showgrid=False)
    fig.update_yaxes(range=[0, 105], ticksuffix="%", secondary_y=True)
    return _base(fig, titulo, alto)


def fig_cascada(k):
    """De la utilidad bruta a la utilidad neta real."""
    pasos = [("Utilidad bruta", k["utilidad_bruta"], "absolute"),
             ("Flete perdido en devoluciones", -k["flete_perdido"], "relative"),
             ("Publicidad", -k["gastos_publicidad"], "relative"),
             ("Gastos fijos", -k["gastos_fijos"], "relative"),
             ("Otros gastos variables", -k["gastos_variables"], "relative"),
             ("Utilidad neta real", k["utilidad_neta"], "total")]
    fig = go.Figure(go.Waterfall(
        x=[p[0] for p in pasos], y=[p[1] for p in pasos], measure=[p[2] for p in pasos],
        text=[cop(p[1]) for p in pasos], textposition="outside",
        increasing=dict(marker_color=VERDE_CLARO), decreasing=dict(marker_color=ROJO),
        totals=dict(marker_color=VERDE if k["utilidad_neta"] >= 0 else ROJO), connector=dict(line=dict(color=GRIS))))
    fig.update_layout(showlegend=False)
    return _base(fig, "De la utilidad bruta a la utilidad neta real")


def fig_estados(k):
    datos = [("Entregados", k["entregados"], VERDE_CLARO), ("Devueltos", k["devueltos"], ROJO),
             ("En oficina", k["en_oficina"], NARANJA), ("Novedad", k["novedad"], AMARILLO),
             ("En tránsito", k["en_transito"], GRIS)]
    datos = [d for d in datos if d[1]]
    fig = go.Figure(go.Pie(labels=[d[0] for d in datos], values=[d[1] for d in datos], hole=0.55,
                           marker=dict(colors=[d[2] for d in datos]), textinfo="label+value"))
    fig.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def fig_linea(sem, columna, titulo, formato="cop", color=VERDE_CLARO, barras=False):
    x = [etiqueta_corta(s) for s in sem["semana"]]
    y = sem[columna]
    if formato == "cop":
        txt = [cop(v) for v in y]
    elif formato == "pct":
        txt = [pct(v) for v in y]
    else:
        txt = [("—" if v is None or v != v else f"{v:.2f}x") for v in y]
    fig = go.Figure()
    if barras:
        colores = [color if (v or 0) >= 0 else ROJO for v in y]
        fig.add_bar(x=x, y=y, marker_color=colores, text=txt, textposition="outside", hoverinfo="x+text")
    else:
        fig.add_scatter(x=x, y=y, mode="lines+markers+text", text=txt, textposition="top center",
                        line=dict(color=color, width=3), hoverinfo="x+text")
    if formato == "pct":
        fig.update_yaxes(tickformat=".0%")
    fig.update_layout(showlegend=False)
    return _base(fig, titulo, 320)


def fig_precio_costo(g, titulo=""):
    x = [etiqueta_corta(s) for s in g["semana"]]
    fig = go.Figure()
    fig.add_scatter(x=x, y=g["precio_venta_prom"], mode="lines+markers+text", name="Precio de venta",
                    text=[cop(v) for v in g["precio_venta_prom"]], textposition="top center", line=dict(color=VERDE_CLARO, width=3))
    fig.add_scatter(x=x, y=g["costo_prom"], mode="lines+markers+text", name="Costo proveedor",
                    text=[cop(v) for v in g["costo_prom"]], textposition="bottom center", line=dict(color=NARANJA, width=3))
    cambios = g[g["cambio_precio"] | g["cambio_costo"]]
    for _, r in cambios.iterrows():
        fig.add_vline(x=etiqueta_corta(r["semana"]), line_dash="dot", line_color=ROJO, opacity=0.5)
    return _base(fig, titulo, 360)
