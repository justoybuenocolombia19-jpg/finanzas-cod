"""Carga de reportes Excel (Dropi / Globaltradecol).

Flujo: preparar_archivo() lee y normaliza (sin tocar la base) -> guardar() hace el
upsert por ID. Un pedido que ya existe se actualiza al estado más reciente; un
reporte viejo nunca pisa un estado más nuevo.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

from . import catalogo
from .semanas import semana_de, semana_de_reporte

ESTADOS = ["ENTREGADO", "DEVUELTO", "EN_OFICINA", "NOVEDAD", "EN_TRANSITO", "PENDIENTE", "CANCELADO", "OTRO"]

# Cuál gana si dos filas del mismo pedido traen la misma fecha de reporte.
_RANGO = {"ENTREGADO": 5, "DEVUELTO": 5, "CANCELADO": 4, "EN_OFICINA": 3, "NOVEDAD": 3,
          "EN_TRANSITO": 2, "PENDIENTE": 1, "OTRO": 0}

# Reglas por palabra clave sobre el ESTATUS (ya sin tildes ni mayúsculas). El orden importa.
_REGLAS = [
    ("ENTREGAD", "ENTREGADO"),
    ("DEVOLUCION", "DEVUELTO"), ("DEVUELT", "DEVUELTO"),
    ("RECLAME", "EN_OFICINA"), ("EN OFICINA", "EN_OFICINA"),
    ("NOVEDAD", "NOVEDAD"),
    ("CANCEL", "CANCELADO"),
    ("TRANSITO", "EN_TRANSITO"), ("REPARTO", "EN_TRANSITO"), ("DESPACH", "EN_TRANSITO"),
    ("GUIA GENERADA", "EN_TRANSITO"), ("PROCESAMIENTO", "EN_TRANSITO"), ("BODEGA", "EN_TRANSITO"),
    ("RECOLECC", "EN_TRANSITO"), ("ADMITID", "EN_TRANSITO"), ("PREPARAD", "EN_TRANSITO"),
    ("PENDIENTE", "PENDIENTE"),
]

# nombre normalizado de columna -> campo interno (primer alias encontrado gana)
_COLUMNAS = {
    "id": ["ID"],
    "fecha_pedido": ["FECHA"],
    "fecha_reporte": ["FECHA DE REPORTE"],
    "estatus": ["ESTATUS", "ESTADO"],
    "cliente": ["NOMBRE CLIENTE", "CLIENTE"],
    "telefono": ["TELEFONO", "CELULAR"],
    "departamento": ["DEPARTAMENTO DESTINO", "DEPARTAMENTO"],
    "ciudad": ["CIUDAD DESTINO", "CIUDAD"],
    "transportadora": ["TRANSPORTADORA"],
    "guia": ["NUMERO GUIA", "GUIA"],
    "tienda_id": ["TIENDA"],
    "vendedor": ["VENDEDOR"],
    "categoria": ["CATEGORIAS", "CATEGORIA"],
    "valor_venta": ["VALOR DE COMPRA EN PRODUCTOS"],
    "costo_proveedor": ["TOTAL EN PRECIOS DE PROVEEDOR"],
    "ganancia": ["GANANCIA"],
    "flete_ida": ["PRECIO FLETE"],
    "flete_devolucion": ["COSTO DEVOLUCION FLETE"],
    "comision": ["COMISION"],
    "novedad": ["NOVEDAD"],
    "concepto_ultimo_mov": ["CONCEPTO ULTIMO MOVIMIENTO"],
    "fecha_ultimo_mov": ["FECHA DE ULTIMO MOVIMIENTO"],
}
_TEXTO = ["cliente", "telefono", "departamento", "ciudad", "transportadora", "guia", "tienda_id",
          "vendedor", "categoria", "novedad", "concepto_ultimo_mov"]
_NUMERICOS = ["valor_venta", "costo_proveedor", "ganancia", "flete_ida", "flete_devolucion", "comision"]

CAMPOS_DB = ["id", "fecha_pedido", "fecha_reporte", "semana_pedido", "semana_estado", "semana_movimiento",
             "estatus_original", "estado", *_TEXTO, *_NUMERICOS, "fecha_ultimo_mov"]


# ---------------------------------------------------------------- limpieza de datos

def normalizar_texto(s) -> str:
    """Sin tildes, mayúsculas, espacios y guiones bajos colapsados."""
    if s is None or (isinstance(s, float) and s != s):
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", " ", s).strip().upper()


def clasificar(estatus, custom: dict | None = None) -> str:
    n = normalizar_texto(estatus)
    if custom and n in custom:
        return custom[n]
    for clave, estado in _REGLAS:
        if clave in n:
            return estado
    return "OTRO"


def _a_numero(v) -> float:
    if v is None or (isinstance(v, float) and v != v):
        return 0.0
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = str(v).strip()
    if s in ("", "-", "nan", "None"):
        return 0.0
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d,.]", "", s)
    if "," in s and "." in s:  # el último separador es el decimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return -x if neg else x


def _a_texto(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, np.integer):
        return str(int(v))
    return str(v).strip()


def _a_fecha(v):
    """-> 'YYYY-MM-DD' o None. Acepta dd-mm-aaaa, dd/mm/aaaa, aaaa-mm-dd y fechas de Excel."""
    if v is None or v is pd.NaT or (isinstance(v, float) and v != v) or str(v).strip() == "":
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    s = str(v).strip()[:10]
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    t = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(t) else t.strftime("%Y-%m-%d")


def _semana(iso, reporte=False):
    if not iso:
        return None
    d = dt.date.fromisoformat(iso)
    return semana_de_reporte(d) if reporte else semana_de(d)


# ---------------------------------------------------------------- preparación (sin base de datos)

def preparar_df(raw: pd.DataFrame, nombre: str, custom: dict | None = None,
                semana_forzada: str | None = None, contenido: bytes = b"", hoy: dt.date | None = None) -> dict:
    """Normaliza un DataFrame crudo. Devuelve un dict 'prep' con df limpio y un resumen."""
    hoy = hoy or dt.date.today()
    prep = {"nombre": nombre, "hash": hashlib.sha1(contenido).hexdigest() if contenido else "",
            "error": None, "df": None, "filas": len(raw), "sin_id": 0, "semana": None,
            "fecha_reporte": None, "estados": Counter(), "advertencias": []}
    norm = {}
    for c in raw.columns:
        norm.setdefault(normalizar_texto(c), c)
    if "ID" not in norm or not ({"ESTATUS", "ESTADO"} & set(norm)):
        prep["error"] = ("No parece un reporte de pedidos: faltan las columnas ID y/o ESTATUS. "
                         f"Columnas encontradas: {', '.join(list(norm)[:8])}…")
        return prep

    df = pd.DataFrame(index=raw.index)
    faltantes = []
    for campo, alias in _COLUMNAS.items():
        origen = next((norm[a] for a in alias if a in norm), None)
        if origen is None:
            df[campo] = None
            if campo in ("valor_venta", "ganancia", "flete_ida", "flete_devolucion", "costo_proveedor"):
                faltantes.append(alias[0])
        else:
            df[campo] = raw[origen]
    if faltantes:
        prep["advertencias"].append("Columnas ausentes (se asumen en 0): " + ", ".join(faltantes))

    df["id"] = df["id"].map(_a_texto)
    prep["sin_id"] = int((df["id"] == "").sum())
    df = df[df["id"] != ""].copy()
    for c in _TEXTO:
        df[c] = df[c].map(_a_texto)
    for c in _NUMERICOS:
        df[c] = df[c].map(_a_numero)
    for c in ("fecha_pedido", "fecha_reporte", "fecha_ultimo_mov"):
        df[c] = df[c].map(_a_fecha)

    m = re.search(r"(20\d{2})(\d{2})(\d{2})", nombre)  # ordenes_20260921_093215.xlsx
    try:
        f_nombre = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat() if m else None
    except ValueError:
        f_nombre = None
    df["fecha_reporte"] = df["fecha_reporte"].fillna(f_nombre or hoy.isoformat())

    df["estatus_original"] = df["estatus"].map(_a_texto)
    df["estado"] = df["estatus_original"].map(lambda x: clasificar(x, custom))
    df = df.drop(columns=["estatus"])

    sem_rep = df["fecha_reporte"].map(lambda f: _semana(f, reporte=True))
    df["semana_estado"] = semana_forzada or sem_rep
    df["semana_pedido"] = df["fecha_pedido"].map(_semana).fillna(df["semana_estado"])
    df["semana_movimiento"] = df["fecha_ultimo_mov"].map(_semana).fillna(df["semana_estado"])

    prep["df"] = df
    prep["estados"] = Counter(zip(df["estatus_original"], df["estado"]))
    if len(df):
        prep["fecha_reporte"] = df["fecha_reporte"].max()
        prep["semana"] = semana_forzada or _semana(prep["fecha_reporte"], reporte=True)
    return prep


def preparar_archivo(nombre: str, contenido: bytes, custom: dict | None = None,
                     semana_forzada: str | None = None, hoy: dt.date | None = None) -> dict:
    try:
        raw = pd.read_excel(io.BytesIO(contenido), engine="openpyxl")
    except Exception as e:  # archivo dañado, no es xlsx, etc.
        return {"nombre": nombre, "error": f"No se pudo leer el Excel: {e}", "df": None, "filas": 0,
                "sin_id": 0, "semana": None, "fecha_reporte": None, "estados": Counter(),
                "advertencias": [], "hash": ""}
    return preparar_df(raw, nombre, custom, semana_forzada, contenido, hoy)


# ---------------------------------------------------------------- persistencia

def mapa_estados(con) -> dict:
    return {r["estatus"]: r["estado"] for r in con.execute("SELECT estatus, estado FROM estado_map")}


def guardar(con, prep: dict) -> dict:
    """Upsert por ID. Devuelve el resumen de la carga."""
    df = prep["df"]
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    res = {"archivo": prep["nombre"], "filas": prep["filas"], "nuevas": 0, "actualizadas": 0,
           "sin_cambio": 0, "desactualizadas": 0, "ignoradas": prep["sin_id"], "repetidas_en_archivo": 0,
           "transiciones": Counter(), "semana": prep["semana"], "productos_nuevos": 0}

    df = df.assign(_rango=df["estado"].map(_RANGO)).sort_values(["fecha_reporte", "_rango"])
    antes = len(df)
    df = df.drop_duplicates("id", keep="last")
    res["repetidas_en_archivo"] = antes - len(df)

    cur = con.execute(
        "INSERT INTO cargas(archivo, hash, fecha_carga, fecha_reporte, semana, filas) VALUES (?,?,?,?,?,?)",
        (prep["nombre"], prep["hash"], ahora, prep["fecha_reporte"], prep["semana"], prep["filas"]))
    carga_id = cur.lastrowid

    existentes = {r["id"]: r for r in con.execute(
        "SELECT id, estado, fecha_reporte, semana_estado FROM pedidos")}
    escribir, historial = [], []
    for r in df.to_dict("records"):
        previo = existentes.get(r["id"])
        if previo is None:
            res["nuevas"] += 1
            historial.append((r["id"], r["estado"], r["fecha_reporte"], carga_id))
        elif (r["fecha_reporte"], _RANGO[r["estado"]]) < (previo["fecha_reporte"] or "", _RANGO.get(previo["estado"], 0)):
            res["desactualizadas"] += 1  # reporte más viejo que lo que ya tenemos
            continue
        elif r["estado"] != previo["estado"]:
            res["actualizadas"] += 1
            res["transiciones"][f"{previo['estado']} → {r['estado']}"] += 1
            historial.append((r["id"], r["estado"], r["fecha_reporte"], carga_id))
        else:
            res["sin_cambio"] += 1
            # mismo estado: se conserva la semana en que el pedido llegó a ese estado
            r["semana_estado"] = previo["semana_estado"] or r["semana_estado"]
        escribir.append(tuple(r[c] for c in CAMPOS_DB) + (carga_id, ahora))

    marcadores = ",".join("?" * (len(CAMPOS_DB) + 2))
    con.executemany(
        f"INSERT OR REPLACE INTO pedidos({','.join(CAMPOS_DB)}, carga_id, actualizado_en) VALUES ({marcadores})",
        escribir)
    con.executemany("INSERT INTO pedidos_historial(pedido_id, estado, fecha_reporte, carga_id) VALUES (?,?,?,?)",
                    historial)
    con.execute("UPDATE cargas SET nuevas=?, actualizadas=?, sin_cambio=?, desactualizadas=?, ignoradas=? WHERE id=?",
                (res["nuevas"], res["actualizadas"], res["sin_cambio"], res["desactualizadas"], res["ignoradas"], carga_id))
    con.commit()

    res["productos_nuevos"] = catalogo.asegurar(
        con, df["valor_venta"].round().astype(int).tolist(), df["tienda_id"].tolist())
    return res


def asignar_estado(con, estatus: str, estado: str) -> int:
    """Enseña a la app qué estado interno corresponde a un ESTATUS desconocido y
    reclasifica los pedidos ya cargados. Devuelve cuántos pedidos cambiaron."""
    n = normalizar_texto(estatus)
    con.execute("INSERT OR REPLACE INTO estado_map(estatus, estado) VALUES (?,?)", (n, estado))
    ids = [r["id"] for r in con.execute("SELECT id, estatus_original FROM pedidos")
           if normalizar_texto(r["estatus_original"]) == n]
    con.executemany("UPDATE pedidos SET estado=? WHERE id=?", [(estado, i) for i in ids])
    con.commit()
    return len(ids)
