"""Contexto de análisis: lo que el usuario eligió (marca y rango de semanas) ya calculado."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import catalogo, gastos as gs
from .data import cargar_pedidos
from .semanas import semanas_entre

CONSOLIDADO = "Consolidado"


@dataclass
class Contexto:
    con: object
    demo: bool
    marca: str
    semanas: list                      # todas las semanas del rango elegido (continuas)
    semanas_disponibles: list          # semanas con datos o gastos
    df_todo: pd.DataFrame              # todas las marcas, todo el tiempo
    df_marca: pd.DataFrame             # marca elegida, todo el tiempo (para alertas)
    df: pd.DataFrame                   # marca elegida + rango de semanas
    df_rango_todas: pd.DataFrame       # todas las marcas + rango (para comparar marcas)
    gastos: pd.DataFrame               # gastos de la marca y rango
    marcas: list = field(default_factory=list)   # marcas con opciones de filtro
    panel_nombre: str = ""

    def gastos_de(self, marca: str) -> pd.DataFrame:
        if marca == CONSOLIDADO:
            return gs.gastos_semanales(self.con, self.semanas)
        f = gs.factor_compartido(self.df_rango_todas, marca, self.marcas)
        return gs.gastos_semanales(self.con, self.semanas, marca, f)

    @property
    def titulo(self) -> str:
        if self.marca == CONSOLIDADO and self.panel_nombre and len(self.marcas) <= 1:
            return self.panel_nombre
        return self.marca


def semanas_disponibles(con, df: pd.DataFrame) -> list:
    s = set(df["semana"].dropna()) if len(df) else set()
    s |= set(gs.semanas_con_gastos(con))
    return sorted(s)


def marcas_visibles(con, todo: pd.DataFrame) -> list:
    marcas = catalogo.marcas(con)
    if len(todo) and (todo["marca"] == "Sin asignar").any():
        marcas = marcas + ["Sin asignar"]
    return marcas


def construir(con, demo: bool = False, marca: str = CONSOLIDADO, desde: str | None = None,
              hasta: str | None = None, todo: pd.DataFrame | None = None, panel_nombre: str = "",
              semanas_elegidas: list | None = None) -> Contexto:
    """`semanas_elegidas`, si se da, reemplaza a desde/hasta: una selección suelta de semanas
    (no necesariamente continua) para armar comparativos a la medida."""
    todo = cargar_pedidos(con) if todo is None else todo
    disp = semanas_disponibles(con, todo)
    marcas = marcas_visibles(con, todo)

    if semanas_elegidas is not None:
        semanas = sorted(set(semanas_elegidas) & set(disp))
    elif disp:
        continuas = semanas_entre(disp[0], disp[-1])
        desde = desde if desde in continuas else disp[0]
        hasta = hasta if hasta in continuas else disp[-1]
        if desde > hasta:
            desde, hasta = hasta, desde
        semanas = semanas_entre(desde, hasta)
    else:
        semanas = []

    rango_todas = todo[todo["semana"].isin(semanas)] if len(todo) else todo
    if marca == CONSOLIDADO or not len(todo):
        df_marca, df = todo, rango_todas
    else:
        df_marca = todo[todo["marca"] == marca]
        df = rango_todas[rango_todas["marca"] == marca]

    ctx = Contexto(con=con, demo=demo, marca=marca, semanas=semanas, semanas_disponibles=disp,
                   df_todo=todo, df_marca=df_marca, df=df, df_rango_todas=rango_todas,
                   gastos=pd.DataFrame(columns=gs.COLUMNAS), marcas=marcas, panel_nombre=panel_nombre)
    ctx.gastos = ctx.gastos_de(marca)
    return ctx
