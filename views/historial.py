import datetime as dt

import pandas as pd
import streamlit as st

from core import catalogo, contexto, export, gastos as gs, graficas, historial, metrics, pareto, ui
from core.fmt import cop, num, pct, veces
from core.semanas import etiqueta, etiqueta_mes

ctx0 = st.session_state["ctx"]
con = ctx0.con
st.title(f"🗂️ Historial · {ctx0.titulo}")
st.caption("Vuelve a cualquier semana o mes para ver qué pasó, **completarlo** con más archivos o gastos y dejar notas. "
           "Aquí no aplica el filtro de semanas del menú.")
if ui.sin_datos(ctx0):
    st.stop()

# contexto con TODO el rango, para ver cualquier período
ctx = contexto.construir(con, ctx0.demo, ctx0.marca, None, None, todo=ctx0.df_todo)
modo = "semana" if st.radio("Ver por", ["Semana", "Mes"], horizontal=True) == "Semana" else "mes"
tabla = historial.periodos(ctx, modo)

st.subheader("Todos los períodos")
ui.tabla(tabla[["etiqueta", "generados", "entregados", "devueltos", "tasa_devolucion", "recaudo", "utilidad_neta",
                "margen_neto", "roas", "gastos_ok", "archivos", "notas", "aviso"]],
         cop_=["recaudo", "utilidad_neta"], pct_=["tasa_devolucion", "margen_neto"],
         num_=["generados", "entregados", "devueltos"], x_=["roas"],
         renombrar={"etiqueta": "Período", "generados": "Pedidos", "entregados": "Entreg.", "devueltos": "Devueltos",
                    "tasa_devolucion": "% devol.", "recaudo": "Recaudo", "utilidad_neta": "Utilidad neta real",
                    "margen_neto": "Margen", "roas": "ROAS", "gastos_ok": "Gastos", "archivos": "Archivos",
                    "notas": "Notas", "aviso": ""})
st.caption("«Gastos ✓» = ya registraste gastos variables (publicidad, etc.) ese período. "
           + ("Un mes incluye las semanas cuyo jueves cae en él." if modo == "mes" else
              "«⚠️ sin pedidos» marca semanas donde falta subir reportes."))

clave = st.selectbox("Abrir período", list(tabla["periodo"]), format_func=historial.etiqueta_periodo)
semanas_p = dict(historial.grupos(ctx.semanas, modo))[clave]
d = ctx.df[ctx.df["semana"].isin(semanas_p)]
g = ctx.gastos[ctx.gastos["semana"].isin(semanas_p)]
k = metrics.kpis(d, g)

st.divider()
st.header(historial.etiqueta_periodo(clave))
if k["generados"] == 0:
    st.warning("No hay pedidos en este período. Puedes completarlo subiendo los reportes que faltan (pestaña Archivos).")

c = st.columns(6)
c[0].metric("Pedidos", num(k["generados"]))
c[1].metric("Entregados", num(k["entregados"]))
c[2].metric("Devueltos", num(k["devueltos"]))
c[3].metric("% devolución", pct(k["tasa_devolucion"]))
c[4].metric("Recaudo", cop(k["recaudo"]))
c[5].metric("Flete perdido", cop(-k["flete_perdido"]))
c = st.columns(6)
c[0].metric("Utilidad bruta", cop(k["utilidad_bruta"]))
c[1].metric("Gastos", cop(-k["gastos_total"]))
c[2].metric("UTILIDAD NETA REAL", cop(k["utilidad_neta"]))
c[3].metric("Margen neto", pct(k["margen_neto"]))
c[4].metric("ROAS", veces(k["roas"]))
c[5].metric("CAC", cop(k["cac"]))

t_res, t_ped, t_gas, t_arc, t_not = st.tabs(["📊 Resumen", "📦 Pedidos", "💸 Gastos", "📎 Archivos", "📝 Notas"])

# semana sobre la que se completa (si vemos un mes, se elige una de sus semanas)
def elegir_semana(key):
    if len(semanas_p) == 1:
        return semanas_p[0]
    return st.selectbox("Semana a completar", semanas_p, index=len(semanas_p) - 1, format_func=etiqueta, key=key)


with t_res:
    if k["generados"]:
        st.plotly_chart(graficas.fig_cascada(k))
        rp = pareto.rentabilidad_producto(d)
        if len(rp):
            st.markdown("**Productos**")
            ui.tabla(rp[["marca", "producto", "entregados", "devueltos", "recaudo", "utilidad_operativa", "tasa_devolucion"]],
                     cop_=["recaudo", "utilidad_operativa"], pct_=["tasa_devolucion"], num_=["entregados", "devueltos"],
                     renombrar={"marca": "Marca", "producto": "Producto", "entregados": "Entreg.", "devueltos": "Devueltos",
                                "recaudo": "Recaudo", "utilidad_operativa": "Utilidad operativa", "tasa_devolucion": "% devol."})
        tr = pareto.efectividad_transportadora(d)
        if len(tr):
            st.markdown("**Transportadoras**")
            ui.tabla(tr[["transportadora", "pedidos", "entregados", "devueltos", "tasa_entrega", "tasa_devolucion", "flete_perdido"]],
                     cop_=["flete_perdido"], pct_=["tasa_entrega", "tasa_devolucion"], num_=["pedidos", "entregados", "devueltos"],
                     renombrar={"transportadora": "Transportadora", "pedidos": "Pedidos", "entregados": "Entreg.",
                                "devueltos": "Devueltos", "tasa_entrega": "% entrega", "tasa_devolucion": "% devol.",
                                "flete_perdido": "Flete perdido"})

with t_ped:
    if d.empty:
        st.info("Sin pedidos en este período.")
    else:
        est = st.multiselect("Estado", sorted(d["estado"].unique()), default=sorted(d["estado"].unique()))
        v = d[d["estado"].isin(est)].sort_values("fecha_pedido", ascending=False)
        ui.tabla(v[["fecha_pedido", "id", "estado", "marca", "producto", "ciudad", "transportadora", "vendedor",
                    "valor_venta", "ganancia", "flete_perdido", "utilidad_operativa"]],
                 cop_=["valor_venta", "ganancia", "flete_perdido", "utilidad_operativa"], fecha_=["fecha_pedido"],
                 renombrar={"fecha_pedido": "Fecha pedido", "id": "ID", "estado": "Estado", "marca": "Marca",
                            "producto": "Producto", "ciudad": "Ciudad", "transportadora": "Transportadora",
                            "vendedor": "Responsable", "valor_venta": "Venta", "ganancia": "Ganancia",
                            "flete_perdido": "Flete perdido", "utilidad_operativa": "Utilidad operativa"}, alto=420)
        st.caption(f"{num(len(v))} pedidos. Cada pedido cuenta en la semana en que llegó a su estado actual.")

with t_gas:
    if g.empty:
        st.info("No hay gastos en este período.")
    else:
        ui.tabla(g.groupby(["grupo", "tipo", "concepto", "marca"], as_index=False)["monto"].sum()
                 .sort_values("monto", ascending=False),
                 cop_=["monto"], renombrar={"grupo": "Grupo", "tipo": "Tipo", "concepto": "Concepto", "marca": "Marca",
                                            "monto": "Monto"})
    st.markdown("**Completar / corregir los gastos variables de una semana**")
    sem_g = elegir_semana("sem_gastos")
    marcas_g = [gs.COMPARTIDO] + catalogo.marcas(con)
    ed = st.data_editor(
        gs.listar_variables(con, sem_g), hide_index=True, num_rows="dynamic", key=f"hist_gv_{sem_g}",
        column_config={
            "tipo": st.column_config.SelectboxColumn("Tipo de gasto", options=gs.TIPOS_VARIABLES, required=True,
                                                     default="Publicidad Meta"),
            "marca": st.column_config.SelectboxColumn("Marca", options=marcas_g, default=gs.COMPARTIDO),
            "monto": st.column_config.NumberColumn("Monto (COP)", min_value=0, step=10000, format="%d", required=True),
            "nota": st.column_config.TextColumn("Nota")})
    if st.button("💾 Guardar gastos de esta semana", type="primary", key="hist_gs"):
        gs.guardar_variables(con, sem_g, ed)
        st.rerun()

with t_arc:
    ws = ",".join("?" * len(semanas_p))
    cargas = pd.read_sql_query(
        f"SELECT archivo, fecha_carga, semana, filas, nuevas, actualizadas, sin_cambio FROM cargas "
        f"WHERE semana IN ({ws}) ORDER BY id DESC", con, params=semanas_p)
    if cargas.empty:
        st.info("Ningún archivo fue asignado a este período todavía.")
    else:
        cargas["fecha_carga"] = pd.to_datetime(cargas["fecha_carga"]).dt.strftime("%d-%m-%Y %H:%M")
        cargas["semana"] = cargas["semana"].map(lambda s: etiqueta(s) if s else "—")
        st.dataframe(cargas.rename(columns={"archivo": "Archivo", "fecha_carga": "Cargado", "semana": "Semana",
                                            "filas": "Filas", "nuevas": "Nuevos", "actualizadas": "Cambiaron de estado",
                                            "sin_cambio": "Sin cambios"}), hide_index=True)
    st.markdown("**Completar con más archivos**")
    ui.subir_a_semana(con, elegir_semana("sem_archivos"), f"hist_{clave}")

with t_not:
    st.markdown("Anota lo que pasó: una campaña nueva, un problema con la transportadora, un cambio de precio…")
    ui.notas_periodo(con, clave, semanas_p if modo == "mes" else ())

st.divider()
nombre = f"historial_{ctx.marca}_{clave}".replace(" ", "_")
ctx_p = contexto.construir(con, ctx.demo, ctx.marca, semanas_p[0], semanas_p[-1], todo=ctx.df_todo)
ui.descarga("Excel de este período", lambda: export.excel_bytes(ctx_p), nombre + ".xlsx", ui.XLSX,
            (ctx.demo, ctx.marca, clave, len(d), round(float(g["monto"].sum()))), "hist_xlsx")
