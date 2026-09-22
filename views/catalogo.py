import pandas as pd
import streamlit as st

from core import catalogo, ui
from core.fmt import cop, num

ctx = st.session_state["ctx"]
con = ctx.con
marcas = catalogo.marcas(con)

st.title("🏷️ Catálogo y marcas")
st.caption("Los reportes no dicen a qué marca pertenece cada pedido, pero sí el precio de venta. La app crea un "
           "producto por cada precio distinto; aquí lo nombras, lo asignas a una marca y agrupas variantes. "
           "Si este panel tiene una sola marca, todos sus pedidos ya cuentan para ella.")
if ui.sin_datos(ctx):
    st.stop()

sin_marca = int((ctx.df_todo["marca"] == "Sin asignar").sum())
if sin_marca:
    st.warning(f"{num(sin_marca)} pedidos siguen sin marca. Asigna una marca a los productos de abajo.")

# ------------------------------------------------------------------ marcas
with st.expander(f"🏷️ Marcas de este panel: {', '.join(marcas)}"):
    ed_m = st.data_editor(pd.DataFrame(catalogo.listar_marcas(con)), hide_index=True, key="ed_marcas",
                          column_order=["nombre"], column_config={"nombre": st.column_config.TextColumn("Marca", required=True)})
    if st.button("💾 Guardar nombres de marcas"):
        err = catalogo.guardar_marcas(con, ed_m.to_dict("records"))
        st.error(err) if err else st.rerun()
    nueva = st.text_input("Agregar otra marca", key="nueva_marca", placeholder="Ej: Rayzen Premium")
    if st.button("➕ Agregar marca", disabled=not nueva.strip()):
        err = catalogo.agregar_marca(con, nueva)
        if err:
            st.error(err)
        else:
            st.session_state.pop("nueva_marca", None)
            st.rerun()

# ------------------------------------------------------------------ productos
st.subheader("1 · Productos")
prods = pd.DataFrame(catalogo.productos(con))
ed = st.data_editor(
    prods, hide_index=True, key="ed_productos", disabled=["precios"],
    column_order=["nombre", "sku", "marca", "precios"],
    column_config={
        "nombre": st.column_config.TextColumn("Nombre del producto", required=True),
        "sku": st.column_config.TextColumn("SKU (opcional)"),
        "marca": st.column_config.SelectboxColumn("Marca", options=marcas),
        "precios": st.column_config.TextColumn("Precios de venta que agrupa"),
    })
if st.button("💾 Guardar productos", type="primary"):
    err = catalogo.guardar_productos(con, ed.to_dict("records"))
    if err:
        st.error(err)
    else:
        st.success("Productos guardados.")
        st.rerun()

with st.form("nuevo_producto", clear_on_submit=True):
    st.markdown("**Agregar un producto** (útil para agrupar varios precios bajo un mismo nombre)")
    c1, c2, c3 = st.columns([3, 2, 1])
    nombre = c1.text_input("Nombre")
    marca = c2.selectbox("Marca", [""] + marcas)
    if c3.form_submit_button("Agregar") and nombre.strip():
        cur = con.execute("INSERT INTO productos(nombre, marca_id) VALUES (?,?)", (nombre.strip(), catalogo.marca_id(con, marca)))
        con.commit()
        st.rerun()

# ------------------------------------------------------------------ precios
st.subheader("2 · Precios de venta detectados → producto")
st.caption("Si dos precios son variantes del mismo producto (por ejemplo, con y sin oferta), apunta ambos al mismo producto.")
pr = pd.DataFrame(catalogo.precios(con))
nombres = [p["nombre"] for p in catalogo.productos(con)]
ed_p = st.data_editor(
    pr, hide_index=True, key="ed_precios", disabled=["precio", "pedidos"],
    column_config={
        "precio": st.column_config.NumberColumn("Precio de venta", format="%d"),
        "pedidos": st.column_config.NumberColumn("Pedidos", format="%d"),
        "producto": st.column_config.SelectboxColumn("Producto", options=nombres, required=True),
    })
c1, c2 = st.columns([1, 3])
if c1.button("💾 Guardar precios", type="primary"):
    catalogo.guardar_precios(con, ed_p.to_dict("records"))
    catalogo.eliminar_productos_huerfanos(con)
    st.success("Precios asignados. Los productos que quedaron sin precios se eliminaron.")
    st.rerun()
c2.caption("Guarda primero los nombres de producto (paso 1) antes de reasignar precios.")

# ------------------------------------------------------------------ tiendas
tiendas = catalogo.tiendas(con)
if tiendas:
    st.subheader("3 · Tiendas → marca (respaldo)")
    st.caption("Solo se usa si un producto no tiene marca. Útil si cada marca vende desde una tienda distinta en la plataforma.")
    ed_t = st.data_editor(
        pd.DataFrame(tiendas), hide_index=True, key="ed_tiendas", disabled=["tienda_id", "pedidos"],
        column_config={"tienda_id": "ID de tienda", "pedidos": st.column_config.NumberColumn("Pedidos", format="%d"),
                       "marca": st.column_config.SelectboxColumn("Marca", options=marcas)})
    if st.button("💾 Guardar tiendas"):
        catalogo.guardar_tiendas(con, ed_t.to_dict("records"))
        st.success("Tiendas guardadas.")
        st.rerun()
