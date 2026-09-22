"""Paneles: espacios de trabajo independientes (cada uno con su propia base de datos).

Ejemplos: 'Rayzen', 'Dropshipping', 'Personal'. En modo local el registro vive en
data/paneles.json (funciones sin sufijo). En modo nube (varias cuentas, ver core/auth.py
y core/cloud_db.py) el registro vive en la base central y cada panel pertenece a un
usuario (funciones con sufijo `_nube`). La base que ya existía (data/finanzas.db) queda
como primer panel local, sin moverla.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import unicodedata
from pathlib import Path

from . import cloud_db, db

TIPOS = {"negocio": "Negocio con pedidos (reportes de Dropi)",
         "personal": "Finanzas personales (ingresos y gastos)"}
ICONOS = ["🏪", "🌱", "📦", "🛍️", "🚚", "💼", "📈", "🎯", "⭐", "🏠", "👤", "💰"]
PANEL_DEMO = {"id": "demo", "nombre": "Demo", "tipo": "negocio", "icono": "🧪", "archivo": "demo.db", "marcas": None}


def _registro():
    return db.DATA_DIR / "paneles.json"


def _guardar(datos: dict) -> None:
    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _registro().with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_registro())


def listar() -> list:
    """Paneles registrados. La primera vez crea el panel inicial con la base que ya existe."""
    p = _registro()
    if not p.exists():
        _guardar({"paneles": [{"id": "principal", "nombre": "Mi negocio", "tipo": "negocio", "icono": "🏪",
                               "archivo": "finanzas.db", "marcas": list(db.MARCAS_INICIALES)}]})
    return json.loads(p.read_text(encoding="utf-8"))["paneles"]


def obtener(panel_id: str | None) -> dict:
    lista = listar()
    return next((x for x in lista if x["id"] == panel_id), lista[0])


def ruta_db(panel: dict):
    return db.DATA_DIR / panel["archivo"]


def conectar(panel: dict):
    if panel["id"] == "demo":
        return db.conectar(demo=True)
    return db.conectar(path=ruta_db(panel), marcas=panel.get("marcas"))


def _slug(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "panel"


def crear(nombre: str, tipo: str = "negocio", icono: str = "🏪") -> dict:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("Escribe un nombre para el panel.")
    if tipo not in TIPOS:
        raise ValueError("Tipo de panel desconocido.")
    if tipo == "personal" and icono == ICONOS[0]:   # el ícono por defecto del formulario es el de tienda
        icono = "👤"
    lista = listar()
    if any(x["nombre"].lower() == nombre.lower() for x in lista):
        raise ValueError("Ya existe un panel con ese nombre.")
    base, n = _slug(nombre), 1
    ids = {x["id"] for x in lista}
    pid = base
    while pid in ids or (db.DATA_DIR / "paneles" / f"{pid}.db").exists():
        n += 1
        pid = f"{base}-{n}"
    panel = {"id": pid, "nombre": nombre, "tipo": tipo, "icono": icono, "archivo": f"paneles/{pid}.db",
             "marcas": [nombre] if tipo == "negocio" else []}
    conectar(panel).close()  # crea el archivo con su esquema
    _guardar({"paneles": lista + [panel]})
    return panel


def editar(panel_id: str, nombre: str, icono: str) -> None:
    nombre = nombre.strip()
    lista = listar()
    if not nombre:
        raise ValueError("Escribe un nombre para el panel.")
    if any(x["nombre"].lower() == nombre.lower() and x["id"] != panel_id for x in lista):
        raise ValueError("Ya existe un panel con ese nombre.")
    for x in lista:
        if x["id"] == panel_id:
            x["nombre"], x["icono"] = nombre, icono
    _guardar({"paneles": lista})


def eliminar(panel_id: str):
    """Quita el panel del menú y mueve su base a data/papelera/ (se puede recuperar a mano)."""
    lista = listar()
    if len(lista) <= 1:
        raise ValueError("Debe quedar al menos un panel.")
    panel = next((x for x in lista if x["id"] == panel_id), None)
    if panel is None:
        raise ValueError("Ese panel no existe.")
    destino = db.DATA_DIR / "papelera" / f"{panel_id}-{dt.datetime.now():%Y%m%d-%H%M%S}.db"
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen = ruta_db(panel)
    if origen.exists():
        shutil.move(str(origen), str(destino))
    _guardar({"paneles": [x for x in lista if x["id"] != panel_id]})
    return destino


def estadisticas(panel: dict) -> str:
    """Resumen de una línea de lo que contiene el panel."""
    con = conectar(panel)
    try:
        return _estadisticas_de(con, panel["tipo"])
    finally:
        con.close()


def _estadisticas_de(con, tipo: str) -> str:
    if tipo == "personal":
        n = con.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
        return f"{n} movimientos"
    n = con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
    c = con.execute("SELECT COUNT(*) FROM cargas").fetchone()[0]
    return f"{n} pedidos · {c} archivos cargados"


# ---------------------------------------------------------------- modo nube (multiusuario)
#
# El registro de paneles vive en la base central (paneles_registro), con dueño (usuario_id).
# El contenido de cada panel se maneja EXACTAMENTE igual que en modo local (un archivo SQLite
# normal, mismo core/db.py): se descarga a un archivo temporal de la sesión la primera vez que
# se abre, y app.py lo vuelve a subir a la nube al final de cada corrida. Así ninguna regla de
# negocio (ingest.py, gastos.py, etc.) tuvo que cambiar para funcionar en la nube.

def listar_nube(con_central, usuario_id: int) -> list:
    filas = con_central.execute(
        """SELECT id, nombre, tipo, icono, marcas_json FROM paneles_registro
           WHERE usuario_id=? ORDER BY creado_en""", (usuario_id,)).fetchall()
    out = []
    for f in filas:
        d = dict(f)
        d["marcas"] = json.loads(d.pop("marcas_json") or "null")
        out.append(d)
    return out


def obtener_nube(con_central, usuario_id: int, panel_id: str | None) -> dict:
    lista = listar_nube(con_central, usuario_id)
    if not lista:
        raise ValueError("Todavía no tienes ningún panel.")
    return next((x for x in lista if x["id"] == panel_id), lista[0])


def crear_nube(con_central, usuario_id: int, nombre: str, tipo: str = "negocio", icono: str = "🏪") -> dict:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("Escribe un nombre para el panel.")
    if tipo not in TIPOS:
        raise ValueError("Tipo de panel desconocido.")
    if tipo == "personal" and icono == ICONOS[0]:
        icono = "👤"
    if any(x["nombre"].lower() == nombre.lower() for x in listar_nube(con_central, usuario_id)):
        raise ValueError("Ya existe un panel con ese nombre.")
    base, n, pid = _slug(nombre), 1, None
    while True:
        candidato = f"{usuario_id}-{base}" if n == 1 else f"{usuario_id}-{base}-{n}"
        if not con_central.execute("SELECT 1 FROM paneles_registro WHERE id=?", (candidato,)).fetchone():
            pid = candidato
            break
        n += 1
    marcas = [nombre] if tipo == "negocio" else []
    con_central.execute(
        """INSERT INTO paneles_registro(id, usuario_id, nombre, tipo, icono, marcas_json, creado_en)
           VALUES (?,?,?,?,?,?,?)""",
        (pid, usuario_id, nombre, tipo, icono, json.dumps(marcas), dt.datetime.now().isoformat(timespec="seconds")))
    con_central.commit()
    # el archivo real (con su esquema) se crea solo, la primera vez que se abre el panel
    return {"id": pid, "nombre": nombre, "tipo": tipo, "icono": icono, "marcas": marcas}


def editar_nube(con_central, usuario_id: int, panel_id: str, nombre: str, icono: str) -> None:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("Escribe un nombre para el panel.")
    if any(x["nombre"].lower() == nombre.lower() and x["id"] != panel_id for x in listar_nube(con_central, usuario_id)):
        raise ValueError("Ya existe un panel con ese nombre.")
    con_central.execute("UPDATE paneles_registro SET nombre=?, icono=? WHERE id=? AND usuario_id=?",
                        (nombre, icono, panel_id, usuario_id))
    con_central.commit()


def eliminar_nube(con_central, usuario_id: int, panel_id: str) -> None:
    if len(listar_nube(con_central, usuario_id)) <= 1:
        raise ValueError("Debe quedar al menos un panel.")
    con_central.execute("DELETE FROM panel_archivos WHERE panel_id=?", (panel_id,))
    con_central.execute("DELETE FROM paneles_registro WHERE id=? AND usuario_id=?", (panel_id, usuario_id))
    con_central.commit()


def asegurar_local(con_central, panel: dict, ruta_local: Path) -> None:
    """La primera vez que se abre un panel en esta sesión, trae su contenido de la nube a
    `ruta_local`. Si ya se trajo antes en esta sesión (el archivo ya existe), no hace nada:
    evita descargar de nuevo en cada interacción."""
    if not ruta_local.exists():
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        cloud_db.descargar_panel(con_central, panel["id"], ruta_local)


def estadisticas_nube(con_central, panel: dict, ruta_local: Path) -> str:
    asegurar_local(con_central, panel, ruta_local)
    if not ruta_local.exists():
        return "recién creado"
    con = db.conectar(path=ruta_local, marcas=panel.get("marcas"))
    try:
        return _estadisticas_de(con, panel["tipo"])
    finally:
        con.close()
