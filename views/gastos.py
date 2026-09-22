import datetime as dt

import pandas as pd
import streamlit as st

from core import catalogo, gastos as gs, ui
from core.fmt import cop
from core.semanas import etiqueta, etiqueta_corta, semana_de, texto_rango

ctx = st.session_state["ctx"]
con = ctx.con
marcas = [gs.COMPARTIDO] + catalogo.marcas(con)

st.title("💸 Gastos")
st.caption("Lo que NO viene en los reportes de Dropi: publicidad, apps, nómina, administrativos… "
           "Entran a la **utilidad neta real**, al ROAS y al CAC.")

t_fijos, t_sem, t_res = st.tabs(["Gastos fijos mensuales", "Gastos de la semana", "Resumen"])

# ------------------------------------------------------------------ fijos
with t_fijos:
    st.markdown("Se configuran **una sola vez**: la app los reparte por días en cada semana "
                "(mensual ÷ días del mes × días de la semana). Sin marca = **Compartido** "
                "(se reparte entre marcas según su recaudo).")
    fijos = gs.listar_fijos(con)
    fijos["desde"] = pd.to_datetime(fijos["desde"], errors="coerce")
    fijos["hasta"] = pd.to_datetime(fijos["hasta"], errors="coerce")
    fijos["activo"] = fijos["activo"].astype(bool)
    editado = st.data_editor(
        fijos, hide_index=True, num_rows="dynamic", key="ed_fijos",
        column_order=["concepto", "categoria", "monto_mensual", "marca", "desde", "hasta", "activo"],
        column_config={
            "concepto": st.column_config.TextColumn("Concepto", required=True, help="Ej: Lucid Bot, Notion, sueldo Yina, contador"),
            "categoria": st.column_config.SelectboxColumn("Categoría", options=gs.CATEGORIAS_FIJOS, required=True,
                                                          default=gs.CATEGORIAS_FIJOS[0]),
            "monto_mensual": st.column_config.NumberColumn("Monto mensual (COP)", min_value=0, step=10000, format="%d", required=True),
            "marca": st.column_config.SelectboxColumn("Marca", options=marcas, default=gs.COMPARTIDO),
            "desde": st.column_config.DateColumn("Desde", format="DD-MM-YYYY", help="Vacío = siempre"),
            "hasta": st.column_config.DateColumn("Hasta", format="DD-MM-YYYY", help="Vacío = sin fin"),
            "activo": st.column_config.CheckboxColumn("Activo", default=True),
        })
    activos = editado[editado["activo"].fillna(True).astype(bool)] if len(editado) else editado
    total_mes = float(pd.to_numeric(activos.get("monto_mensual"), errors="coerce").fillna(0).sum()) if len(activos) else 0.0
    a, b = st.columns(2)
    a.metric("Total fijos por mes", cop(total_mes))
    b.metric("Equivale por semana (aprox.)", cop(total_mes * 12 / 52))
    if st.button("💾 Guardar gastos fijos", type="primary"):
        gs.guardar_fijos(con, editado)
        st.success("Gastos fijos guardados.")
        st.rerun()
    if len(editado):
        por_cat = activos.assign(monto_mensual=pd.to_numeric(activos["monto_mensual"], errors="coerce").fillna(0)) \
            .groupby("categoria")["monto_mensual"].sum().reset_index()
        st.markdown("**Por categoría (mensual)**")
        ui.tabla(por_cat, cop_=["monto_mensual"], renombrar={"categoria": "Categoría", "monto_mensual": "Por mes"})

# ------------------------------------------------------------------ variables por semana
with t_sem:
    hoy = dt.date.today()
    previa = semana_de(hoy - dt.timedelta(days=7))
    opciones = sorted(set(ctx.semanas_disponibles) | {previa, semana_de(hoy)}, reverse=True)
    sem = st.selectbox("Semana", opciones, index=opciones.index(previa), format_func=etiqueta)
    st.markdown("Registra la inversión en **publicidad por plataforma**, empaques, comisiones y otros. "
                "Una fila por gasto; puedes asignarlo a una marca o dejarlo compartido.")

    var = gs.listar_variables(con, sem)
    if var.empty:
        ant = semana_de(dt.date.fromisocalendar(int(sem[:4]), int(sem[-2:]), 1) - dt.timedelta(days=7))
        if len(gs.listar_variables(con, ant)) and st.button(f"📋 Copiar los gastos de {etiqueta_corta(ant)}"):
            base = gs.listar_variables(con, ant)
            gs.guardar_variables(con, sem, base)
            st.rerun()
    ed = st.data_editor(
        var, hide_index=True, num_rows="dynamic", key=f"ed_var_{sem}",
        column_config={
            "tipo": st.column_config.SelectboxColumn("Tipo de gasto", options=gs.TIPOS_VARIABLES, required=True,
                                                     default="Publicidad Meta"),
            "marca": st.column_config.SelectboxColumn("Marca", options=marcas, default=gs.COMPARTIDO),
            "monto": st.column_config.NumberColumn("Monto (COP)", min_value=0, step=10000, format="%d", required=True),
            "nota": st.column_config.TextColumn("Nota"),
        })
    pub = pd.to_numeric(ed.loc[ed["tipo"].map(gs.es_publicidad), "monto"], errors="coerce").sum() if len(ed) else 0
    tot = pd.to_numeric(ed["monto"], errors="coerce").sum() if len(ed) else 0
    a, b = st.columns(2)
    a.metric("Publicidad de la semana", cop(pub))
    b.metric("Total variables de la semana", cop(tot))
    if st.button("💾 Guardar gastos de la semana", type="primary"):
        gs.guardar_variables(con, sem, ed)
        st.success(f"Gastos de {etiqueta(sem)} guardados.")
        st.rerun()

    fijos_sem = gs.fijos_por_semana(con, [sem])
    if len(fijos_sem):
        with st.expander(f"Gastos fijos que le tocan a esta semana: {cop(fijos_sem['monto'].sum())}"):
            ui.tabla(fijos_sem[["tipo", "concepto", "marca", "monto"]].sort_values("monto", ascending=False),
                     cop_=["monto"], renombrar={"tipo": "Categoría", "concepto": "Concepto", "marca": "Marca", "monto": "En la semana"})

# ------------------------------------------------------------------ resumen
with t_res:
    st.markdown(f"**{ctx.titulo}** · {texto_rango(ctx.semanas)}" if ctx.semanas
                else "Sin semanas con datos todavía.")
    g = ctx.gastos
    if g.empty:
        st.info("Aún no hay gastos en este rango.")
    else:
        a, b, c = st.columns(3)
        a.metric("Total gastos", cop(g["monto"].sum()))
        a2 = g.loc[g["tipo"].map(gs.es_publicidad), "monto"].sum()
        b.metric("Publicidad", cop(a2))
        c.metric("Fijos", cop(g.loc[g["grupo"] == "Fijo", "monto"].sum()))
        pv = g.pivot_table(index="semana", columns="tipo", values="monto", aggfunc="sum", fill_value=0)
        pv["TOTAL"] = pv.sum(axis=1)
        pv.index = [etiqueta_corta(s) for s in pv.index]
        st.dataframe(pv.reset_index().rename(columns={"index": "Semana"}).pipe(
            lambda d: d.assign(**{c: d[c].map(cop) for c in d.columns if c != "Semana"})), hide_index=True)
        if ctx.marca != "Consolidado" and (g["marca"] == gs.COMPARTIDO).any():
            st.caption("Incluye la parte proporcional (según recaudo) de los gastos compartidos.")
