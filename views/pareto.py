import streamlit as st

from core import graficas, pareto, ui
from core.fmt import cop, num, pct
from core.semanas import etiqueta_corta, texto_rango

ctx = st.session_state["ctx"]
st.title(f"🎯 Pareto y rentabilidad · {ctx.titulo}")
if ui.sin_datos(ctx):
    st.stop()
if ctx.df.empty:
    st.info("No hay pedidos en el rango de semanas elegido.")
    st.stop()
st.caption(f"{texto_rango(ctx.semanas)}. En verde: lo que suma el 80 %.")

TOP = 25


def resumen(g, que, unidad="productos"):
    if g.empty:
        st.info("Sin datos suficientes.")
        return
    n = int(g["en_80"].sum())
    st.success(f"**{n} de {len(g)} {unidad}** concentran el **{pct(g.loc[g['en_80'], 'pct'].sum(), 0)}** {que}: "
               + ", ".join(str(x) for x in g.loc[g["en_80"], g.columns[0]].head(8)) + ("…" if n > 8 else ""))


def mostrar(g, clave, valor, titulo, etiqueta_clave, formato="cop"):
    resumen(g, "de este total", "elementos" if clave != "producto" else "productos")
    if g.empty:
        return
    st.plotly_chart(graficas.fig_pareto(g.head(TOP), clave, valor, titulo, formato))
    g2 = g.assign(en_80=g["en_80"].map({True: "✅", False: ""}))
    ui.tabla(g2, cop_=[valor] if formato == "cop" else (), num_=[valor] if formato != "cop" else (),
             pct_=["pct", "acumulado"], renombrar={clave: etiqueta_clave, valor: "Valor", "pct": "% del total",
                                                   "acumulado": "% acumulado", "en_80": "En el 80 %"})


t1, t2, t3, t4, t5, t6 = st.tabs(["Utilidad", "Ventas", "Devoluciones", "Transportadoras",
                                  "Rentabilidad por producto", "Precio y costo"])

with t1:
    st.markdown("**¿Qué productos generan el 80 % de la ganancia?** (utilidad bruta de los entregados)")
    mostrar(pareto.pareto_utilidad(ctx.df), "producto", "ganancia", "Pareto de utilidad por producto", "Producto")

with t2:
    st.markdown("**¿Qué productos concentran el 80 % de las ventas?** (recaudo de los entregados)")
    mostrar(pareto.pareto_ventas(ctx.df), "producto", "valor_venta", "Pareto de ventas por producto", "Producto")

with t3:
    st.markdown("**¿Qué zonas, productos o causas concentran el 80 % de las devoluciones?**")
    c1, c2 = st.columns(2)
    dim = c1.selectbox("Agrupar por", list(pareto.DIMENSIONES_DEVOLUCION), format_func=pareto.DIMENSIONES_DEVOLUCION.get)
    por = c2.radio("Medir en", ["Flete perdido ($)", "Cantidad de devoluciones"], horizontal=True)
    med = "flete_perdido" if por.startswith("Flete") else "pedidos"
    g = pareto.pareto_devoluciones(ctx.df, dim, med)
    mostrar(g, dim, med, f"Devoluciones por {pareto.DIMENSIONES_DEVOLUCION[dim].lower()}",
            pareto.DIMENSIONES_DEVOLUCION[dim], "cop" if med == "flete_perdido" else "num")

with t4:
    st.markdown("**¿Con qué transportadora quedarme?** Tasas sobre pedidos ya resueltos (entregados + devueltos).")
    tr = pareto.efectividad_transportadora(ctx.df)
    if tr.empty:
        st.info("Sin datos.")
    else:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_bar(x=tr["transportadora"], y=tr["tasa_entrega"], name="Tasa de entrega", marker_color=graficas.VERDE_CLARO,
                    text=[pct(v) for v in tr["tasa_entrega"]], textposition="outside")
        fig.add_bar(x=tr["transportadora"], y=tr["tasa_devolucion"], name="Tasa de devolución", marker_color=graficas.ROJO,
                    text=[pct(v) for v in tr["tasa_devolucion"]], textposition="outside")
        fig.update_layout(barmode="group", height=360, yaxis=dict(tickformat=".0%", range=[0, 1.1]),
                          margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig)
        ui.tabla(tr, cop_=["flete_perdido", "utilidad_operativa"], pct_=["tasa_entrega", "tasa_devolucion"],
                 num_=["pedidos", "entregados", "devueltos", "en_oficina", "novedad"],
                 renombrar={"transportadora": "Transportadora", "pedidos": "Pedidos", "entregados": "Entregados",
                            "devueltos": "Devueltos", "en_oficina": "En oficina", "novedad": "Novedad",
                            "flete_perdido": "Flete perdido", "utilidad_operativa": "Utilidad operativa",
                            "tasa_entrega": "% entrega", "tasa_devolucion": "% devolución"})
        if len(tr) > 1 and (tr["entregados"] + tr["devueltos"]).min() < 10:
            st.caption("⚠️ Alguna transportadora tiene menos de 10 pedidos resueltos: sus tasas todavía no son confiables.")

with t5:
    st.markdown("**Rentabilidad por producto** antes de gastos generales: recaudo, utilidad bruta, flete perdido y "
                "utilidad operativa (bruta − flete perdido). La publicidad y los gastos fijos no se pueden atribuir a un "
                "producto, por eso el margen es *operativo*.")
    rp = pareto.rentabilidad_producto(ctx.df)
    if rp.empty:
        st.info("Sin datos.")
    else:
        ui.tabla(rp, cop_=["recaudo", "utilidad_bruta", "flete_perdido", "utilidad_operativa"],
                 pct_=["margen_operativo", "tasa_devolucion"], num_=["pedidos", "entregados", "devueltos"],
                 renombrar={"marca": "Marca", "producto": "Producto", "pedidos": "Pedidos", "entregados": "Entregados",
                            "devueltos": "Devueltos", "recaudo": "Recaudo", "utilidad_bruta": "Utilidad bruta",
                            "flete_perdido": "Flete perdido", "utilidad_operativa": "Utilidad operativa",
                            "margen_operativo": "Margen operativo", "tasa_devolucion": "% devolución"})
        peor = rp[rp["utilidad_operativa"] < 0]
        if len(peor):
            st.error("Productos que pierden plata antes de gastos: " + ", ".join(peor["producto"].astype(str)))

with t6:
    st.markdown("**¿Cambió el precio o el costo de un producto?** El proveedor a veces sube el precio, o tú ajustas "
                "el de venta: aquí ves el promedio semana a semana para detectarlo y comparar el efecto en el margen. "
                "Las líneas punteadas marcan semanas donde el precio o el costo cambiaron más de 1 % frente a la anterior.")
    con_ventas = sorted(ctx.df.loc[ctx.df["estado"] == "ENTREGADO", "producto"].unique())
    if not con_ventas:
        st.info("No hay pedidos entregados en este rango.")
    else:
        prod = st.selectbox("Producto", con_ventas, key="prod_evolucion")
        g = pareto.evolucion_producto(ctx.df, prod)
        if len(g) < 2:
            st.info("Necesitas al menos 2 semanas con ventas de este producto para comparar. "
                    "Prueba eligiendo más semanas en el filtro de la izquierda.")
        else:
            st.plotly_chart(graficas.fig_precio_costo(g, f"Precio de venta y costo de proveedor · {prod}"))
            cambios = g[g["cambio_precio"] | g["cambio_costo"]]
            if len(cambios):
                st.warning("Cambios detectados en: " + ", ".join(etiqueta_corta(s) for s in cambios["semana"]))
            g2 = g.assign(semana=g["semana"].map(etiqueta_corta),
                         cambio=(g["cambio_precio"] | g["cambio_costo"]).map({True: "⚠️", False: ""}))
            ui.tabla(g2, cop_=["precio_venta_prom", "costo_prom", "ganancia_prom"], pct_=["margen_pct"],
                     num_=["entregados"], renombrar={"semana": "Semana", "entregados": "Entregados",
                                                     "precio_venta_prom": "Precio venta prom.",
                                                     "costo_prom": "Costo proveedor prom.",
                                                     "ganancia_prom": "Ganancia prom.", "margen_pct": "Margen",
                                                     "cambio": "Cambió"})
