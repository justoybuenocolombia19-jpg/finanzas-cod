import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import graficas, pareto, personal, ui
from core.fmt import cop, pct
from core.semanas import etiqueta_mes

ctx = st.session_state["ctx"]
panel = st.session_state["panel_actual"]
con = ctx.con
st.title(f"{panel['icono']} {panel['nombre']} · Resumen")

df = personal.cargar(con)
if df.empty:
    st.info("Aún no hay movimientos. Registra tus ingresos y gastos para ver el resumen.")
    st.page_link("views/personal_movimientos.py", label="Registrar ingresos y gastos", icon="💸")
    st.stop()

meses = sorted(df["mes"].unique(), reverse=True)
mes = st.selectbox("Mes", meses, format_func=etiqueta_mes)
d = df[df["mes"] == mes]
t = personal.totales(d)
previo = [m for m in meses if m < mes]
tp = personal.totales(df[df["mes"] == previo[0]]) if previo else None

c = st.columns(4)
c[0].metric("Ingresos", cop(t["ingresos"]), cop(t["ingresos"] - tp["ingresos"]) if tp else None)
c[1].metric("Gastos", cop(t["gastos"]), cop(t["gastos"] - tp["gastos"]) if tp else None, delta_color="inverse")
c[2].metric("Balance", cop(t["balance"]), cop(t["balance"] - tp["balance"]) if tp else None,
            help="Ingresos − gastos")
c[3].metric("% que te queda", pct(t["ahorro"]), help="Balance / ingresos")
if tp:
    st.caption(f"Las diferencias son contra {etiqueta_mes(previo[0])}.")

izq, der = st.columns([3, 2])
gastos = pareto.pareto(d[d["tipo"] == "gasto"], "categoria", "monto")
with izq:
    st.markdown("**¿En qué se va la plata?** (Pareto: en verde lo que suma el 80 % de tus gastos)")
    if gastos.empty:
        st.info("Sin gastos este mes.")
    else:
        st.plotly_chart(graficas.fig_pareto(gastos, "categoria", "monto", "Gastos por categoría", alto=380))
with der:
    ing = personal.por_categoria(d, "ingreso")
    st.markdown("**Ingresos por categoría**")
    if ing.empty:
        st.info("Sin ingresos este mes.")
    else:
        ui.tabla(ing, cop_=["monto"], renombrar={"categoria": "Categoría", "monto": "Monto"})

st.subheader("Mes a mes")
hist = personal.periodos(con, df, "mes").sort_values("periodo")
fig = go.Figure()
fig.add_bar(x=hist["etiqueta"], y=hist["ingresos"], name="Ingresos", marker_color=graficas.VERDE_CLARO)
fig.add_bar(x=hist["etiqueta"], y=hist["gastos"], name="Gastos", marker_color=graficas.NARANJA)
fig.add_scatter(x=hist["etiqueta"], y=hist["balance"], name="Balance", mode="lines+markers",
                line=dict(color=graficas.CAFE, width=3))
fig.update_layout(barmode="group", height=340, margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig)
