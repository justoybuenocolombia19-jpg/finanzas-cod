"""Conexión y esquema SQLite. Toda la data vive en data/finanzas.db (demo en data/demo.db)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("FINANZAS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

MARCAS_INICIALES = ["Rayzen", "Dropshipping"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS marcas (
    id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL);

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, sku TEXT,
    marca_id INTEGER REFERENCES marcas(id));

-- precio de venta -> producto (permite agrupar variantes en un solo producto)
CREATE TABLE IF NOT EXISTS producto_precios (
    precio INTEGER PRIMARY KEY, producto_id INTEGER REFERENCES productos(id));

-- id de tienda de la plataforma -> marca (respaldo cuando el producto no tiene marca)
CREATE TABLE IF NOT EXISTS tiendas (
    tienda_id TEXT PRIMARY KEY, marca_id INTEGER REFERENCES marcas(id));

-- estatus desconocidos que el usuario asignó a un estado conocido
CREATE TABLE IF NOT EXISTS estado_map (
    estatus TEXT PRIMARY KEY, estado TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS cargas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, archivo TEXT, hash TEXT,
    fecha_carga TEXT, fecha_reporte TEXT, semana TEXT,
    filas INTEGER, nuevas INTEGER, actualizadas INTEGER,
    sin_cambio INTEGER, desactualizadas INTEGER, ignoradas INTEGER);

CREATE TABLE IF NOT EXISTS pedidos (
    id TEXT PRIMARY KEY,
    fecha_pedido TEXT, fecha_reporte TEXT,
    semana_pedido TEXT, semana_estado TEXT, semana_movimiento TEXT,
    estatus_original TEXT, estado TEXT,
    cliente TEXT, telefono TEXT, departamento TEXT, ciudad TEXT,
    transportadora TEXT, guia TEXT, tienda_id TEXT, vendedor TEXT, categoria TEXT,
    valor_venta REAL, costo_proveedor REAL, ganancia REAL,
    flete_ida REAL, flete_devolucion REAL, comision REAL,
    novedad TEXT, concepto_ultimo_mov TEXT, fecha_ultimo_mov TEXT,
    carga_id INTEGER, actualizado_en TEXT);
CREATE INDEX IF NOT EXISTS ix_pedidos_estado ON pedidos(estado);
CREATE INDEX IF NOT EXISTS ix_pedidos_semana ON pedidos(semana_estado);

CREATE TABLE IF NOT EXISTS pedidos_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id TEXT, estado TEXT,
    fecha_reporte TEXT, carga_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_hist_pedido ON pedidos_historial(pedido_id);

-- marca_id NULL = gasto compartido entre marcas
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, concepto TEXT NOT NULL, categoria TEXT NOT NULL,
    monto_mensual REAL NOT NULL, marca_id INTEGER REFERENCES marcas(id),
    desde TEXT, hasta TEXT, activo INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS gastos_semana (
    id INTEGER PRIMARY KEY AUTOINCREMENT, semana TEXT NOT NULL, tipo TEXT NOT NULL,
    marca_id INTEGER REFERENCES marcas(id), monto REAL NOT NULL, nota TEXT);
CREATE INDEX IF NOT EXISTS ix_gsem ON gastos_semana(semana);

CREATE TABLE IF NOT EXISTS llamadas (
    pedido_id TEXT PRIMARY KEY, llamado INTEGER NOT NULL DEFAULT 0,
    resultado TEXT, nota TEXT, fecha_llamada TEXT);

-- bitácora: periodo es '2026-W38' (semana) o '2026-09' (mes)
CREATE TABLE IF NOT EXISTS notas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, periodo TEXT NOT NULL, texto TEXT NOT NULL, creado_en TEXT);
CREATE INDEX IF NOT EXISTS ix_notas_periodo ON notas(periodo);

-- panel personal: ingresos y gastos sueltos
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, tipo TEXT NOT NULL,
    categoria TEXT, monto REAL NOT NULL, nota TEXT);
CREATE INDEX IF NOT EXISTS ix_mov_fecha ON movimientos(fecha);

CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT);
"""


def ruta(demo: bool = False) -> Path:
    return DATA_DIR / ("demo.db" if demo else "finanzas.db")


def conectar(demo: bool = False, path=None, marcas: list | None = None) -> sqlite3.Connection:
    p = Path(path) if path else ruta(demo)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(ESQUEMA)
    # Las marcas iniciales solo se siembran en una base nueva (así se pueden renombrar sin que reaparezcan).
    if con.execute("SELECT COUNT(*) FROM marcas").fetchone()[0] == 0:
        for m in (MARCAS_INICIALES if marcas is None else marcas):
            con.execute("INSERT OR IGNORE INTO marcas(nombre) VALUES (?)", (m,))
    con.commit()
    return con


def get_config(con, clave: str, defecto=None):
    r = con.execute("SELECT valor FROM config WHERE clave=?", (clave,)).fetchone()
    return r["valor"] if r else defecto


def set_config(con, clave: str, valor: str) -> None:
    con.execute("INSERT OR REPLACE INTO config(clave, valor) VALUES (?,?)", (clave, valor))
    con.commit()


def reiniciar(con) -> None:
    """Borra toda la data operativa (pedidos, gastos, catálogo, cargas)."""
    for t in ["pedidos", "pedidos_historial", "cargas", "llamadas", "gastos_fijos",
              "gastos_semana", "notas", "movimientos", "producto_precios", "productos", "tiendas", "estado_map"]:
        con.execute(f"DELETE FROM {t}")
    con.commit()
