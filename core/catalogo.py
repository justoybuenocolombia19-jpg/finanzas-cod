"""Catálogo de productos (agrupados por precio de venta) y mapeo tienda -> marca."""
from __future__ import annotations

from typing import Iterable

from .fmt import cop


def asegurar(con, precios: Iterable[int], tiendas: Iterable[str]) -> int:
    """Crea un producto por cada precio de venta nuevo y registra las tiendas nuevas.
    Devuelve cuántos productos nuevos se crearon."""
    creados = 0
    conocidos = {r["precio"] for r in con.execute("SELECT precio FROM producto_precios")}
    for p in sorted({int(x) for x in precios if x and int(x) > 0} - conocidos):
        cur = con.execute("INSERT INTO productos(nombre) VALUES (?)", (f"Producto {cop(p)}",))
        con.execute("INSERT INTO producto_precios(precio, producto_id) VALUES (?,?)", (p, cur.lastrowid))
        creados += 1
    for t in {str(x) for x in tiendas if x}:
        con.execute("INSERT OR IGNORE INTO tiendas(tienda_id) VALUES (?)", (t,))
    con.commit()
    return creados


def marcas(con) -> list:
    return [r["nombre"] for r in con.execute("SELECT nombre FROM marcas ORDER BY id")]


def marca_id(con, nombre):
    if not nombre:
        return None
    r = con.execute("SELECT id FROM marcas WHERE nombre=?", (nombre,)).fetchone()
    return r["id"] if r else None


def productos(con):
    """Lista de productos con su marca y los precios que agrupa."""
    filas = con.execute(
        """SELECT p.id, p.nombre, p.sku, m.nombre AS marca,
                  (SELECT GROUP_CONCAT(precio, ', ') FROM producto_precios WHERE producto_id=p.id) AS precios
           FROM productos p LEFT JOIN marcas m ON m.id=p.marca_id ORDER BY p.id"""
    ).fetchall()
    return [dict(f) for f in filas]


def guardar_productos(con, filas: list) -> str:
    """filas: dicts con id, nombre, sku, marca. Devuelve mensaje de error o ''."""
    nombres = [str(f["nombre"]).strip() for f in filas]
    if any(not n for n in nombres):
        return "Todos los productos necesitan un nombre."
    if len(set(n.lower() for n in nombres)) != len(nombres):
        return "Hay nombres de producto repetidos: cada producto debe tener un nombre único."
    for f in filas:
        con.execute("UPDATE productos SET nombre=?, sku=?, marca_id=? WHERE id=?",
                    (str(f["nombre"]).strip(), (f.get("sku") or None), marca_id(con, f.get("marca")), f["id"]))
    con.commit()
    return ""


def precios(con):
    """Precios de venta detectados, con cuántos pedidos tienen y a qué producto apuntan."""
    filas = con.execute(
        """SELECT pp.precio, pr.nombre AS producto,
                  (SELECT COUNT(*) FROM pedidos p WHERE CAST(ROUND(p.valor_venta) AS INTEGER)=pp.precio) AS pedidos
           FROM producto_precios pp LEFT JOIN productos pr ON pr.id=pp.producto_id
           ORDER BY pedidos DESC, pp.precio"""
    ).fetchall()
    return [dict(f) for f in filas]


def guardar_precios(con, filas: list) -> None:
    ids = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM productos")}
    for f in filas:
        pid = ids.get(f["producto"])
        if pid:
            con.execute("UPDATE producto_precios SET producto_id=? WHERE precio=?", (pid, int(f["precio"])))
    con.commit()


def eliminar_productos_huerfanos(con) -> None:
    con.execute("DELETE FROM productos WHERE id NOT IN (SELECT producto_id FROM producto_precios WHERE producto_id IS NOT NULL)")
    con.commit()


def tiendas(con):
    filas = con.execute(
        """SELECT t.tienda_id, m.nombre AS marca,
                  (SELECT COUNT(*) FROM pedidos p WHERE p.tienda_id=t.tienda_id) AS pedidos
           FROM tiendas t LEFT JOIN marcas m ON m.id=t.marca_id ORDER BY pedidos DESC"""
    ).fetchall()
    return [dict(f) for f in filas]


def guardar_tiendas(con, filas: list) -> None:
    for f in filas:
        con.execute("UPDATE tiendas SET marca_id=? WHERE tienda_id=?", (marca_id(con, f.get("marca")), f["tienda_id"]))
    con.commit()


def listar_marcas(con) -> list:
    return [dict(r) for r in con.execute("SELECT id, nombre FROM marcas ORDER BY id")]


def guardar_marcas(con, filas: list) -> str:
    """Renombra marcas existentes. Devuelve mensaje de error o ''."""
    nombres = [str(f["nombre"]).strip() for f in filas]
    if any(not n for n in nombres) or len({n.lower() for n in nombres}) != len(nombres):
        return "Cada marca necesita un nombre único."
    for f in filas:
        con.execute("UPDATE marcas SET nombre=? WHERE id=?", (str(f["nombre"]).strip(), f["id"]))
    con.commit()
    return ""


def agregar_marca(con, nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        return "Escribe un nombre."
    if con.execute("SELECT 1 FROM marcas WHERE lower(nombre)=lower(?)", (nombre,)).fetchone():
        return "Ya existe una marca con ese nombre."
    con.execute("INSERT INTO marcas(nombre) VALUES (?)", (nombre,))
    con.commit()
    return ""
