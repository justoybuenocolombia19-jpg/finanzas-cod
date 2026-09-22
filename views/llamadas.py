import streamlit as st

from core import export, llamadas, ui
from core.fmt import cop, num

ctx = st.session_state["ctx"]
con = ctx.con
st.title(f"📞 Lista de llamadas · {ctx.titulo}")
st.caption("Pedidos **en oficina** o **en novedad**: es plata en riesgo que hay que gestionar hoy. "
           "Ordenados por urgencia (días sin resolver y valor). Aquí no aplica el filtro de semanas.")
if ui.sin_datos(ctx):
    st.stop()

ll = llamadas.lista(con, ctx.df_marca)
if ll.empty:
    st.success("🎉 No hay pedidos en oficina ni en novedad.")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Pedidos en riesgo", num(len(ll)))
b.metric("Dinero en riesgo", cop(ll["valor_venta"].sum()))
c.metric("Urgentes (7+ días)", num((ll["prioridad"] == "Urgente").sum()))
d.metric("Por llamar", num((~ll["llamado"]).sum()))

f1, f2, f3, f4 = st.columns(4)
solo = f1.toggle("Solo pendientes", value=True)
prio = f2.multiselect("Prioridad", ["Urgente", "Alta", "Normal"], default=["Urgente", "Alta", "Normal"])
vend = f3.multiselect("Responsable", sorted(ll["vendedor"].unique()))
transp = f4.multiselect("Transportadora", sorted(ll["transportadora"].unique()))

v = ll[ll["prioridad"].isin(prio)]
if solo:
    v = v[~v["llamado"]]
if vend:
    v = v[v["vendedor"].isin(vend)]
if transp:
    v = v[v["transportadora"].isin(transp)]
v = v.reset_index(drop=True)
v.insert(3, "valor", v["valor_venta"].map(cop))

MARCA = {"Urgente": "🔴 Urgente", "Alta": "🟠 Alta", "Normal": "🟡 Normal"}
v_show = v.assign(prioridad=v["prioridad"].map(MARCA))
ed = st.data_editor(
    v_show, hide_index=True, key="ed_llamadas",
    column_order=["prioridad", "dias", "valor", "cliente", "telefono", "whatsapp", "ciudad", "transportadora", "estado",
                  "causa", "vendedor", "llamado", "resultado", "nota"],
    disabled=["prioridad", "dias", "valor", "cliente", "telefono", "whatsapp", "ciudad", "transportadora", "estado",
              "causa", "vendedor"],
    column_config={
        "prioridad": "Prioridad", "dias": st.column_config.NumberColumn("Días", format="%d"), "valor": "Valor",
        "cliente": "Cliente", "telefono": "Teléfono", "ciudad": "Ciudad", "transportadora": "Transportadora",
        "estado": "Estado", "causa": "Novedad / último mov.", "vendedor": "Responsable",
        "whatsapp": st.column_config.LinkColumn("WhatsApp", display_text="💬 Abrir"),
        "llamado": st.column_config.CheckboxColumn("Llamado"),
        "resultado": st.column_config.SelectboxColumn("Resultado", options=llamadas.RESULTADOS),
        "nota": st.column_config.TextColumn("Nota"),
    })

cambios = []
for i in range(len(v)):
    o, n = v.loc[i], ed.loc[i]
    if bool(o["llamado"]) != bool(n["llamado"]) or (o["resultado"] or "") != (n["resultado"] or "") \
            or (o["nota"] or "") != (n["nota"] or ""):
        cambios.append({"id": o["id"], "llamado": bool(n["llamado"]), "resultado": n["resultado"], "nota": n["nota"]})

if st.button(f"💾 Guardar gestión ({len(cambios)} cambio(s))", type="primary", disabled=not cambios):
    llamadas.guardar_gestion(con, cambios)
    st.success("Gestión guardada.")
    st.rerun()

st.divider()
ui.descarga("lista de llamadas (Excel)", lambda: export.excel_llamadas(ll), "lista_llamadas.xlsx", ui.XLSX,
            (ctx.demo, ctx.marca, len(ll), int(ll["llamado"].sum())), "llamadas")
