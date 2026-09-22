import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_ingest import _fila, _xlsx  # noqa: E402


@pytest.fixture()
def P(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANZAS_DATA_DIR", str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("core")]:
        del sys.modules[m]
    from core import paneles
    return paneles


def test_panel_inicial_usa_la_base_existente(P):
    lista = P.listar()
    assert len(lista) == 1 and lista[0]["archivo"] == "finanzas.db" and lista[0]["tipo"] == "negocio"
    assert lista[0]["marcas"] == ["Rayzen", "Dropshipping"]


def test_crear_editar_y_eliminar(P):
    a = P.crear("Rayzen", "negocio", "🌱")
    b = P.crear("Personal", "personal", "👤")
    assert P.crear("Dropshipping", "negocio")["id"] == "dropshipping"
    assert a["marcas"] == ["Rayzen"] and b["marcas"] == []
    with pytest.raises(ValueError):
        P.crear("rayzen")                       # nombre repetido (sin importar mayúsculas)
    with pytest.raises(ValueError):
        P.crear("  ")
    P.editar("personal", "Mis finanzas", "💰")
    assert P.obtener("personal")["nombre"] == "Mis finanzas"
    destino = P.eliminar("rayzen")
    assert destino.exists() and destino.parent.name == "papelera"   # se conserva, no se borra
    assert "rayzen" not in [p["id"] for p in P.listar()]


def test_no_se_puede_eliminar_el_ultimo(P):
    with pytest.raises(ValueError):
        P.eliminar("principal")


def test_paneles_son_independientes(P):
    from core import data, ingest
    a, b = P.crear("Rayzen"), P.crear("Dropshipping")
    ca, cb = P.conectar(a), P.conectar(b)
    ingest.guardar(ca, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO"), _fila(2, "ENTREGADO")])))
    assert len(data.cargar_pedidos(ca)) == 2
    assert len(data.cargar_pedidos(cb)) == 0                 # el otro panel no ve esos pedidos
    ingest.guardar(cb, ingest.preparar_archivo("b.xlsx", _xlsx([_fila(1, "DEVOLUCION")])))  # mismo ID, otro panel
    assert data.cargar_pedidos(ca)["estado"].tolist() == ["ENTREGADO", "ENTREGADO"]
    assert data.cargar_pedidos(cb)["estado"].tolist() == ["DEVUELTO"]


def test_panel_de_una_marca_asigna_todo_a_esa_marca(P):
    from core import data, ingest
    ca = P.conectar(P.crear("Rayzen"))
    ingest.guardar(ca, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO")])))
    assert data.cargar_pedidos(ca)["marca"].tolist() == ["Rayzen"]


def test_marcas_no_reaparecen_al_renombrar(P):
    from core import catalogo
    con = P.conectar(P.listar()[0])
    m = catalogo.listar_marcas(con)
    m[0]["nombre"] = "Rayzen Pro"
    assert catalogo.guardar_marcas(con, m) == ""
    con.close()
    assert "Rayzen" not in catalogo.marcas(P.conectar(P.listar()[0]))
    assert catalogo.agregar_marca(P.conectar(P.listar()[0]), "rayzen pro")  # duplicado → mensaje de error


def test_personal_ingresos_gastos_y_periodos(P):
    from core import personal
    con = P.conectar(P.crear("Personal", "personal"))
    personal.agregar(con, "2026-09-02", "ingreso", "Ventas", 3_000_000)
    personal.agregar(con, "2026-09-03", "gasto", "Vivienda", 900_000)
    personal.agregar(con, "2026-09-20", "gasto", "Alimentación", 400_000, "mercado")
    personal.agregar(con, "2026-10-01", "gasto", "Transporte", 100_000)
    with pytest.raises(ValueError):
        personal.agregar(con, "2026-09-03", "gasto", "Vivienda", 0)
    df = personal.cargar(con)
    t = personal.totales(df[df["mes"] == "2026-09"])
    assert (t["ingresos"], t["gastos"], t["balance"]) == (3_000_000, 1_300_000, 1_700_000)
    assert round(t["ahorro"], 3) == 0.567
    meses = personal.periodos(con, df, "mes")
    assert list(meses["periodo"]) == ["2026-10", "2026-09"]
    assert len(personal.periodos(con, df, "semana")) == 3   # 2 y 3 de sep caen en la misma semana
    # editar un mes: quitar una fila y corregir otra
    d = df[df["mes"] == "2026-09"][["fecha", "tipo", "categoria", "monto", "nota"]].iloc[:2].copy()
    d.loc[d.index[1], "monto"] = 950_000
    personal.guardar_mes(con, "2026-09", d)
    df2 = personal.cargar(con)
    assert personal.totales(df2[df2["mes"] == "2026-09"])["gastos"] == 950_000
    assert len(df2[df2["mes"] == "2026-10"]) == 1            # otros meses no se tocan


# ---------------------------------------------------------------- modo nube (multiusuario)

@pytest.fixture()
def central_sqlite(tmp_path):
    import sqlite3
    from core import cloud_db
    con = sqlite3.connect(tmp_path / "central.db")
    con.row_factory = sqlite3.Row
    con.executescript(cloud_db.CENTRAL_ESQUEMA)
    return con


def test_crear_y_listar_paneles_nube(central_sqlite, P):
    p1 = P.crear_nube(central_sqlite, 1, "Rayzen")
    p2 = P.crear_nube(central_sqlite, 1, "Dropshipping", icono="📦")
    otro_usuario = P.crear_nube(central_sqlite, 2, "Rayzen")  # mismo nombre, otro dueño: no choca
    assert p1["marcas"] == ["Rayzen"] and p1["id"] != otro_usuario["id"]
    lista1 = P.listar_nube(central_sqlite, 1)
    assert {p["nombre"] for p in lista1} == {"Rayzen", "Dropshipping"}
    assert len(P.listar_nube(central_sqlite, 2)) == 1
    with pytest.raises(ValueError):
        P.crear_nube(central_sqlite, 1, "rayzen")  # nombre repetido para el mismo usuario


def test_editar_y_eliminar_panel_nube(central_sqlite, P):
    p1 = P.crear_nube(central_sqlite, 1, "Rayzen")
    P.crear_nube(central_sqlite, 1, "Personal", tipo="personal")
    P.editar_nube(central_sqlite, 1, p1["id"], "Rayzen Colombia", "🌱")
    assert P.listar_nube(central_sqlite, 1)[0]["nombre"] == "Rayzen Colombia"
    P.editar_nube(central_sqlite, 99, p1["id"], "Robado", "👤")  # otro usuario: el WHERE no matchea nada, no pasa nada
    assert P.listar_nube(central_sqlite, 1)[0]["nombre"] == "Rayzen Colombia"
    P.eliminar_nube(central_sqlite, 1, p1["id"])
    assert len(P.listar_nube(central_sqlite, 1)) == 1
    with pytest.raises(ValueError):
        P.eliminar_nube(central_sqlite, 1, P.listar_nube(central_sqlite, 1)[0]["id"])  # no puede quedar en 0


def test_panel_nube_se_sincroniza_con_la_nube(tmp_path, central_sqlite, P):
    from core import data, db, ingest
    panel = P.crear_nube(central_sqlite, 1, "Rayzen")
    ruta = tmp_path / "sesion1" / f"{panel['id']}.db"
    P.asegurar_local(central_sqlite, panel, ruta)
    assert not ruta.exists()  # panel nuevo: todavía no hay nada en la nube

    con = db.conectar(path=ruta, marcas=panel["marcas"])
    ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO")])))
    con.close()
    from core import cloud_db
    cloud_db.subir_panel(central_sqlite, panel["id"], ruta)  # como haría app.py al final de la corrida

    # "otra sesión" (otro archivo temporal) trae lo mismo que se subió
    ruta2 = tmp_path / "sesion2" / f"{panel['id']}.db"
    P.asegurar_local(central_sqlite, panel, ruta2)
    assert ruta2.exists()
    con2 = db.conectar(path=ruta2, marcas=panel["marcas"])
    assert len(data.cargar_pedidos(con2)) == 1
    con2.close()

    assert "1 pedidos" in P.estadisticas_nube(central_sqlite, panel, tmp_path / "sesion3" / f"{panel['id']}.db")
