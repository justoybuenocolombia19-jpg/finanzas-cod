import streamlit as st

from core import historial, personal, ui
from core.fmt import cop, num, pct, dmy

ctx = st.session_state["ctx"]
panel = st.session_state["panel_actual"]
con = ctx.con
st.title(f"🗂️ {panel['nombre']} · Historial")
st.caption("Vuelve a cualquier semana o mes, revisa qué pasó y deja notas.")

df = personal.cargar(con)
if df.empty:
    st.info("Aún no hay movimientos.")
    st.page_link("views/personal_movimientos.py", label="Registrar ingresos y gastos", icon="💸")
    st.stop()

modo = "semana" if st.radio("Ver por", ["Semana", "Mes"], horizontal=True) == "Semana" else "mes"
tabla = personal.periodos(con, df, modo)
ui.tabla(tabla[["etiqueta", "ingresos", "gastos", "balance", "ahorro", "movimientos", "notas"]],
         cop_=["ingresos", "gastos", "balance"], pct_=["ahorro"], num_=["movimientos", "notas"],
         renombrar={"etiqueta": "Período", "ingresos": "Ingresos", "gastos": "Gastos", "balance": "Balance",
                    "ahorro": "% que queda", "movimientos": "Movimientos", "notas": "Notas"})

clave = st.selectbox("Abrir período", list(tabla["periodo"]), format_func=historial.etiqueta_periodo)
d = df[df["semana" if modo == "semana" else "mes"] == clave]
t = personal.totales(d)
st.divider()
st.header(historial.etiqueta_periodo(clave))
c = st.columns(4)
c[0].metric("Ingresos", cop(t["ingresos"]))
c[1].metric("Gastos", cop(t["gastos"]))
c[2].metric("Balance", cop(t["balance"]))
c[3].metric("% que queda", pct(t["ahorro"]))

t1, t2 = st.tabs(["💸 Movimientos", "📝 Notas"])
with t1:
    v = d.sort_values("fecha", ascending=False)
    ui.tabla(v[["fecha", "tipo", "categoria", "monto", "nota"]], cop_=["monto"], fecha_=["fecha"],
             renombrar={"fecha": "Fecha", "tipo": "Tipo", "categoria": "Categoría", "monto": "Monto", "nota": "Nota"})
    cat = personal.por_categoria(d, "gasto")
    if len(cat):
        st.markdown("**Gastos por categoría**")
        ui.tabla(cat, cop_=["monto"], renombrar={"categoria": "Categoría", "monto": "Monto"})
with t2:
    ui.notas_periodo(con, clave)
