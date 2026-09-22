"""Puente con Turso (base de datos en la nube) para el modo público con cuentas.

En modo local (sin secrets de Turso en .streamlit/secrets.toml) nada de este módulo se
usa: la app funciona exactamente igual que hasta ahora, con archivos SQLite locales.

Cómo funciona el modo nube:
- Hay UNA base "central" en Turso con los usuarios, las invitaciones y el registro de
  qué paneles tiene cada quién (`paneles_registro`), más el contenido de cada panel
  guardado como un archivo (`panel_archivos`).
- Cada panel se sigue manejando como un archivo SQLite normal (exactamente el mismo
  `core/db.py` de siempre): al abrirlo se descarga desde la nube a un archivo temporal
  de esta sesión, y al guardar (cada `commit()`) se vuelve a subir. Así ninguna de las
  reglas de negocio (ingest.py, gastos.py, etc.) tuvo que cambiar.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

CENTRAL_ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, es_admin INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1, creado_en TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS invitaciones (
    codigo TEXT PRIMARY KEY, creado_por TEXT, creado_en TEXT NOT NULL,
    usado_por_id INTEGER REFERENCES usuarios(id), usado_en TEXT);

CREATE TABLE IF NOT EXISTS paneles_registro (
    id TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    nombre TEXT NOT NULL, tipo TEXT NOT NULL, icono TEXT NOT NULL,
    marcas_json TEXT, creado_en TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS panel_archivos (
    panel_id TEXT PRIMARY KEY REFERENCES paneles_registro(id),
    contenido BLOB NOT NULL, actualizado_en TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS intentos_login (
    email TEXT PRIMARY KEY, intentos INTEGER NOT NULL DEFAULT 0, bloqueado_hasta TEXT);
"""


def dividir_sql(script: str) -> list:
    """Parte un script de varias sentencias separadas por ';', quitando antes las líneas
    de comentario. Nuestros esquemas no usan ';' dentro de strings ni triggers, así que
    un split simple es seguro aquí."""
    sin_comentarios = "\n".join(l for l in script.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in sin_comentarios.split(";") if s.strip()]


class _FilaNube:
    """Envuelve una Row de libsql_client para que se comporte como sqlite3.Row: acepta
    fila["columna"], fila[0] Y dict(fila). La Row real de libsql_client no tiene .keys(),
    así que dict(fila) revienta si no se envuelve (a diferencia de sqlite3.Row, que sí
    lo soporta — por eso este puente hace falta)."""

    __slots__ = ("_fila",)

    def __init__(self, fila):
        self._fila = fila

    def __getitem__(self, key):
        return self._fila[key]

    def keys(self):
        return self._fila._fields

    def __iter__(self):
        return iter(self._fila.astuple())  # como sqlite3.Row: iterar da los VALORES, no las llaves

    def __len__(self):
        return len(self._fila)

    def __repr__(self):
        return repr(dict(self))


class _CursorNube:
    """Le da a un ResultSet de libsql_client la forma de un cursor sqlite3: fetchone,
    fetchall, lastrowid — para que el resto del código no note la diferencia."""

    def __init__(self, resultado):
        self._r = resultado

    def fetchone(self):
        return _FilaNube(self._r.rows[0]) if self._r.rows else None

    def fetchall(self):
        return [_FilaNube(f) for f in self._r.rows]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self._r.last_insert_rowid

    @property
    def rowcount(self):
        return self._r.rows_affected


class ConexionNube:
    """Envuelve libsql_client.ClientSync para que se use igual que sqlite3.Connection:
    con.execute(sql, params) -> cursor, con.commit(), con.executescript(sql)."""

    def __init__(self, cliente):
        self._c = cliente

    def execute(self, sql, params=()):
        return _CursorNube(self._c.execute(sql, list(params) if params else []))

    def executemany(self, sql, seq_params):
        ultimo = None
        for params in seq_params:
            ultimo = self._c.execute(sql, list(params))
        return _CursorNube(ultimo) if ultimo is not None else None

    def executescript(self, script):
        for sentencia in dividir_sql(script):
            self._c.execute(sentencia)

    def commit(self):
        pass  # cada .execute() en Turso ya queda guardado; no hay transacción que cerrar

    def close(self):
        self._c.close()


def _url_http(url: str) -> str:
    """Turso da la URL como 'libsql://...', que por defecto conecta por WebSocket — en
    despliegues como Streamlit Cloud esa conexión falla (handshake rechazado). Se usa
    'https://...' en su lugar (mismo servidor, protocolo HTTP normal, más confiable aquí).
    Así el usuario puede pegar la URL tal como se la da Turso, sin tener que pensarlo."""
    url = (url or "").strip()
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


def _cliente(url: str, token: str):
    import libsql_client  # import perezoso: que no truene en modo local si el paquete faltara
    return libsql_client.create_client_sync(url=_url_http(url), auth_token=token)


def conectar_central(url: str, token: str) -> ConexionNube:
    con = ConexionNube(_cliente(url, token))
    con.executescript(CENTRAL_ESQUEMA)
    return con


def descargar_panel(con_central, panel_id: str, destino: Path) -> bool:
    """Trae el archivo del panel desde la nube a `destino`. True si había datos guardados
    (False = panel nuevo, `destino` queda tal como estaba para que se cree desde cero)."""
    fila = con_central.execute("SELECT contenido FROM panel_archivos WHERE panel_id=?", (panel_id,)).fetchone()
    if fila is None:
        return False
    destino.write_bytes(fila["contenido"])
    return True


def subir_panel(con_central, panel_id: str, origen: Path) -> None:
    contenido = origen.read_bytes()
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    con_central.execute(
        "INSERT OR REPLACE INTO panel_archivos(panel_id, contenido, actualizado_en) VALUES (?,?,?)",
        (panel_id, contenido, ahora))
