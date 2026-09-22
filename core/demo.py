"""Datos de ejemplo (100% ficticios) para probar la app sin subir nada."""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd

from . import catalogo, gastos as gs, ingest
from .semanas import semana_de

# nombre, marca, precio venta, costo proveedor, peso (frecuencia)
PRODUCTOS = [
    ("Rayzen Fertilizante 500 g", "Rayzen", 68000, 21000, 30),
    ("Rayzen Fertilizante 1 kg", "Rayzen", 118000, 39000, 22),
    ("Masajeador Cervical", "Dropshipping", 89900, 32000, 26),
    ("Kit Organizador Cocina", "Dropshipping", 129900, 51000, 14),
    ("Reloj Inteligente", "Dropshipping", 155000, 78000, 8),
]
CIUDADES = [("BOGOTA", "CUNDINAMARCA", 0.05), ("MEDELLIN", "ANTIOQUIA", 0.07), ("CALI", "VALLE DEL CAUCA", 0.1),
            ("BARRANQUILLA", "ATLANTICO", 0.14), ("CARTAGENA", "BOLIVAR", 0.16), ("CUCUTA", "NORTE DE SANTANDER", 0.2),
            ("IBAGUE", "TOLIMA", 0.09), ("PASTO", "NARINO", 0.25), ("MONTERIA", "CORDOBA", 0.18)]
TRANSPORTADORAS = [("INTERRAPIDISIMO", 0.12), ("ENVIA", 0.15), ("TCC", 0.24)]
NOMBRES = ["Ana Torres", "Luis Pérez", "María Gómez", "Carlos Ruiz", "Sofía Díaz", "Juan Castro", "Laura Rojas"]
VENDEDORES = ["logistica yina", "LOGISTICA YASMIN", ""]
CAUSAS = ["CLIENTE NO CONTESTA", "DIRECCION ERRADA", "CLIENTE RECHAZA", "NO HAY QUIEN RECIBA", "ZONA DE DIFICIL ACCESO"]
SEMANAS = 8

# Simula un cambio real de precio/costo para que el nuevo panel "Precio y costo" (Pareto) tenga algo
# que mostrar en el demo: el proveedor sube el costo un par de semanas antes de que subas el precio de venta.
CAMBIOS_DEMO = {"Masajeador Cervical": {"costo_desde": SEMANAS - 3, "costo_factor": 1.18,
                                        "precio_desde": SEMANAS - 1, "precio_factor": 1.07}}


def _pedido(rng, n, fecha_pedido, estatus, fecha_reporte, ultimo_mov, semana_idx=None):
    nombre, marca, precio, costo, _ = rng.choices(PRODUCTOS, weights=[p[4] for p in PRODUCTOS])[0]
    if semana_idx is not None and (cambio := CAMBIOS_DEMO.get(nombre)):
        if semana_idx >= cambio["costo_desde"]:
            costo = round(costo * cambio["costo_factor"] / 100) * 100
        if semana_idx >= cambio["precio_desde"]:
            precio = round(precio * cambio["precio_factor"] / 100) * 100
    ciudad, depto, p_dev = rng.choice(CIUDADES)
    transp, p_transp = rng.choice(TRANSPORTADORAS)
    flete = rng.choice([13500, 16500, 19000, 22500])
    if estatus is None:  # pedido ya resuelto: la probabilidad de devolución depende de ciudad y transportadora
        estatus = "DEVOLUCION" if rng.random() < (p_dev + p_transp) / 2 else "ENTREGADO"
    ent = estatus == "ENTREGADO"
    dev = estatus == "DEVOLUCION"
    return {
        "ID": 9000000 + n, "FECHA": fecha_pedido.strftime("%d-%m-%Y"), "FECHA DE REPORTE": fecha_reporte.strftime("%d-%m-%Y"),
        "ESTATUS": estatus, "NOMBRE CLIENTE": rng.choice(NOMBRES), "TELÉFONO": f"3{rng.randint(0, 2)}{rng.randint(10**7, 10**8 - 1)}",
        "DEPARTAMENTO DESTINO": depto, "CIUDAD DESTINO": ciudad, "TRANSPORTADORA": transp,
        "VALOR DE COMPRA EN PRODUCTOS": precio, "TOTAL EN PRECIOS DE PROVEEDOR": costo,
        "GANANCIA": (precio - costo - flete) if ent else None,
        "PRECIO FLETE": flete, "COSTO DEVOLUCION FLETE": rng.choice([13500, 16500, 19000]) if dev else 0, "COMISION": 0,
        "NOVEDAD": rng.choice(CAUSAS) if estatus in ("DEVOLUCION", "NOVEDAD") else "",
        "CONCEPTO ÚLTIMO MOVIMIENTO": {"ENTREGADO": "ENTREGADA", "DEVOLUCION": "DEVOLUCIÓN RATIFICADA",
                                       "RECLAME EN OFICINA": "RECLAME EN OFICINA"}.get(estatus, estatus),
        "FECHA DE ÚLTIMO MOVIMIENTO": ultimo_mov.strftime("%d-%m-%Y"),
        "VENDEDOR": rng.choice(VENDEDORES), "TIENDA": 1007920, "NÚMERO GUIA": f"DEMO{n:07d}",
    }


def poblar(con, hoy: dt.date | None = None, semilla: int = 7) -> dict:
    """Llena la base con SEMANAS semanas de pedidos, gastos y catálogo ficticios."""
    rng = random.Random(semilla)
    hoy = hoy or dt.date.today()
    lunes_actual = hoy - dt.timedelta(days=hoy.weekday())
    n = 0
    for i in range(SEMANAS, 0, -1):  # i semanas atrás; el reporte sale el lunes siguiente
        lunes_sem = lunes_actual - dt.timedelta(weeks=i)
        reporte = lunes_sem + dt.timedelta(days=7)
        filas = []
        semana_idx = SEMANAS - i
        for _ in range(rng.randint(85, 115) + (SEMANAS - i) * 4):
            n += 1
            fecha_pedido = lunes_sem - dt.timedelta(days=rng.randint(4, 12))
            mov = lunes_sem + dt.timedelta(days=rng.randint(0, 6))
            filas.append(_pedido(rng, n, fecha_pedido, None, reporte, mov, semana_idx))
        prep = ingest.preparar_df(pd.DataFrame(filas), f"ordenes_{reporte:%Y%m%d}_080000_demo.xlsx", hoy=hoy)
        ingest.guardar(con, prep)

    # pedidos actuales en riesgo (oficina / novedad) para la lista de llamadas
    filas = []
    for _ in range(26):
        n += 1
        dias = rng.randint(1, 11)
        mov = hoy - dt.timedelta(days=dias)
        estatus = rng.choices(["RECLAME EN OFICINA", "NOVEDAD"], weights=[70, 30])[0]
        filas.append(_pedido(rng, n, mov - dt.timedelta(days=rng.randint(3, 8)), estatus, hoy, mov, SEMANAS))
    for _ in range(18):
        n += 1
        mov = hoy - dt.timedelta(days=rng.randint(0, 3))
        filas.append(_pedido(rng, n, mov - dt.timedelta(days=2), "EN TRANSITO", hoy, mov, SEMANAS))
    ingest.guardar(con, ingest.preparar_df(pd.DataFrame(filas), f"ordenes_{hoy:%Y%m%d}_090000_demo.xlsx", hoy=hoy))

    # catálogo: nombres y marcas
    for nombre, marca, precio, _, _ in PRODUCTOS:
        r = con.execute("SELECT producto_id FROM producto_precios WHERE precio=?", (precio,)).fetchone()
        if r:
            con.execute("UPDATE productos SET nombre=?, marca_id=? WHERE id=?",
                        (nombre, catalogo.marca_id(con, marca), r["producto_id"]))
    con.commit()

    # gastos fijos (apps, nómina, administrativos) y variables semanales
    mid = lambda m: catalogo.marca_id(con, m)  # noqa: E731
    for concepto, cat, monto, marca in [
        ("Lucid Bot", "Apps y suscripciones", 149000, None), ("Notion", "Apps y suscripciones", 48000, None),
        ("Shopify", "Apps y suscripciones", 165000, "Dropshipping"), ("Auxiliar de logística (Yina)", "Nómina (empleados)", 1750000, None),
        ("Asesora de llamadas (Yasmin)", "Nómina (empleados)", 1750000, None),
        ("Contador", "Administrativos", 600000, None), ("Arriendo bodega", "Arriendo y servicios", 900000, "Rayzen")]:
        con.execute("INSERT INTO gastos_fijos(concepto, categoria, monto_mensual, marca_id) VALUES (?,?,?,?)",
                    (concepto, cat, monto, mid(marca) if marca else None))
    for i in range(SEMANAS, -1, -1):
        sem = semana_de(lunes_actual - dt.timedelta(weeks=i))
        for marca, meta, tiktok in (("Rayzen", rng.randint(250, 450) * 1000, rng.randint(80, 200) * 1000),
                                    ("Dropshipping", rng.randint(350, 600) * 1000, rng.randint(120, 300) * 1000)):
            for tipo, monto in (("Publicidad Meta", meta), ("Publicidad TikTok", tiktok), ("Empaques", rng.randint(60, 140) * 1000)):
                con.execute("INSERT INTO gastos_semana(semana, tipo, marca_id, monto) VALUES (?,?,?,?)", (sem, tipo, mid(marca), monto))
    con.commit()
    return {"pedidos": con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]}


def crear_si_falta(con) -> None:
    if con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 0:
        poblar(con)
