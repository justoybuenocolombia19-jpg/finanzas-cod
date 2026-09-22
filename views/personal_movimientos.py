import datetime as dt

import pandas as pd
import streamlit as st

from core import personal
from core.fmt import cop
from core.semanas import etiqueta_mes

ctx = st.session_state["ctx"]
panel = st.session_state["panel_actual"]
con = ctx.con
st.title(f"{panel['icono']} {panel['nombre']} · Ingresos y gastos")

df = personal.cargar(con)

# ------------------------------------------------------------------ registro rápido
st.subheader("Registrar un movimiento")
n = st.session_state.get("mov_n", 0)
tipo = st.radio("Tipo", personal.TIPOS, horizontal=True, format_func=str.capitalize, key=f"mov_tipo_{n}")
c1, c2, c3 = st.columns([1, 2, 1])
fecha = c1.date_input("Fecha", value=dt.date.today(), format="DD/MM/YYYY", key=f"mov_fecha_{n}")
cat = c2.selectbox("Categoría", personal.categorias(tipo), key=f"mov_cat_{n}_{tipo}")
monto = c3.number_input("Monto (COP)", min_value=0, step=1000, key=f"mov_monto_{n}")
nota = st.text_input("Nota (opcional)", key=f"mov_nota_{n}")
if st.button("➕ Agregar", type="primary", disabled=not monto):
    personal.agregar(con, fecha, tipo, cat, monto, nota)
    st.session_state["mov_n"] = n + 1
    st.rerun()

# ------------------------------------------------------------------ editar un mes
st.subheader("Ver y corregir un mes")
meses = sorted(set(df["mes"]) | {personal.mes_actual()}, reverse=True)
mes = st.selectbox("Mes", meses, format_func=etiqueta_mes)
d = df[df["mes"] == mes][["fecha", "tipo", "categoria", "monto", "nota"]].reset_index(drop=True)
t = personal.totales(d)
a, b, c = st.columns(3)
a.metric("Ingresos", cop(t["ingresos"]))
b.metric("Gastos", cop(t["gastos"]))
c.metric("Balance", cop(t["balance"]))

todas = personal.CATEGORIAS_INGRESO + personal.CATEGORIAS_GASTO
ed = st.data_editor(
    d, hide_index=True, num_rows="dynamic", key=f"ed_mov_{mes}",
    column_config={
        "fecha": st.column_config.DateColumn("Fecha", format="DD-MM-YYYY"),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=personal.TIPOS, required=True, default="gasto"),
        "categoria": st.column_config.SelectboxColumn("Categoría", options=todas, required=True),
        "monto": st.column_config.NumberColumn("Monto (COP)", min_value=0, step=1000, format="%d", required=True),
        "nota": st.column_config.TextColumn("Nota"),
    })
st.caption("Puedes editar celdas, agregar filas al final o borrar filas seleccionadas. Nada cambia hasta que guardes.")
if st.button("💾 Guardar cambios de este mes"):
    personal.guardar_mes(con, mes, ed)
    st.success("Movimientos guardados.")
    st.rerun()
