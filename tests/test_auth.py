"""Pruebas de core/auth.py y core/cloud_db.py contra una base central SQLite local
(misma forma que cloud_db.ConexionNube — no depende de Turso ni de internet)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import auth, cloud_db  # noqa: E402


@pytest.fixture()
def central(tmp_path):
    import sqlite3
    con = sqlite3.connect(tmp_path / "central.db")
    con.row_factory = sqlite3.Row
    con.executescript(cloud_db.CENTRAL_ESQUEMA)
    return con


# ---------------------------------------------------------------- primitivas

def test_hash_nunca_es_el_password_en_claro():
    h = auth.hash_password("miClaveSegura123")
    assert h != "miClaveSegura123" and h.startswith("$2b$")
    assert auth.verificar_password("miClaveSegura123", h)
    assert not auth.verificar_password("otraClave", h)


def test_verificar_password_no_truena_con_hash_invalido():
    assert not auth.verificar_password("cualquiera", "esto-no-es-un-hash-bcrypt")


def test_validar_email():
    assert auth.validar_email("gente@negocio.com")
    assert not auth.validar_email("no-es-correo")
    assert not auth.validar_email("")
    assert not auth.validar_email("a" * 260 + "@x.com")


def test_codigos_de_invitacion_son_distintos():
    codigos = {auth.generar_codigo_invitacion() for _ in range(50)}
    assert len(codigos) == 50


def test_dividir_sql():
    partes = cloud_db.dividir_sql("CREATE TABLE a (x INT);\n-- comentario\nCREATE TABLE b (y INT);  ")
    assert partes == ["CREATE TABLE a (x INT)", "CREATE TABLE b (y INT)"]


# ---------------------------------------------------------------- registro

def test_primer_usuario_no_necesita_codigo_y_queda_admin(central):
    ok, msg = auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    assert ok and msg == "admin"
    u = auth.obtener_usuario_por_email(central, "dueno@negocio.com")
    assert u["es_admin"] == 1


def test_segundo_usuario_necesita_codigo_valido(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    ok, msg = auth.registrar(central, "empleado@negocio.com", "otraClave1", "otraClave1", "codigo-inventado")
    assert not ok and "invitación" in msg

    codigo = auth.crear_invitacion(central, "dueno@negocio.com")
    ok, msg = auth.registrar(central, "empleado@negocio.com", "otraClave1", "otraClave1", codigo)
    assert ok and msg == "ok"
    assert auth.obtener_usuario_por_email(central, "empleado@negocio.com")["es_admin"] == 0

    # el código ya se usó: no sirve una segunda vez
    ok, msg = auth.registrar(central, "otro@negocio.com", "claveSegura2", "claveSegura2", codigo)
    assert not ok and "invitación" in msg


def test_registro_rechaza_datos_invalidos(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    codigo = auth.crear_invitacion(central, "dueno@negocio.com")
    assert not auth.registrar(central, "no-es-correo", "claveSegura1", "claveSegura1", codigo)[0]
    assert not auth.registrar(central, "x@x.com", "corta", "corta", codigo)[0]
    assert not auth.registrar(central, "x@x.com", "claveSegura1", "otraClave1", codigo)[0]
    assert not auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", codigo)[0]  # ya existe


def test_invitacion_revocada_no_sirve(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    codigo = auth.crear_invitacion(central, "dueno@negocio.com")
    auth.revocar_invitacion(central, codigo)
    ok, _ = auth.registrar(central, "empleado@negocio.com", "otraClave1", "otraClave1", codigo)
    assert not ok


# ---------------------------------------------------------------- login

def test_login_correcto_e_incorrecto(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    ok, msg, usuario = auth.iniciar_sesion(central, "DUENO@negocio.com", "claveSegura1")  # correo insensible a mayúsculas
    assert ok and usuario["email"] == "dueno@negocio.com"

    ok, msg, usuario = auth.iniciar_sesion(central, "dueno@negocio.com", "claveMala")
    assert not ok and usuario is None and msg == auth.MENSAJE_LOGIN_INVALIDO

    ok, msg, _ = auth.iniciar_sesion(central, "nadie@negocio.com", "loquesea")
    assert not ok and msg == auth.MENSAJE_LOGIN_INVALIDO  # mismo mensaje: no delata si el correo existe


def test_bloqueo_por_intentos_fallidos(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    for _ in range(auth.MAX_INTENTOS):
        auth.iniciar_sesion(central, "dueno@negocio.com", "mala")
    ok, msg, _ = auth.iniciar_sesion(central, "dueno@negocio.com", "claveSegura1")  # ya bloqueado, aunque la clave sea buena
    assert not ok and "Demasiados intentos" in msg
    # un login correcto (antes del bloqueo) limpia el contador
    auth.registrar(central, "otro@negocio.com", "claveSegura1", "claveSegura1", auth.crear_invitacion(central, "x"))
    auth.iniciar_sesion(central, "otro@negocio.com", "mala")
    auth.iniciar_sesion(central, "otro@negocio.com", "mala")
    ok, _, _ = auth.iniciar_sesion(central, "otro@negocio.com", "claveSegura1")
    assert ok


def test_cambiar_password(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    uid = auth.obtener_usuario_por_email(central, "dueno@negocio.com")["id"]
    ok, msg = auth.cambiar_password(central, uid, "claveMala", "nuevaClave1", "nuevaClave1")
    assert not ok
    ok, msg = auth.cambiar_password(central, uid, "claveSegura1", "nuevaClave1", "nuevaClave1")
    assert ok
    assert auth.iniciar_sesion(central, "dueno@negocio.com", "nuevaClave1")[0]
    assert not auth.iniciar_sesion(central, "dueno@negocio.com", "claveSegura1")[0]


def test_listar_usuarios_e_invitaciones(central):
    auth.registrar(central, "dueno@negocio.com", "claveSegura1", "claveSegura1", "")
    c1, c2 = auth.crear_invitacion(central, "dueno@negocio.com"), auth.crear_invitacion(central, "dueno@negocio.com")
    auth.registrar(central, "empleado@negocio.com", "otraClave1", "otraClave1", c1)
    inv = {i["codigo"]: i for i in auth.listar_invitaciones(central)}
    assert inv[c1]["usado_por"] == "empleado@negocio.com" and inv[c2]["usado_por"] is None
    assert len(auth.listar_usuarios(central)) == 2
