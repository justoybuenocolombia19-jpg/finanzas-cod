"""Prueba de humo: cada pantalla se ejecuta sin excepciones (modo demo y datos reales)."""
import glob
import os
import sys

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, RAIZ)
PAGINAS = ["cargar", "tablero", "gastos", "pareto", "tendencias", "historial", "llamadas", "catalogo"]
REALES = sorted(glob.glob(os.path.expanduser("~/Downloads/ordenes_2026*.xlsx")))


@pytest.fixture()
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANZAS_DATA_DIR", str(tmp_path))
    for m in [m for m in sys.modules if m.startswith("core")]:
        del sys.modules[m]
    return tmp_path


def _app():
    return AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=60)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_paginas_modo_demo(datos, pagina):
    at = _app()
    at.session_state["demo"] = True
    at.run()
    assert not at.exception, at.exception
    at.switch_page(f"views/{pagina}.py").run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_paginas_base_vacia(datos, pagina):
    at = _app().run()
    at.switch_page(f"views/{pagina}.py").run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("marca", ["Rayzen", "Dropshipping"])
def test_filtro_marca_demo(datos, marca):
    at = _app()
    at.session_state["demo"] = True
    at.run()
    at.session_state["marca"] = marca
    for p in ("tablero", "pareto", "tendencias", "gastos"):
        at.switch_page(f"views/{p}.py").run()
        assert not at.exception, (p, [e.value for e in at.exception])


@pytest.mark.skipif(len(REALES) < 4, reason="reportes reales no disponibles")
def test_paginas_con_reportes_reales(datos):
    from core import db, ingest
    con = db.conectar()
    for f in REALES:
        ingest.guardar(con, ingest.preparar_archivo(os.path.basename(f), open(f, "rb").read()))
    con.close()
    at = _app().run()
    for p in PAGINAS:
        at.switch_page(f"views/{p}.py").run()
        assert not at.exception, (p, [e.value for e in at.exception])


def test_historial_por_mes_y_notas(datos):
    at = _app()
    at.session_state["demo"] = True
    at.run()
    at.switch_page("views/historial.py").run()
    assert not at.exception, [e.value for e in at.exception]
    at.radio[0].set_value("Mes").run()
    assert not at.exception, [e.value for e in at.exception]
    # guardar una nota y verla
    at.text_area[0].set_value("Subimos presupuesto de TikTok").run()
    [b for b in at.button if "Guardar nota" in b.label][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Subimos presupuesto de TikTok" in m.value for m in at.markdown)


def test_panel_personal_y_cambio_de_panel(datos):
    from core import paneles, personal
    p = paneles.crear("Personal", "personal", "👤")
    con = paneles.conectar(p)
    personal.agregar(con, "2026-09-02", "ingreso", "Ventas", 3_000_000)
    personal.agregar(con, "2026-09-03", "gasto", "Vivienda", 900_000)
    con.close()
    at = _app()
    at.session_state["panel"] = p["id"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    for pagina in ("personal_resumen", "personal_movimientos", "personal_historial", "paneles"):
        at.switch_page(f"views/{pagina}.py").run()
        assert not at.exception, (pagina, [e.value for e in at.exception])


def test_paneles_de_negocio_nuevos_todas_las_paginas(datos):
    from core import paneles
    n = paneles.crear("Rayzen", "negocio")
    at = _app()
    at.session_state["panel"] = n["id"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    for pagina in PAGINAS + ["paneles"]:
        at.switch_page(f"views/{pagina}.py").run()
        assert not at.exception, (pagina, [e.value for e in at.exception])


def test_cambiar_entre_negocio_y_personal_en_la_misma_sesion(datos):
    """Regresión: cambiar de un panel de negocio a uno personal (o viceversa) sin recargar la
    página no debe reventar el script ni dejar el navegador en un estado roto."""
    from core import paneles
    negocio = paneles.crear("Rayzen", "negocio")
    personal = paneles.crear("Personal", "personal")

    at = _app()
    at.session_state["panel"] = negocio["id"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["_tipo_prev"] == "negocio"

    # cambio de tipo dentro de la MISMA sesión (como si el usuario hiciera clic en el menú de paneles)
    at.session_state["panel"] = personal["id"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]  # se corta con st.stop(), no con una excepción
    assert at.session_state["_tipo_prev"] == "personal"

    # la "recarga" (una nueva corrida ya con el tipo actualizado) sí debe mostrar el panel personal
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Personal" in h.value for h in at.title)


def test_elegir_semanas_sueltas_en_la_app(datos):
    at = _app()
    at.session_state["demo"] = True
    at.run()
    disp_key = [w.key for w in at.sidebar.radio if w.key == "modo_semanas"]
    assert disp_key, "no apareció el selector de modo de semanas"
    at.sidebar.radio(key="modo_semanas").set_value("Elegir semanas").run()
    assert not at.exception, [e.value for e in at.exception]
    precargadas = at.session_state["semanas_custom"]                     # valores crudos ('2026-W38', ...)
    sueltas = [precargadas[0], precargadas[-1]] if len(precargadas) > 2 else precargadas
    at.sidebar.multiselect(key="semanas_custom").set_value(sueltas).run()
    assert not at.exception, [e.value for e in at.exception]
    for p in ("tablero", "pareto", "tendencias", "gastos"):
        at.switch_page(f"views/{p}.py").run()
        assert not at.exception, (p, [e.value for e in at.exception])


def test_pareto_precio_y_costo(datos):
    at = _app()
    at.session_state["demo"] = True
    at.run()
    at.switch_page("views/pareto.py").run()
    assert not at.exception, [e.value for e in at.exception]
    sel = at.selectbox(key="prod_evolucion")
    sel.set_value("Masajeador Cervical").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("cambiaron" in m.value.lower() or "cambió" in m.value.lower() for t in (at.markdown, at.caption) for m in t)
