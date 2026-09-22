import datetime as dt

import pandas as pd
import streamlit as st

from core import data, db, ingest, paneles, ui
from core.fmt import dmy, num
from core.semanas import etiqueta, semana_de, semanas_entre

ctx = st.session_state["ctx"]
con = ctx.con

st.title("📤 Cargar reportes")
st.caption("Arrastra **todos** los Excel de estado de pedidos de la semana (entregados, devoluciones, en oficina, "
           "en tránsito, novedades…). La app detecta el estado de cada pedido por la columna ESTATUS, "
           "evita duplicados por ID y deja cada pedido en su estado más reciente.")

# --- resultados de la última carga (se guardan en sesión porque el cargador se reinicia)
if resultados := st.session_state.pop("resultados_carga", None):
    st.success(f"✅ Se procesaron {len(resultados)} archivo(s).")
    for r in resultados:
        with st.container(border=True):
            st.markdown(f"**{r['archivo']}** · {num(r['filas'])} filas · semana asignada: "
                        f"{etiqueta(r['semana']) if r['semana'] else '—'}")
            a, b, c, d, e = st.columns(5)
            a.metric("Pedidos nuevos", num(r["nuevas"]))
            b.metric("Cambiaron de estado", num(r["actualizadas"]))
            c.metric("Sin cambios", num(r["sin_cambio"]))
            d.metric("Ya tenía más reciente", num(r["desactualizadas"]))
            e.metric("Repetidos en el archivo", num(r["repetidas_en_archivo"] + r["ignoradas"]))
            if r["transiciones"]:
                st.info("Pedidos que avanzaron de estado: " + " · ".join(
                    f"{t} ×{n}" for t, n in r["transiciones"].most_common()))
            if r["productos_nuevos"]:
                st.warning(f"Se detectaron {r['productos_nuevos']} precio(s) de venta nuevos. Ponles nombre y marca en "
                           "**Catálogo y marcas** para que la app separe Rayzen de dropshipping.")
    st.page_link("views/tablero.py", label="Ver el tablero", icon="📊")

# --- selección de archivos
n_up = st.session_state.get("up_n", 0)
archivos = st.file_uploader("Archivos .xlsx", type=["xlsx"], accept_multiple_files=True, key=f"uploader_{n_up}")

if archivos:
    hoy = dt.date.today()
    todas = semanas_entre(semana_de(hoy - dt.timedelta(weeks=40)), semana_de(hoy))
    manual = st.radio("¿A qué semana pertenece esta carga?",
                      ["Detectar automáticamente (por la fecha del reporte)", "Elegir la semana yo mismo"],
                      horizontal=True, help="Un reporte exportado un lunes refleja la semana que acaba de cerrar, "
                                            "así que se asigna a la semana anterior.") == "Elegir la semana yo mismo"
    forzada = None
    if manual:
        forzada = st.selectbox("Semana", todas, index=len(todas) - 2, format_func=etiqueta)

    custom = ingest.mapa_estados(con)
    preps = [ingest.preparar_archivo(a.name, a.getvalue(), custom, forzada) for a in archivos]
    conocidos = {r["hash"] for r in con.execute("SELECT hash FROM cargas")}

    filas = []
    for p in preps:
        if p["error"]:
            st.error(f"**{p['nombre']}**: {p['error']}")
            continue
        resumen = " · ".join(f"{e} ×{n}" for (_, e), n in p["estados"].most_common())
        aviso = "; ".join(p["advertencias"])
        if p["hash"] in conocidos:
            aviso = ("Este archivo ya se había cargado antes (no se duplica nada). " + aviso).strip()
        filas.append({"Archivo": p["nombre"], "Filas": p["filas"], "Estados detectados": resumen,
                      "Fecha de reporte": dmy(p["fecha_reporte"]),
                      "Semana": etiqueta(p["semana"]) if p["semana"] else "—", "Avisos": aviso})
    if filas:
        st.dataframe(pd.DataFrame(filas), hide_index=True)

    # estatus que la app no reconoce: el usuario los asigna una vez y quedan aprendidos
    desconocidos = sorted({s for p in preps if not p["error"] for (s, e) in p["estados"] if e == "OTRO"})
    asignaciones = {}
    if desconocidos:
        st.warning("Hay estatus que no reconozco. Dime a qué estado equivalen (se recuerda para próximas cargas):")
        for s in desconocidos:
            asignaciones[s] = st.selectbox(f"«{s or '(vacío)'}» equivale a…", ["(dejar como OTRO)"] + ingest.ESTADOS[:-1],
                                           key=f"map_{s}")

    validos = [p for p in preps if not p["error"] and p["df"] is not None]
    if validos and st.button(f"✅ Procesar {len(validos)} archivo(s)", type="primary"):
        if any(v != "(dejar como OTRO)" for v in asignaciones.values()):
            for s, v in asignaciones.items():
                if v != "(dejar como OTRO)":
                    ingest.asignar_estado(con, s, v)
            custom = ingest.mapa_estados(con)
            preps = [ingest.preparar_archivo(a.name, a.getvalue(), custom, forzada) for a in archivos]
            validos = [p for p in preps if not p["error"] and p["df"] is not None]
        validos.sort(key=lambda p: p["fecha_reporte"] or "")
        with st.spinner("Procesando…"):
            st.session_state["resultados_carga"] = [ingest.guardar(con, p) for p in validos]
        st.session_state["up_n"] = n_up + 1
        st.rerun()

st.divider()

# --- estado de la base
resumen = data.resumen_base(con)
a, b, c = st.columns(3)
a.metric("Pedidos en la base", num(resumen["pedidos"]))
b.metric("Archivos cargados", num(resumen["cargas"]))
c.metric("Semanas con datos", f"{etiqueta(resumen['desde'])[:6]} → {etiqueta(resumen['hasta'])[:6]}" if resumen["desde"] else "—")

hist = pd.read_sql_query(
    "SELECT archivo, fecha_carga, semana, filas, nuevas, actualizadas, sin_cambio FROM cargas ORDER BY id DESC LIMIT 50", con)
if len(hist):
    st.subheader("Historial de cargas")
    hist["fecha_carga"] = pd.to_datetime(hist["fecha_carga"]).dt.strftime("%d-%m-%Y %H:%M")
    hist["semana"] = hist["semana"].map(lambda s: etiqueta(s) if s else "—")
    st.dataframe(hist.rename(columns={"archivo": "Archivo", "fecha_carga": "Cargado", "semana": "Semana", "filas": "Filas",
                                      "nuevas": "Nuevos", "actualizadas": "Con cambio de estado",
                                      "sin_cambio": "Sin cambios"}), hide_index=True)

with st.expander("⚙️ Ajustes de la base de datos"):
    actual = db.get_config(con, "modo_semana", "estado")
    llaves = list(data.MODOS_SEMANA)
    nuevo = st.radio("¿En qué semana cuenta cada pedido para el dinero?", llaves, index=llaves.index(actual),
                     format_func=lambda k: data.MODOS_SEMANA[k])
    if nuevo != actual:
        db.set_config(con, "modo_semana", nuevo)
        st.rerun()
    if ctx.demo:
        st.caption(f"Archivo de la base: `{db.ruta(True)}`")
    elif st.session_state.get("modo_nube"):
        st.caption("Este panel vive en la nube (se guarda automáticamente).")
    else:
        st.caption(f"Archivo de la base: `{paneles.ruta_db(st.session_state['panel_actual'])}`")
    st.markdown("**Copia de seguridad** de toda tu información (pedidos, gastos, catálogo, notas).")
    ui.descarga("copia de seguridad", lambda: ui.copia_seguridad(con),
                f"respaldo_finanzas_{dt.date.today():%Y-%m-%d}.db", "application/octet-stream",
                (ctx.demo, resumen["pedidos"], len(hist)), "respaldo")
    st.markdown("**Borrar todo** (pedidos, gastos, catálogo). No se puede deshacer.")
    if st.text_input("Escribe BORRAR para confirmar", key="confirma_borrar") == "BORRAR" and st.button("🗑️ Borrar la base"):
        db.reiniciar(con)
        st.session_state["confirma_borrar"] = ""
        st.rerun()
