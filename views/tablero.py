import streamlit as st

from core import export, graficas, metrics, ui
from core.contexto import CONSOLIDADO
from core.fmt import cop, num, pct, veces
from core.semanas import etiqueta, slug_rango, texto_rango

ctx = st.session_state["ctx"]
st.title(f"📊 Tablero · {ctx.titulo}")
if ui.sin_datos(ctx):
    st.stop()

st.caption(f"{texto_rango(ctx.semanas)}  ·  {len(ctx.semanas)} semana(s)")

sin_marca = int((ctx.df_rango_todas["marca"] == "Sin asignar").sum())
if sin_marca:
    st.warning(f"{num(sin_marca)} pedidos no tienen marca (su producto no está asignado a una marca). "
               "Solo aparecen en «Consolidado».")
    st.page_link("views/catalogo.py", label="Asignar marcas en el Catálogo", icon="🏷️")

k = metrics.kpis(ctx.df, ctx.gastos)

st.subheader("Operación")
c = st.columns(6)
c[0].metric("Pedidos generados", num(k["generados"]))
c[1].metric("Entregados", num(k["entregados"]))
c[2].metric("Devueltos", num(k["devueltos"]))
c[3].metric("En oficina", num(k["en_oficina"]))
c[4].metric("En tránsito", num(k["en_transito"]))
c[5].metric("En novedad", num(k["novedad"]))
c = st.columns(3)
c[0].metric("Tasa de entrega", pct(k["tasa_entrega"]), help="Entregados / (Entregados + Devueltos)")
c[1].metric("Tasa de devolución", pct(k["tasa_devolucion"]), help="Devueltos / (Entregados + Devueltos)")
c[2].metric("Dinero en riesgo ahora", cop(k["dinero_en_riesgo"]),
            help=f"{num(k['pedidos_en_riesgo'])} pedidos en oficina o novedad que el equipo debe gestionar")

st.subheader("Dinero real")
if k["gastos_total"] == 0:
    st.warning("No hay gastos registrados en este rango, así que la utilidad neta todavía **no descuenta** publicidad, "
               "apps, nómina ni administrativos.")
    st.page_link("views/gastos.py", label="Registrar gastos", icon="💸")
c = st.columns(4)
c[0].metric("Recaudo cobrado", cop(k["recaudo"]), help="Valor de compra de los pedidos ENTREGADOS")
c[1].metric("Utilidad bruta", cop(k["utilidad_bruta"]), help="GANANCIA de la plataforma (ya descuenta el flete de ida)")
c[2].metric("Flete perdido en devoluciones", cop(-k["flete_perdido"]), help="Flete de ida + flete de devolución de los devueltos")
c[3].metric("Gastos", cop(-k["gastos_total"]), help="Publicidad + fijos prorrateados + variables")
c = st.columns(4)
c[0].metric("UTILIDAD NETA REAL", cop(k["utilidad_neta"]), help="Utilidad bruta − Flete perdido − Gastos")
c[1].metric("Margen neto", pct(k["margen_neto"]), help="Utilidad neta real / Recaudo cobrado")
c[2].metric("ROAS", veces(k["roas"]), help="Recaudo cobrado / Inversión en publicidad")
c[3].metric("CAC", cop(k["cac"]), help="Inversión en publicidad / Pedidos entregados")
c = st.columns(4)
c[0].metric("Utilidad prom. por entregado", cop(k["utilidad_prom_entregado"]))
c[1].metric("Costo prom. por devolución", cop(k["costo_prom_devolucion"]))
c[2].metric("Publicidad", cop(k["gastos_publicidad"]))
c[3].metric("Gastos fijos", cop(k["gastos_fijos"]))

izq, der = st.columns([3, 2])
izq.plotly_chart(graficas.fig_cascada(k))
der.markdown("**Estado de los pedidos**")
der.plotly_chart(graficas.fig_estados(k))

if ctx.marca == CONSOLIDADO:
    con_datos = [m for m in ctx.marcas if (ctx.df["marca"] == m).any()]
    if len(con_datos) >= 2:
        st.subheader("Cada marca por separado")
        pm = metrics.por_marca(ctx.df, ctx.gastos_de, con_datos)
        ui.tabla(pm[["marca", "entregados", "devueltos", "tasa_devolucion", "recaudo", "utilidad_bruta", "flete_perdido",
                     "gastos_total", "utilidad_neta", "margen_neto", "roas"]],
                 cop_=["recaudo", "utilidad_bruta", "flete_perdido", "gastos_total", "utilidad_neta"],
                 pct_=["tasa_devolucion", "margen_neto"], num_=["entregados", "devueltos"], x_=["roas"],
                 renombrar={"marca": "Marca", "entregados": "Entregados", "devueltos": "Devueltos",
                            "tasa_devolucion": "% devolución", "recaudo": "Recaudo", "utilidad_bruta": "Utilidad bruta",
                            "flete_perdido": "Flete perdido", "gastos_total": "Gastos", "utilidad_neta": "Utilidad neta real",
                            "margen_neto": "Margen", "roas": "ROAS"})
        if (ctx.gastos["marca"] == "Compartido").any():
            st.caption("Los gastos compartidos (sin marca) se reparten según el recaudo de cada marca.")

st.divider()
st.subheader("Exportar")
nombre = f"reporte_{ctx.titulo}_{slug_rango(ctx.semanas)}".replace(" ", "_")
sig = ui.firma(ctx)
a, b = st.columns(2)
with a:
    ui.descarga("Excel", lambda: export.excel_bytes(ctx), nombre + ".xlsx", ui.XLSX, sig, "xlsx")
with b:
    ui.descarga("PDF", lambda: export.pdf_bytes(ctx), nombre + ".pdf", "application/pdf", sig, "pdf")
