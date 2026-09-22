"""Ayudas de interfaz Streamlit compartidas por las pantallas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .fmt import cop, dmy, num, pct, veces


def tabla(df: pd.DataFrame, cop_=(), pct_=(), num_=(), x_=(), fecha_=(), renombrar=None, alto=None):
    """Muestra un DataFrame con formato colombiano ($1.234.567, 12,3 %, dd-mm-aaaa)."""
    d = df.copy()
    for cols, f in ((cop_, cop), (pct_, pct), (num_, num), (x_, veces), (fecha_, dmy)):
        for c in cols:
            if c in d:
                d[c] = d[c].map(f)
    if renombrar:
        d = d.rename(columns=renombrar)
    st.dataframe(d, hide_index=True, **({"height": alto} if alto else {}))


def sin_datos(ctx) -> bool:
    """Si la base está vacía muestra la guía de primer uso y devuelve True."""
    if len(ctx.df_todo):
        return False
    st.info("Aún no hay pedidos cargados. Ve a **Cargar archivos** y arrastra tus reportes de Dropi, "
            "o activa el **modo demo** en el menú de la izquierda para explorar con datos de ejemplo.")
    st.page_link("views/cargar.py", label="Ir a Cargar archivos", icon="📤")
    return True


def firma(ctx) -> tuple:
    return (ctx.demo, ctx.marca, ctx.semanas[:1], ctx.semanas[-1:], len(ctx.df), round(float(ctx.gastos["monto"].sum())))


def descarga(etiqueta: str, generar, nombre: str, mime: str, sig, key: str):
    """Genera el archivo solo cuando se pide (evita recalcular Excel/PDF en cada interacción)."""
    if st.button(f"⚙️ Preparar {etiqueta}", key=f"gen_{key}"):
        with st.spinner("Generando…"):
            st.session_state[f"dl_{key}"] = (sig, generar())
    v = st.session_state.get(f"dl_{key}")
    if v and v[0] == sig:
        st.download_button(f"⬇️ Descargar {etiqueta}", v[1], file_name=nombre, mime=mime, key=f"dl_btn_{key}")


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def subir_a_semana(con, semana: str, key: str) -> None:
    """Cargador de archivos que asigna TODO lo nuevo a una semana concreta (para completar un período)."""
    from . import db, ingest
    from .fmt import num
    from .semanas import etiqueta

    if (res := st.session_state.pop(f"res_{key}", None)) is not None:
        for r in res:
            st.success(f"**{r['archivo']}**: {num(r['nuevas'])} pedidos nuevos · {num(r['actualizadas'])} cambiaron de estado · "
                       f"{num(r['sin_cambio'])} sin cambios · {num(r['desactualizadas'])} ya tenía más reciente.")
    if db.get_config(con, "modo_semana", "estado") != "estado":
        st.info("Ojo: en Ajustes tienes otro criterio de semana (fecha del pedido o último movimiento); "
                "en ese caso la semana la define el propio pedido y no la que elijas aquí.")
    n = st.session_state.get(f"upn_{key}", 0)
    archivos = st.file_uploader(f"Agregar archivos a {etiqueta(semana)}", type=["xlsx"], accept_multiple_files=True,
                                key=f"up_{key}_{n}")
    st.caption("Los pedidos nuevos, o que cambien de estado, cuentan en esta semana. Los que ya estaban en el mismo "
               "estado conservan su semana. Nada se duplica.")
    if not archivos:
        return
    custom = ingest.mapa_estados(con)
    preps = [ingest.preparar_archivo(a.name, a.getvalue(), custom, semana) for a in archivos]
    for p in preps:
        if p["error"]:
            st.error(f"**{p['nombre']}**: {p['error']}")
    validos = [p for p in preps if not p["error"] and p["df"] is not None]
    if validos and st.button(f"✅ Agregar {len(validos)} archivo(s) a esta semana", type="primary", key=f"go_{key}"):
        st.session_state[f"res_{key}"] = [ingest.guardar(con, p) for p in sorted(validos, key=lambda p: p["fecha_reporte"] or "")]
        st.session_state[f"upn_{key}"] = n + 1
        st.rerun()


def copia_seguridad(con) -> bytes:
    """Copia completa de la base de datos (un archivo .db) para respaldo."""
    import os
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "copia.db")
        destino = sqlite3.connect(ruta)
        con.backup(destino)
        destino.close()
        with open(ruta, "rb") as f:
            return f.read()


def notas_periodo(con, clave: str, extra=()) -> None:
    """Bitácora de un período (semana '2026-W38' o mes '2026-09'); `extra` = claves cuyas notas también se listan."""
    from . import historial, notas
    from .fmt import dmy

    txt = st.text_area("Nueva nota", key=f"nota_{clave}", height=90,
                       placeholder="Ej: Subimos el presupuesto de TikTok el miércoles; Envía tuvo retrasos en Costa.")
    if st.button("💾 Guardar nota", type="primary", disabled=not txt.strip(), key=f"gn_{clave}"):
        notas.agregar(con, clave, txt)
        st.session_state.pop(f"nota_{clave}", None)
        st.rerun()
    lista = notas.listar(con, [clave] + list(extra))
    for n in lista:
        with st.container(border=True):
            st.markdown(n["texto"])
            a, b = st.columns([5, 1])
            a.caption(f"{dmy(n['creado_en'][:10])} {n['creado_en'][11:16]} · {historial.etiqueta_periodo(n['periodo'])}")
            if b.button("🗑️", key=f"del_{n['id']}", help="Borrar nota"):
                notas.borrar(con, n["id"])
                st.rerun()
    if not lista:
        st.caption("Aún no hay notas en este período.")


def pantalla_login(con_central) -> None:
    """Pantalla de acceso del modo nube: iniciar sesión o crear cuenta con código de
    invitación. Al terminar deja st.session_state['usuario'] con el usuario que entró."""
    from . import auth

    st.title("📦 Finanzas COD")
    st.caption("Cada quien ve solo sus propios paneles. Los datos de nadie se mezclan con los de otro.")
    t_login, t_registro = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with t_login:
        with st.form("form_login"):
            email = st.text_input("Correo", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            if st.form_submit_button("Entrar", type="primary"):
                ok, msg, usuario = auth.iniciar_sesion(con_central, email, password)
                if ok:
                    st.session_state["usuario"] = usuario
                    st.rerun()
                else:
                    st.error(msg)

    with t_registro:
        st.caption("Necesitas un código de invitación de quien administra la cuenta. "
                   "(Si eres la primera persona en registrarte, no hace falta código: quedas como administrador.)")
        with st.form("form_registro"):
            email = st.text_input("Correo", key="reg_email")
            codigo = st.text_input("Código de invitación", key="reg_codigo", placeholder="a1b2-c3d4-e5f6")
            p1 = st.text_input("Contraseña", type="password", key="reg_p1",
                               help=f"Mínimo {auth.MIN_PASSWORD} caracteres.")
            p2 = st.text_input("Repite la contraseña", type="password", key="reg_p2")
            if st.form_submit_button("Crear cuenta", type="primary"):
                ok, msg = auth.registrar(con_central, email, p1, p2, codigo)
                if not ok:
                    st.error(msg)
                elif msg == "admin":
                    st.success("✅ Cuenta creada como **administrador**. Ve a la pestaña «Iniciar sesión».")
                else:
                    st.success("✅ Cuenta creada. Ve a la pestaña «Iniciar sesión».")
