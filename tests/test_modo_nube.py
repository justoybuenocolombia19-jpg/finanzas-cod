"""Prueba de extremo a extremo del modo nube (login, registro, paneles por usuario) a
través de la app real, SIN ninguna cuenta de Turso: se reemplaza el cliente de Turso por
uno que en realidad guarda todo en un SQLite local. Así se prueba toda la integración
(app.py, core/auth.py, core/paneles.py, core/cloud_db.py) tal como corre de verdad.
"""
import glob
import os
import sqlite3
import sys

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, RAIZ)


class _ResultadoFalso:
    """Imita libsql_client.ResultSet, respaldado por un cursor sqlite3 real."""

    def __init__(self, cursor, filas):
        self.rows = filas
        self.rows_affected = cursor.rowcount
        self.last_insert_rowid = cursor.lastrowid


class _ClienteFalso:
    """Imita libsql_client.ClientSync ejecutando todo contra un SQLite local de verdad."""

    def __init__(self, ruta):
        # AppTest corre el script en su propio hilo, y puede usar hilos distintos entre
        # una corrida y otra de la misma sesión; el cliente real de Turso habla por HTTP y
        # no tiene esta restricción, así que el doble de prueba tampoco debería tenerla.
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._con.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        cur = self._con.execute(sql, params or [])
        filas = cur.fetchall()
        self._con.commit()
        return _ResultadoFalso(cur, filas)

    def close(self):
        self._con.close()


@pytest.fixture()
def modo_nube(tmp_path, monkeypatch):
    """Activa el modo nube apuntando a un SQLite local disfrazado de Turso, aislado por prueba."""
    monkeypatch.setenv("FINANZAS_DATA_DIR", str(tmp_path / "local"))  # por si algo cae a modo local
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://prueba.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "token-de-prueba")
    ruta_central = tmp_path / "central_falsa.db"
    for m in [m for m in sys.modules if m.startswith("core")]:
        del sys.modules[m]
    import core.cloud_db as cloud_db
    monkeypatch.setattr(cloud_db, "_cliente", lambda url, token: _ClienteFalso(str(ruta_central)))
    return tmp_path


def _app():
    return AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=60)


def test_pantalla_de_login_aparece_sin_sesion(modo_nube):
    at = _app().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Finanzas COD" in t.value for t in at.title)
    assert "usuario" not in at.session_state


def test_registro_primer_usuario_queda_admin_y_puede_entrar(modo_nube):
    at = _app().run()
    at.tabs[1].text_input(key="reg_email").set_value("dueno@negocio.com")
    at.tabs[1].text_input(key="reg_p1").set_value("claveSegura1")
    at.tabs[1].text_input(key="reg_p2").set_value("claveSegura1")
    at.tabs[1].button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("administrador" in s.value.lower() for s in at.success)

    at.tabs[0].text_input(key="login_email").set_value("dueno@negocio.com")
    at.tabs[0].text_input(key="login_password").set_value("claveSegura1")
    at.tabs[0].button[0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["usuario"]["email"] == "dueno@negocio.com"
    assert at.session_state["usuario"]["es_admin"] == 1
    # sin ningún panel todavía: pide crear el primero
    assert any("primer panel" in i.value.lower() for i in at.info)


def _registrar_y_entrar(at, email="dueno@negocio.com", clave="claveSegura1", codigo=""):
    at.tabs[1].text_input(key="reg_email").set_value(email)
    at.tabs[1].text_input(key="reg_codigo").set_value(codigo)
    at.tabs[1].text_input(key="reg_p1").set_value(clave)
    at.tabs[1].text_input(key="reg_p2").set_value(clave)
    at.tabs[1].button[0].click().run()
    at.tabs[0].text_input(key="login_email").set_value(email)
    at.tabs[0].text_input(key="login_password").set_value(clave)
    at.tabs[0].button[0].click().run()
    return at


def test_crear_primer_panel_y_ver_el_tablero(modo_nube):
    at = _registrar_y_entrar(_app().run())
    nombre_input = [w for w in at.text_input if w.label == "Nombre"][0]
    nombre_input.set_value("Rayzen").run()
    assert not at.exception, [e.value for e in at.exception]
    [b for b in at.button if "Crear panel" in b.label][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["panel_actual"]["nombre"] == "Rayzen"
    assert any("Tablero" in t.value or "Cargar" in t.value for t in at.title)


def test_dos_usuarios_no_ven_los_paneles_del_otro(modo_nube):
    at1 = _registrar_y_entrar(_app().run(), "uno@negocio.com")
    [w for w in at1.text_input if w.label == "Nombre"][0].set_value("Panel de Uno").run()
    [b for b in at1.button if "Crear panel" in b.label][0].click().run()
    assert at1.session_state["panel_actual"]["nombre"] == "Panel de Uno"

    from core import auth
    codigo = auth.crear_invitacion(at1.session_state["con_central"], "uno@negocio.com")
    at2 = _registrar_y_entrar(_app().run(), "dos@negocio.com", "otraClave1", codigo)
    # usuario nuevo: todavía no ve "Panel de Uno", le toca crear el suyo
    assert any("primer panel" in i.value.lower() for i in at2.info)
    [w for w in at2.text_input if w.label == "Nombre"][0].set_value("Panel de Dos").run()
    [b for b in at2.button if "Crear panel" in b.label][0].click().run()
    assert at2.session_state["panel_actual"]["nombre"] == "Panel de Dos"

    from core import paneles as _paneles
    con_central = at2.session_state["con_central"]
    vistos_por_dos = {p["nombre"] for p in _paneles.listar_nube(con_central, at2.session_state["usuario"]["id"])}
    assert vistos_por_dos == {"Panel de Dos"}


def test_datos_sobreviven_a_una_sesion_nueva(modo_nube):
    at1 = _registrar_y_entrar(_app().run())
    [w for w in at1.text_input if w.label == "Nombre"][0].set_value("Rayzen").run()
    [b for b in at1.button if "Crear panel" in b.label][0].click().run()
    at1.switch_page("views/catalogo.py").run()
    assert not at1.exception, [e.value for e in at1.exception]

    # "otra sesión": un AppTest nuevo (sin el session_state de la sesión anterior), mismo usuario
    at2 = _app().run()
    at2.tabs[0].text_input(key="login_email").set_value("dueno@negocio.com")
    at2.tabs[0].text_input(key="login_password").set_value("claveSegura1")
    at2.tabs[0].button[0].click().run()
    assert not at2.exception, [e.value for e in at2.exception]
    assert at2.session_state["panel_actual"]["nombre"] == "Rayzen"  # el panel que creó antes sigue ahí
