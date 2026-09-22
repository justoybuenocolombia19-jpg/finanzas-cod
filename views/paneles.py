import pandas as pd
import streamlit as st

from core import paneles, ui

ctx = st.session_state["ctx"]
actual = st.session_state["panel_actual"]
modo_nube = st.session_state.get("modo_nube", False)
con_central = st.session_state.get("con_central")
usuario = st.session_state.get("usuario_actual")

st.title("⚙️ Paneles")
st.caption("Un panel es un espacio **totalmente independiente**: sus propios pedidos, gastos, catálogo y notas. "
           "Úsalos para separar Rayzen, Dropshipping o tus finanzas personales. Cámbialos con los botones de arriba.")

lista = paneles.listar_nube(con_central, usuario["id"]) if modo_nube else paneles.listar()

# ------------------------------------------------------------------ crear
st.subheader("➕ Crear un panel nuevo")
with st.form("nuevo_panel", clear_on_submit=True):
    c1, c2 = st.columns([3, 1])
    nombre = c1.text_input("Nombre", placeholder="Ej: Rayzen, Dropshipping, Personal")
    icono = c2.selectbox("Ícono", paneles.ICONOS)
    tipo = st.radio("¿Qué vas a llevar en este panel?", list(paneles.TIPOS), format_func=paneles.TIPOS.get)
    if st.form_submit_button("Crear panel", type="primary"):
        try:
            if modo_nube:
                nuevo = paneles.crear_nube(con_central, usuario["id"], nombre, tipo, icono)
            else:
                nuevo = paneles.crear(nombre, tipo, icono)
        except ValueError as e:
            st.error(str(e))
        else:
            st.session_state["_panel_solicitado"] = nuevo["id"]
            st.rerun()

# ------------------------------------------------------------------ lista
st.subheader("Tus paneles")
for p in lista:
    with st.container(border=True):
        a, b, c = st.columns([4, 3, 1])
        a.markdown(f"**{p['icono']} {p['nombre']}**" + ("  ·  _(estás aquí)_" if p["id"] == actual["id"] else ""))
        if modo_nube:
            b.caption(paneles.TIPOS[p["tipo"]].split(" (")[0])
        else:
            b.caption(f"{paneles.TIPOS[p['tipo']].split(' (')[0]} · {paneles.estadisticas(p)}")
        if p["id"] != actual["id"] and c.button("Abrir", key=f"abrir_{p['id']}"):
            st.session_state["_panel_solicitado"] = p["id"]
            st.rerun()

# ------------------------------------------------------------------ el panel actual
if actual["id"] == "demo":
    st.info("Estás en el modo demo. Desactívalo en el menú de la izquierda para administrar tus paneles.")
    st.stop()

st.subheader(f"Panel actual: {actual['icono']} {actual['nombre']}")
with st.expander("✏️ Cambiar nombre o ícono"):
    n = st.text_input("Nombre", value=actual["nombre"], key="ren_nombre")
    i = st.selectbox("Ícono", paneles.ICONOS, index=paneles.ICONOS.index(actual["icono"]) if actual["icono"] in paneles.ICONOS else 0,
                     key="ren_icono")
    if st.button("Guardar cambios"):
        try:
            if modo_nube:
                paneles.editar_nube(con_central, usuario["id"], actual["id"], n, i)
            else:
                paneles.editar(actual["id"], n, i)
        except ValueError as e:
            st.error(str(e))
        else:
            st.rerun()

with st.expander("💾 Copia de seguridad de este panel"):
    st.caption("Descarga toda la información de este panel en un archivo .db.")
    ui.descarga("copia de seguridad", lambda: ui.copia_seguridad(ctx.con),
                f"respaldo_{actual['id']}.db", "application/octet-stream",
                (actual["id"], modo_nube), "respaldo_panel")

with st.expander("🗑️ Eliminar este panel"):
    if len(lista) <= 1:
        st.info("Debe quedar al menos un panel.")
    elif st.text_input(f"Escribe el nombre del panel ({actual['nombre']}) para confirmar", key="conf_eliminar") == actual["nombre"] \
            and st.button("Eliminar panel"):
        if modo_nube:
            paneles.eliminar_nube(con_central, usuario["id"], actual["id"])
            aviso = "Panel eliminado."
        else:
            destino = paneles.eliminar(actual["id"])
            aviso = f"Panel eliminado. Su base quedó en {destino}"
        st.session_state["_panel_solicitado"] = next(
            p["id"] for p in (paneles.listar_nube(con_central, usuario["id"]) if modo_nube else paneles.listar()))
        st.session_state["aviso_panel"] = aviso
        st.rerun()
    elif modo_nube:
        st.warning("El panel y sus datos se eliminan de la nube. No se puede deshacer.")
    else:
        st.warning("El panel desaparece del menú. Su base de datos no se borra: se mueve a la carpeta "
                   "`data/papelera/` por si necesitas recuperarla.")

# ------------------------------------------------------------------ cuenta e invitaciones (solo modo nube)
if modo_nube:
    from core import auth

    st.divider()
    st.subheader("👤 Tu cuenta")
    st.caption(f"Conectado como **{usuario['email']}**" + (" · administrador" if usuario.get("es_admin") else ""))
    with st.expander("🔑 Cambiar contraseña"):
        with st.form("form_cambiar_password"):
            actual_pw = st.text_input("Contraseña actual", type="password")
            n1 = st.text_input("Contraseña nueva", type="password", help=f"Mínimo {auth.MIN_PASSWORD} caracteres.")
            n2 = st.text_input("Repite la contraseña nueva", type="password")
            if st.form_submit_button("Actualizar", type="primary"):
                ok, msg = auth.cambiar_password(con_central, usuario["id"], actual_pw, n1, n2)
                (st.success if ok else st.error)(msg)

    if usuario.get("es_admin"):
        st.subheader("✉️ Invitaciones")
        st.caption("Solo quien tenga un código puede crear una cuenta. Genera uno por cada persona que quieras invitar.")
        if st.button("➕ Generar código de invitación"):
            codigo = auth.crear_invitacion(con_central, usuario["email"])
            st.success(f"Código nuevo: `{codigo}` — cópialo y compártelo con la persona que quieres invitar.")
        invitaciones = auth.listar_invitaciones(con_central)
        if invitaciones:
            ui.tabla(
                pd.DataFrame(invitaciones),
                fecha_=["creado_en", "usado_en"],
                renombrar={"codigo": "Código", "creado_por": "Creado por", "creado_en": "Creado",
                          "usado_por": "Usado por", "usado_en": "Usado"})
            sin_usar = [i["codigo"] for i in invitaciones if not i["usado_por"]]
            if sin_usar:
                revocar = st.selectbox("Revocar un código sin usar", [""] + sin_usar)
                if revocar and st.button("Revocar"):
                    auth.revocar_invitacion(con_central, revocar)
                    st.rerun()

        st.subheader("👥 Usuarios registrados")
        ui.tabla(pd.DataFrame(auth.listar_usuarios(con_central)), fecha_=["creado_en"],
                 renombrar={"id": "ID", "email": "Correo", "es_admin": "Admin", "activo": "Activo", "creado_en": "Creado"})
