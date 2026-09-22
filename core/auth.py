"""Autenticación del modo nube: registro por código de invitación, contraseñas con
hash bcrypt (nunca en texto plano) y un bloqueo simple contra fuerza bruta.

Todas las funciones reciben una conexión (`con`) ya abierta a la base central — funcionan
igual con una conexión sqlite3 normal (así se prueban, sin depender de la nube) que con
`cloud_db.ConexionNube` (lo que se usa de verdad en producción).
"""
from __future__ import annotations

import datetime as dt
import re
import secrets as _secrets

import bcrypt

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_INTENTOS = 6
BLOQUEO_MINUTOS = 15
MENSAJE_LOGIN_INVALIDO = "Correo o contraseña incorrectos."  # nunca decir cuál de los dos falló


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw((password or "").encode("utf-8"), hash_.encode("utf-8"))
    except ValueError:
        return False


def validar_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip())) and len(email) <= 254


def generar_codigo_invitacion() -> str:
    return "-".join(_secrets.token_hex(2) for _ in range(3))  # ej: a1b2-c3d4-e5f6


# ---------------------------------------------------------------- usuarios

def obtener_usuario_por_email(con, email: str) -> dict | None:
    r = con.execute("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(r) if r else None


def obtener_usuario(con, usuario_id: int) -> dict | None:
    r = con.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return dict(r) if r else None


def registrar(con, email: str, password: str, password2: str, codigo_invitacion: str) -> tuple[bool, str]:
    """-> (ok, mensaje). El primer usuario que se registra en la base queda admin
    automáticamente (no hay nadie más que le pueda dar un código); los siguientes
    necesitan un código de invitación válido y sin usar."""
    email = (email or "").strip().lower()
    if not validar_email(email):
        return False, "Ese correo no parece válido."
    if len(password or "") < MIN_PASSWORD:
        return False, f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres."
    if password != password2:
        return False, "Las contraseñas no coinciden."
    if obtener_usuario_por_email(con, email):
        return False, "Ya existe una cuenta con ese correo."

    es_primero = con.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"] == 0
    codigo = (codigo_invitacion or "").strip()
    if not es_primero:
        fila = con.execute("SELECT usado_por_id FROM invitaciones WHERE codigo = ?", (codigo,)).fetchone()
        if fila is None or fila["usado_por_id"] is not None:
            return False, "Ese código de invitación no es válido o ya se usó."

    ahora = dt.datetime.now().isoformat(timespec="seconds")
    cur = con.execute("INSERT INTO usuarios(email, password_hash, es_admin, creado_en) VALUES (?,?,?,?)",
                       (email, hash_password(password), 1 if es_primero else 0, ahora))
    con.commit()
    nuevo_id = cur.lastrowid
    if not es_primero:
        con.execute("UPDATE invitaciones SET usado_por_id=?, usado_en=? WHERE codigo=?", (nuevo_id, ahora, codigo))
        con.commit()
    return True, "admin" if es_primero else "ok"


def _bloqueado_hasta(con, email: str) -> str | None:
    r = con.execute("SELECT bloqueado_hasta FROM intentos_login WHERE email=?", (email,)).fetchone()
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    return r["bloqueado_hasta"] if r and r["bloqueado_hasta"] and r["bloqueado_hasta"] > ahora else None


def _registrar_intento(con, email: str, exito: bool) -> None:
    if exito:
        con.execute("DELETE FROM intentos_login WHERE email=?", (email,))
        con.commit()
        return
    r = con.execute("SELECT intentos FROM intentos_login WHERE email=?", (email,)).fetchone()
    intentos = (r["intentos"] if r else 0) + 1
    bloqueado_hasta = None
    if intentos >= MAX_INTENTOS:
        bloqueado_hasta = (dt.datetime.now() + dt.timedelta(minutes=BLOQUEO_MINUTOS)).isoformat(timespec="seconds")
    con.execute("INSERT OR REPLACE INTO intentos_login(email, intentos, bloqueado_hasta) VALUES (?,?,?)",
                (email, intentos, bloqueado_hasta))
    con.commit()


def iniciar_sesion(con, email: str, password: str) -> tuple[bool, str, dict | None]:
    email = (email or "").strip().lower()
    if not email:
        return False, MENSAJE_LOGIN_INVALIDO, None
    if (hasta := _bloqueado_hasta(con, email)):
        return False, f"Demasiados intentos fallidos. Vuelve a intentar después de las {hasta[11:16]}.", None
    usuario = obtener_usuario_por_email(con, email)
    if not usuario or not usuario["activo"] or not verificar_password(password, usuario["password_hash"]):
        _registrar_intento(con, email, False)
        return False, MENSAJE_LOGIN_INVALIDO, None
    _registrar_intento(con, email, True)
    return True, "", usuario


def cambiar_password(con, usuario_id: int, password_actual: str, password_nuevo: str, password_nuevo2: str) -> tuple[bool, str]:
    usuario = obtener_usuario(con, usuario_id)
    if not usuario or not verificar_password(password_actual, usuario["password_hash"]):
        return False, "La contraseña actual no es correcta."
    if len(password_nuevo or "") < MIN_PASSWORD:
        return False, f"La contraseña nueva debe tener al menos {MIN_PASSWORD} caracteres."
    if password_nuevo != password_nuevo2:
        return False, "Las contraseñas nuevas no coinciden."
    con.execute("UPDATE usuarios SET password_hash=? WHERE id=?", (hash_password(password_nuevo), usuario_id))
    con.commit()
    return True, "Contraseña actualizada."


# ---------------------------------------------------------------- invitaciones (solo admin)

def crear_invitacion(con, creado_por_email: str) -> str:
    codigo = generar_codigo_invitacion()
    con.execute("INSERT INTO invitaciones(codigo, creado_por, creado_en) VALUES (?,?,?)",
                (codigo, creado_por_email, dt.datetime.now().isoformat(timespec="seconds")))
    con.commit()
    return codigo


def listar_invitaciones(con) -> list:
    filas = con.execute(
        """SELECT i.codigo, i.creado_por, i.creado_en, u.email AS usado_por, i.usado_en
           FROM invitaciones i LEFT JOIN usuarios u ON u.id = i.usado_por_id
           ORDER BY i.creado_en DESC""").fetchall()
    return [dict(f) for f in filas]


def revocar_invitacion(con, codigo: str) -> None:
    con.execute("DELETE FROM invitaciones WHERE codigo=? AND usado_por_id IS NULL", (codigo,))
    con.commit()


def listar_usuarios(con) -> list:
    return [dict(f) for f in con.execute(
        "SELECT id, email, es_admin, activo, creado_en FROM usuarios ORDER BY creado_en").fetchall()]
