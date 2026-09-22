"""Finanzas y operaciones COD. Ejecutar: streamlit run app.py

Modo nube (varias cuentas): se activa solo si existen los secrets TURSO_DATABASE_URL y
TURSO_AUTH_TOKEN (ver .streamlit/secrets.toml.example y DEPLOY.md). Sin esos secrets, la
app funciona exactamente como siempre: local, sin login, con data/paneles.json.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from core import catalogo, cloud_db, contexto, data, demo, paneles, ui
from core.contexto import CONSOLIDADO
from core.semanas import etiqueta_corta, semanas_entre

st.set_page_config(page_title="Finanzas COD", page_icon="📦", layout="wide")


def _secreto(clave: str):
    """TURSO_* se busca primero en los secrets de Streamlit (despliegue normal) y si no
    en variables de entorno (útil para pruebas, sin tocar ningún archivo)."""
    try:
        v = st.secrets.get(clave)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(clave)


MODO_NUBE = bool(_secreto("TURSO_DATABASE_URL") and _secreto("TURSO_AUTH_TOKEN"))

# ============================================================ modo nube: login / registro
usuario = None
con_central = None
if MODO_NUBE:
    if "con_central" not in st.session_state:
        try:
            st.session_state["con_central"] = cloud_db.conectar_central(
                _secreto("TURSO_DATABASE_URL"), _secreto("TURSO_AUTH_TOKEN"))
        except Exception as e:
            st.error(f"No se pudo conectar con la base de datos en la nube: {e}")
            if st.button("Reintentar"):
                st.rerun()
            st.stop()
    con_central = st.session_state["con_central"]

    if not st.session_state.get("usuario"):
        ui.pantalla_login(con_central)
        st.stop()
    usuario = st.session_state["usuario"]

# ============================================================ selector de paneles
demo_on = False
with st.sidebar:
    demo_on = st.toggle("🧪 Modo demo (datos de ejemplo)", key="demo",
                        help="Usa una base aparte con datos ficticios. Tus paneles reales no se tocan.")
    if MODO_NUBE:
        st.caption(f"👤 {usuario['email']}")
        if st.button("Cerrar sesión"):
            for k in ("usuario", "con_central"):
                st.session_state.pop(k, None)
            st.rerun()

if (pedido := st.session_state.pop("_panel_solicitado", None)):
    st.session_state["panel"] = pedido

if demo_on:
    lista = [paneles.PANEL_DEMO]
elif MODO_NUBE:
    lista = paneles.listar_nube(con_central, usuario["id"])
else:
    lista = paneles.listar()

if not lista and MODO_NUBE:
    # cuenta recién creada: todavía no tiene ningún panel — se pide el primero antes de mostrar nada más
    st.title("📦 ¡Bienvenido!")
    st.info("Crea tu primer panel para empezar. Un panel es un espacio independiente: sus propios "
            "pedidos, gastos y catálogo. Puedes crear más después (uno por marca, o uno personal).")
    with st.form("primer_panel"):
        c1, c2 = st.columns([3, 1])
        nombre = c1.text_input("Nombre", placeholder="Ej: Rayzen, Dropshipping, Personal")
        icono = c2.selectbox("Ícono", paneles.ICONOS)
        tipo = st.radio("¿Qué vas a llevar en este panel?", list(paneles.TIPOS), format_func=paneles.TIPOS.get)
        if st.form_submit_button("Crear panel", type="primary"):
            try:
                paneles.crear_nube(con_central, usuario["id"], nombre, tipo, icono)
            except ValueError as e:
                st.error(str(e))
            else:
                st.rerun()
    st.stop()

ids = [p["id"] for p in lista]
etiquetas = {p["id"]: f"{p['icono']} {p['nombre']}" for p in lista}

barra, boton = st.columns([6, 1])
if demo_on:
    panel = paneles.PANEL_DEMO
    barra.markdown("**🧪 Demo**")
else:
    if st.session_state.get("panel") not in ids:
        recordado = st.session_state.get("_panel_ok")
        st.session_state["panel"] = recordado if recordado in ids else ids[0]
    elegido = barra.radio("Panel", ids, key="panel", format_func=etiquetas.get, horizontal=True,
                          label_visibility="collapsed")
    panel = next((p for p in lista if p["id"] == elegido), lista[0])
    st.session_state["_panel_ok"] = panel["id"]
st.session_state["panel_actual"] = panel

# --- Negocio y Personal tienen menús con una cantidad distinta de páginas. Si se pasa de uno a
# otro con un simple rerun, el navegador a veces no logra reconciliar el menú viejo con el nuevo
# y lanza "NotFoundError: removeChild". Se evita forzando una recarga limpia justo en ese cambio;
# tu selección de panel ya quedó guardada, así que la recarga abre directo en el panel correcto.
tipo_actual = panel["tipo"]
if st.session_state.get("_tipo_prev") not in (None, tipo_actual):
    st.session_state["_tipo_prev"] = tipo_actual
    st.components.v1.html("<script>window.parent.location.href = window.parent.location.pathname;</script>", height=0)
    st.stop()
st.session_state["_tipo_prev"] = tipo_actual

# --- al cambiar de panel se descarta lo que era del anterior (filtros, cargas a medias, editores)
if st.session_state.get("_panel_prev") != panel["id"]:
    for k in list(st.session_state):
        if k in ("resultados_carga", "marca", "desde", "hasta", "_ultima_semana", "modo_semanas", "semanas_custom") or \
                k.startswith(("dl_", "res_", "upn_", "up_", "uploader_", "ed_", "hist_", "nota_", "mov_")):
            del st.session_state[k]
    st.session_state["_panel_prev"] = panel["id"]

# ============================================================ conexión al panel elegido
ruta_local_nube = None
if demo_on or not MODO_NUBE:
    con = paneles.conectar(panel)
else:
    # el contenido del panel viaja como un archivo temporal de esta sesión (se trae de la nube
    # una sola vez, y se vuelve a subir al final de esta corrida — ver el final del archivo).
    if "_dir_temp" not in st.session_state:
        st.session_state["_dir_temp"] = tempfile.mkdtemp(prefix="finanzas_")
    ruta_local_nube = Path(st.session_state["_dir_temp"]) / f"{panel['id']}.db"
    paneles.asegurar_local(con_central, panel, ruta_local_nube)
    from core import db as _db
    con = _db.conectar(path=ruta_local_nube, marcas=panel.get("marcas"))

personal = panel["tipo"] == "personal"

if personal:
    ctx = SimpleNamespace(con=con, demo=False, panel=panel)
    paginas = [
        st.Page("views/personal_resumen.py", title="Resumen", icon="📊", default=True, url_path="resumen"),
        st.Page("views/personal_movimientos.py", title="Ingresos y gastos", icon="💸", url_path="movimientos"),
        st.Page("views/personal_historial.py", title="Historial (semanas y meses)", icon="🗂️", url_path="historial"),
        st.Page("views/paneles.py", title="Paneles", icon="⚙️", url_path="paneles"),
    ]
else:
    if demo_on:
        demo.crear_si_falta(con)
        with st.sidebar:
            if st.button("🔄 Regenerar datos demo"):
                from core import db
                db.reiniciar(con)
                demo.poblar(con)
                st.rerun()
    todo = data.cargar_pedidos(con)
    disp = contexto.semanas_disponibles(con, todo)

    with st.sidebar:
        st.markdown("#### Filtros")
        marca = CONSOLIDADO
        if len(catalogo.marcas(con)) > 1:
            opciones = [CONSOLIDADO] + contexto.marcas_visibles(con, todo)
            if st.session_state.get("marca") not in opciones:
                st.session_state["marca"] = CONSOLIDADO
            marca = st.selectbox("Marca / tienda", opciones, key="marca")

        desde = hasta = None
        semanas_elegidas = None
        if len(disp) >= 2:
            modo_sem = st.radio("Semanas a analizar", ["Rango continuo", "Elegir semanas"], key="modo_semanas",
                                horizontal=True, help="«Elegir semanas» arma un comparativo a tu gusto: picas "
                                "las semanas que quieras, no tienen que ser seguidas. Útil para comparar antes/después "
                                "de un cambio de precio del proveedor, por ejemplo.")
            if modo_sem == "Elegir semanas":
                if not st.session_state.get("semanas_custom"):
                    st.session_state["semanas_custom"] = disp[-4:]
                st.session_state["semanas_custom"] = [s for s in st.session_state["semanas_custom"] if s in disp] \
                    or disp[-1:]
                semanas_elegidas = st.multiselect("Semanas", disp, key="semanas_custom", format_func=etiqueta_corta)
                if not semanas_elegidas:
                    st.caption("Elige al menos una semana.")
            else:
                continuas = semanas_entre(disp[0], disp[-1])
                ultima_antes = st.session_state.get("_ultima_semana")
                # si "Hasta" estaba en la última semana, que siga a la última cuando lleguen datos nuevos
                if st.session_state.get("hasta") not in continuas or st.session_state.get("hasta") == ultima_antes:
                    st.session_state["hasta"] = continuas[-1]
                if st.session_state.get("desde") not in continuas:
                    st.session_state["desde"] = continuas[0]
                st.session_state["_ultima_semana"] = continuas[-1]
                desde = st.selectbox("Semana desde", continuas, key="desde", format_func=etiqueta_corta)
                hasta = st.selectbox("Semana hasta", continuas, key="hasta", format_func=etiqueta_corta)
        elif disp:
            desde = hasta = disp[0]
            st.caption(f"Semana con datos: {etiqueta_corta(disp[0])}")
        else:
            st.caption("Sin datos todavía.")

    ctx = contexto.construir(con, demo_on, marca, desde, hasta, todo=todo, panel_nombre=panel["nombre"],
                             semanas_elegidas=semanas_elegidas)
    hay_datos = len(todo) > 0
    paginas = [
        st.Page("views/cargar.py", title="Cargar archivos", icon="📤", default=not hay_datos, url_path="cargar"),
        st.Page("views/tablero.py", title="Tablero", icon="📊", default=hay_datos, url_path="tablero"),
        st.Page("views/gastos.py", title="Gastos", icon="💸", url_path="gastos"),
        st.Page("views/pareto.py", title="Pareto y rentabilidad", icon="🎯", url_path="pareto"),
        st.Page("views/tendencias.py", title="Semanas y tendencias", icon="📈", url_path="tendencias"),
        st.Page("views/historial.py", title="Historial (semanas y meses)", icon="🗂️", url_path="historial"),
        st.Page("views/llamadas.py", title="Lista de llamadas", icon="📞", url_path="llamadas"),
        st.Page("views/catalogo.py", title="Catálogo y marcas", icon="🏷️", url_path="catalogo"),
        st.Page("views/paneles.py", title="Paneles", icon="⚙️", url_path="paneles"),
    ]

st.session_state["ctx"] = ctx
st.session_state["modo_nube"] = MODO_NUBE
st.session_state["con_central"] = con_central
st.session_state["usuario_actual"] = usuario
navegacion = st.navigation(paginas)
boton.page_link("views/paneles.py", label="➕ Panel")

if demo_on:
    st.warning("🧪 **MODO DEMO** — todo lo que ves son datos ficticios. Desactívalo en el menú de la izquierda "
               "para volver a tus paneles.")
if (aviso := st.session_state.pop("aviso_panel", None)):
    st.success(aviso)
navegacion.run()

# se sube de vuelta a la nube al final de CADA corrida (cubre cualquier guardado que haya
# pasado en esta misma ejecución, y también lo que quede justo antes de un st.rerun())
if ruta_local_nube is not None and ruta_local_nube.exists():
    try:
        cloud_db.subir_panel(con_central, panel["id"], ruta_local_nube)
    except Exception as e:
        st.error(f"⚠️ No se pudo guardar en la nube: {e}. Tus cambios quedaron en esta sesión; "
                 "recarga y vuelve a intentar antes de cerrar la pestaña.")
