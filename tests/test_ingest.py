import glob
import io
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import db, ingest  # noqa: E402

REALES = sorted(glob.glob(os.path.expanduser("~/Downloads/ordenes_2026*.xlsx")))


def _xlsx(filas, cols=None):
    buf = io.BytesIO()
    pd.DataFrame(filas).to_excel(buf, index=False)
    return buf.getvalue()


def _fila(id_, estatus, rep="21-09-2026", venta=89900, **kw):
    f = {"ID": id_, "ESTATUS": estatus, "FECHA": "10-09-2026", "FECHA DE REPORTE": rep,
         "VALOR DE COMPRA EN PRODUCTOS": venta, "TOTAL EN PRECIOS DE PROVEEDOR": 30000,
         "GANANCIA": 40000 if estatus == "ENTREGADO" else None, "PRECIO FLETE": 20000,
         "COSTO DEVOLUCION FLETE": 18000 if estatus == "DEVOLUCION" else 0, "COLUMNA EXTRA": "x"}
    f.update(kw)
    return f


@pytest.fixture()
def con(tmp_path):
    return db.conectar(path=tmp_path / "t.db")


def test_clasificar_estados():
    c = ingest.clasificar
    assert c("ENTREGADO") == "ENTREGADO" and c("DEVOLUCIÓN") == "DEVUELTO"
    assert c("RECLAME EN OFICINA") == "EN_OFICINA" and c("EN TRANSITO") == "EN_TRANSITO"
    assert c("en novedad") == "NOVEDAD" and c("algo raro") == "OTRO"
    assert c("algo raro", {"ALGO RARO": "NOVEDAD"}) == "NOVEDAD"


def test_numeros_como_texto_y_columnas_extra(con):
    x = _xlsx([_fila(1, "ENTREGADO", venta="$ 89.900", **{"TELÉFONO": 3001234567})])
    prep = ingest.preparar_archivo("ordenes_20260921_090000.xlsx", x)
    assert prep["error"] is None
    assert prep["df"].iloc[0]["valor_venta"] == 89900
    assert prep["df"].iloc[0]["telefono"] == "3001234567"


def test_archivo_invalido(con):
    assert ingest.preparar_archivo("x.xlsx", b"no es excel")["error"]
    assert ingest.preparar_archivo("x.xlsx", _xlsx([{"A": 1}]))["error"]


def test_semana_del_reporte_lunes_es_semana_anterior():
    prep = ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO", rep="21-09-2026")]))
    assert prep["semana"] == "2026-W38"  # lunes 21-sep refleja la semana 14-20 sep


def test_dedupe_y_actualizacion_de_estado(con):
    r1 = ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx(
        [_fila(1, "RECLAME EN OFICINA", rep="14-09-2026"), _fila(2, "RECLAME EN OFICINA", rep="14-09-2026")])))
    assert r1["nuevas"] == 2
    r2 = ingest.guardar(con, ingest.preparar_archivo("b.xlsx", _xlsx(
        [_fila(1, "ENTREGADO", rep="21-09-2026"), _fila(3, "DEVOLUCION", rep="21-09-2026")])))
    assert (r2["nuevas"], r2["actualizadas"]) == (1, 1)
    assert r2["transiciones"]["EN_OFICINA → ENTREGADO"] == 1
    assert con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 3
    # mismo archivo otra vez: nada cambia
    r3 = ingest.guardar(con, ingest.preparar_archivo("b.xlsx", _xlsx(
        [_fila(1, "ENTREGADO", rep="21-09-2026"), _fila(3, "DEVOLUCION", rep="21-09-2026")])))
    assert (r3["nuevas"], r3["actualizadas"], r3["sin_cambio"]) == (0, 0, 2)
    # reporte viejo no pisa el estado nuevo
    r4 = ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "RECLAME EN OFICINA", rep="14-09-2026")])))
    assert r4["desactualizadas"] == 1
    assert con.execute("SELECT estado FROM pedidos WHERE id='1'").fetchone()[0] == "ENTREGADO"


def test_semana_se_conserva_si_el_estado_no_cambia(con):
    ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO", rep="21-09-2026")])))
    ingest.guardar(con, ingest.preparar_archivo("b.xlsx", _xlsx([_fila(1, "ENTREGADO", rep="28-09-2026")])))
    assert con.execute("SELECT semana_estado FROM pedidos").fetchone()[0] == "2026-W38"


def test_duplicados_dentro_del_mismo_archivo(con):
    r = ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx(
        [_fila(1, "RECLAME EN OFICINA"), _fila(1, "ENTREGADO")])))
    assert r["repetidas_en_archivo"] == 1
    assert con.execute("SELECT estado FROM pedidos").fetchone()[0] == "ENTREGADO"


def test_catalogo_se_autocompleta_por_precio(con):
    ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx(
        [_fila(1, "ENTREGADO", venta=89900), _fila(2, "ENTREGADO", venta=155000)])))
    assert con.execute("SELECT COUNT(*) FROM producto_precios").fetchone()[0] == 2


@pytest.mark.skipif(len(REALES) < 4, reason="reportes reales no disponibles")
def test_reportes_reales_dropi(con):
    total = 0
    for f in REALES:
        prep = ingest.preparar_archivo(os.path.basename(f), open(f, "rb").read())
        assert prep["error"] is None and not prep["estados"].get(("", "OTRO"))
        total += ingest.guardar(con, prep)["nuevas"]
    n, = con.execute("SELECT COUNT(*) FROM pedidos").fetchone()
    assert n == 226 and total <= 242
    est = dict(con.execute("SELECT estado, COUNT(*) FROM pedidos GROUP BY estado").fetchall())
    assert est.get("OTRO", 0) == 0
    bruta, = con.execute("SELECT SUM(ganancia) FROM pedidos WHERE estado='ENTREGADO'").fetchone()
    assert round(bruta) == 13508718


def test_meses_y_semanas():
    from core import semanas as sm
    assert sm.mes_de("2026-W38") == "2026-09"      # jueves 17-sep
    assert sm.mes_de("2026-W40") == "2026-10"      # lunes 28-sep, jueves 1-oct
    assert sm.etiqueta_mes("2026-09") == "Septiembre 2026"


def test_notas_y_respaldo(con):
    from core import notas, ui
    notas.agregar(con, "2026-W38", "  campaña nueva  ")
    notas.agregar(con, "2026-W38", "   ")  # vacía: se ignora
    assert [n["texto"] for n in notas.listar(con, "2026-W38")] == ["campaña nueva"]
    assert notas.conteo(con) == {"2026-W38": 1}
    ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO")])))
    copia = ui.copia_seguridad(con)
    assert copia[:15] == b"SQLite format 3"
    notas.borrar(con, notas.listar(con, "2026-W38")[0]["id"])
    assert notas.listar(con, "2026-W38") == []


def test_periodos_semana_y_mes(con):
    from core import contexto, historial
    ingest.guardar(con, ingest.preparar_archivo("a.xlsx", _xlsx([_fila(1, "ENTREGADO", rep="21-09-2026")])))
    ingest.guardar(con, ingest.preparar_archivo("b.xlsx", _xlsx([_fila(2, "DEVOLUCION", rep="05-10-2026")])))
    ctx = contexto.construir(con)
    sem = historial.periodos(ctx, "semana")
    assert list(sem["periodo"]) == ["2026-W40", "2026-W39", "2026-W38"]   # la más reciente primero
    assert sem.loc[sem["periodo"] == "2026-W39", "aviso"].iloc[0] == "⚠️ sin pedidos"  # semana sin reportes
    mes = historial.periodos(ctx, "mes")
    assert list(mes["periodo"]) == ["2026-10", "2026-09"]
    assert mes.loc[mes["periodo"] == "2026-09", "entregados"].iloc[0] == 1


def test_texto_y_slug_rango():
    from core import semanas as sm
    assert sm.es_continua(["2026-W38", "2026-W39", "2026-W40"])
    assert sm.es_continua(["2026-W40", "2026-W38", "2026-W39"])          # el orden no importa
    assert not sm.es_continua(["2026-W38", "2026-W40"])                  # falta la W39
    assert sm.es_continua(["2026-W38"]) and sm.es_continua([])
    assert "→" in sm.texto_rango(["2026-W38", "2026-W39"])
    assert sm.texto_rango(["2026-W38"]) == sm.etiqueta("2026-W38")       # una sola: sin flecha
    suelto = sm.texto_rango(["2026-W20", "2026-W35", "2026-W40"])
    assert suelto.startswith("3 semanas elegidas:") and "→" not in suelto
    assert sm.slug_rango(["2026-W38", "2026-W39"]) == "2026-W38_2026-W39"
    assert sm.slug_rango(["2026-W20", "2026-W35"]) == "2semanas_2026-W35"
    assert sm.slug_rango([]) == "sin_semanas"


def test_contexto_con_semanas_sueltas(con):
    from core import contexto
    for i, rep in enumerate(["21-09-2026", "28-09-2026", "05-10-2026", "12-10-2026"]):
        ingest.guardar(con, ingest.preparar_archivo(f"a{i}.xlsx", _xlsx([_fila(i, "ENTREGADO", rep=rep)])))
    disp = contexto.semanas_disponibles(con, __import__("core.data", fromlist=["cargar_pedidos"]).cargar_pedidos(con))
    sueltas = [disp[0], disp[2]]                                         # se saltan una semana a propósito
    ctx = contexto.construir(con, semanas_elegidas=sueltas)
    assert ctx.semanas == sorted(sueltas) and len(ctx.df) == 2           # solo esas 2 semanas, no la de en medio
    ctx_ignorada = contexto.construir(con, semanas_elegidas=["2099-W01"])  # semana que no existe: se ignora
    assert ctx_ignorada.semanas == []


def test_evolucion_producto_detecta_cambio_de_costo():
    from core import contexto, pareto
    import tempfile
    from pathlib import Path
    c = db.conectar(path=Path(tempfile.mkdtemp()) / "e.db")
    for rep, costo in [("07-09-2026", 30000), ("14-09-2026", 30000), ("21-09-2026", 36000)]:
        ingest.guardar(c, ingest.preparar_archivo(f"a{rep}.xlsx", _xlsx(
            [_fila(1000 + hash(rep) % 100, "ENTREGADO", rep=rep, **{"TOTAL EN PRECIOS DE PROVEEDOR": costo})])))
    ctx = contexto.construir(c)
    g = pareto.evolucion_producto(ctx.df, ctx.df["producto"].iloc[0])
    assert len(g) == 3
    assert g["cambio_costo"].tolist() == [False, False, True]
    assert not g["cambio_precio"].any()
