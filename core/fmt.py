"""Formato colombiano: COP $1.234.567, porcentajes con coma, fechas dd-mm-aaaa."""
from __future__ import annotations

import pandas as pd


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and x != x) or x is pd.NaT


def cop(x) -> str:
    if _nan(x):
        return "—"
    v = float(x)
    s = f"{abs(v):,.0f}".replace(",", ".")
    return f"-${s}" if v < 0 and round(v) != 0 else f"${s}"


def num(x) -> str:
    if _nan(x):
        return "—"
    return f"{float(x):,.0f}".replace(",", ".")


def pct(x, d: int = 1) -> str:
    if _nan(x):
        return "—"
    return f"{float(x) * 100:.{d}f}".replace(".", ",") + "%"


def veces(x) -> str:
    if _nan(x):
        return "—"
    return f"{float(x):.2f}".replace(".", ",") + "x"


def dmy(x) -> str:
    if _nan(x) or x == "":
        return ""
    try:
        return pd.to_datetime(x).strftime("%d-%m-%Y")
    except Exception:
        return str(x)
