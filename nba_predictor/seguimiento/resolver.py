"""
Resolución automática de picks y líneas con los box scores de ESPN.

Al día siguiente de un partido, los puntos reales están en ESPN: no hace
falta marcar a mano si un pick ganó o perdió. Un jugador que no jugó deja
el pick anulado (VOID), como hacen las casas con los props.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from nba_predictor.datos import espn
from nba_predictor.datos.boxscore import filas_de_partido
from nba_predictor.datos.hoy import temporada_de


def puntos_del_dia(dia: date) -> pd.DataFrame:
    """Puntos de cada jugador en los partidos terminados de un día."""
    temporada = temporada_de(dia)
    filas = []
    for p in espn.partidos_del_dia(dia):
        if not p["terminado"]:
            continue
        resumen = espn.resumen_partido(p["id"], temporada)
        jugadores, _ = filas_de_partido(resumen, temporada, p["id"])
        filas.extend(jugadores)
    if not filas:
        return pd.DataFrame(columns=["athlete_id", "jugador", "PTS", "no_jugo"])
    return pd.DataFrame(filas)[["athlete_id", "jugador", "PTS", "no_jugo"]]


def resultado_pick(lado: str, linea: float, pts: float | None, no_jugo: bool) -> str:
    if no_jugo or pts is None or pd.isna(pts):
        return "VOID"
    if lado == "OVER":
        return "W" if pts > linea else "L"
    return "W" if pts < linea else "L"


def buscar(puntos: pd.DataFrame, athlete_id, jugador: str):
    """Fila del jugador en el día: por id si se tiene, si no por nombre."""
    if athlete_id and str(athlete_id) in set(puntos["athlete_id"]):
        return puntos[puntos["athlete_id"] == str(athlete_id)].iloc[0]
    por_nombre = puntos[puntos["jugador"].str.lower() == str(jugador).lower()]
    return por_nombre.iloc[0] if len(por_nombre) == 1 else None


def resolver_pendientes(ledger: pd.DataFrame, hoy: date | None = None) -> list[tuple[int, str, float | None]]:
    """
    (id, resultado, puntos) de cada pick pendiente cuyo partido ya terminó.
    No escribe nada: el llamador decide si registra los resultados.
    """
    hoy = hoy or datetime.now().date()
    pendientes = ledger[ledger["resultado"].isna()].copy()
    if pendientes.empty:
        return []
    pendientes["dia"] = pd.to_datetime(pendientes["fecha"]).dt.date
    salida = []
    for dia, grupo in pendientes.groupby("dia"):
        if dia >= hoy:
            continue
        puntos = puntos_del_dia(dia)
        if puntos.empty:
            continue
        for fila in grupo.itertuples():
            j = buscar(puntos, getattr(fila, "athlete_id", None), fila.jugador)
            if j is None:
                continue
            res = resultado_pick(fila.lado, float(fila.linea), j["PTS"], bool(j["no_jugo"]))
            salida.append((int(fila.id), res, None if pd.isna(j["PTS"]) else float(j["PTS"])))
    return salida
