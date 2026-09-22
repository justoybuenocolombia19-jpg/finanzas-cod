import streamlit as st

from core import graficas, metrics, ui
from core.fmt import cop, num, pct, veces
from core.semanas import etiqueta, etiqueta_corta, texto_rango

ctx = st.session_state["ctx"]
st.title(f"📈 Semanas y tendencias · {ctx.titulo}")
if ui.sin_datos(ctx):
    st.stop()
st.caption(texto_rango(ctx.semanas))

sem = metrics.semanal(ctx.df, ctx.gastos, ctx.semanas)
if len(sem):
    sem = sem[(sem["generados"] > 0) | (sem["gastos_total"] > 0)].reset_index(drop=True)
if sem.empty:
    st.info("No hay semanas con datos en el rango elegido.")
    st.stop()

# ---- comparar dos semanas
st.subheader("Comparar semanas")
opts = list(sem["semana"])
c1, c2 = st.columns(2)
b = c1.selectbox("Semana", opts, index=len(opts) - 1, format_func=etiqueta)
a = c2.selectbox("Contra", opts, index=max(len(opts) - 2, 0), format_func=etiqueta)
ka, kb = sem[sem["semana"] == a].iloc[0], sem[sem["semana"] == b].iloc[0]


def delta(campo, fmt, inverso=False):
    x, y = kb[campo], ka[campo]
    if x is None or y is None or x != x or y != y:
        return None, "off"
    d = x - y
    txt = pct(d) if fmt == pct else fmt(d)
    return txt, ("inverse" if inverso else "normal")


cols = st.columns(5)
for col, (campo, etq, fmt, inv) in zip(cols, [
        ("utilidad_neta", "Utilidad neta real", cop, False), ("recaudo", "Recaudo", cop, False),
        ("tasa_devolucion", "% devolución", pct, True), ("roas", "ROAS", veces, False),
        ("entregados", "Entregados", num, False)]):
    d, color = delta(campo, fmt, inv)
    col.metric(etq, fmt(kb[campo]), d, delta_color=color)

# ---- gráficas
st.subheader("Evolución semana a semana")
g1, g2 = st.columns(2)
g1.plotly_chart(graficas.fig_linea(sem, "utilidad_neta", "Utilidad neta real", "cop", graficas.VERDE_CLARO, barras=True))
g2.plotly_chart(graficas.fig_linea(sem, "margen_neto", "Margen neto", "pct", graficas.VERDE))
g3, g4 = st.columns(2)
g3.plotly_chart(graficas.fig_linea(sem, "tasa_devolucion", "Tasa de devolución", "pct", graficas.ROJO))
g4.plotly_chart(graficas.fig_linea(sem, "roas", "ROAS", "x", graficas.NARANJA))

# ---- tabla
st.subheader("Detalle por semana")
t = sem.assign(semana=sem["semana"].map(etiqueta_corta))
ui.tabla(t[["semana", "generados", "entregados", "devueltos", "tasa_devolucion", "recaudo", "utilidad_bruta",
            "flete_perdido", "gastos_total", "utilidad_neta", "margen_neto", "roas", "cac"]],
         cop_=["recaudo", "utilidad_bruta", "flete_perdido", "gastos_total", "utilidad_neta", "cac"],
         pct_=["tasa_devolucion", "margen_neto"], num_=["generados", "entregados", "devueltos"], x_=["roas"],
         renombrar={"semana": "Semana", "generados": "Pedidos", "entregados": "Entreg.", "devueltos": "Devueltos",
                    "tasa_devolucion": "% devol.", "recaudo": "Recaudo", "utilidad_bruta": "Util. bruta",
                    "flete_perdido": "Flete perdido", "gastos_total": "Gastos", "utilidad_neta": "Util. neta real",
                    "margen_neto": "Margen", "roas": "ROAS", "cac": "CAC"})
st.caption("Cada pedido cuenta en la semana en que llegó a su estado final (configurable en Cargar archivos → Ajustes).")
