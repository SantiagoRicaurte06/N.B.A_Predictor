"""
Convierte los resúmenes de ESPN cacheados en dos tablas:

- jugador-partido: una fila por jugador convocado y partido, incluidos los
  que no jugaron (con su motivo). Es la base de todas las features.
- equipo-partido: una fila por equipo y partido, con su marcador, posesiones
  estimadas y las líneas de la casa (spread y total).

Las tablas se guardan en `cache/espn/tablas/` y solo se reconstruyen cuando
cambian los partidos descargados.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nba_predictor.datos.espn import CACHE_ESPN, ruta_lineas

TABLAS = CACHE_ESPN / "tablas"
ZONA_NBA = "America/New_York"   # la "fecha del partido" es la de la costa este

# Etiquetas del box score de ESPN. Las "M-A" se parten en anotados e intentos.
_SIMPLES = {"MIN": "MIN", "PTS": "PTS", "REB": "REB", "AST": "AST", "TO": "TOV",
            "STL": "STL", "BLK": "BLK", "OREB": "OREB", "DREB": "DREB",
            "PF": "PF", "+/-": "PLUS_MINUS"}
_DOBLES = {"FG": ("FGM", "FGA"), "3PT": ("FG3M", "FG3A"), "FT": ("FTM", "FTA")}
_COLS_STATS = ["MIN", "PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
               "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"]


def _num(valor) -> float:
    try:
        return float(str(valor).replace("+", ""))
    except (TypeError, ValueError):
        return np.nan


def _parsear_stats(labels: list[str], valores: list[str]) -> dict:
    fila = {}
    for etiqueta, valor in zip(labels, valores):
        if etiqueta in _SIMPLES:
            fila[_SIMPLES[etiqueta]] = _num(valor)
        elif etiqueta in _DOBLES:
            anotados, intentos = (str(valor).split("-") + [None])[:2]
            fila[_DOBLES[etiqueta][0]] = _num(anotados)
            fila[_DOBLES[etiqueta][1]] = _num(intentos)
    return fila


def filas_de_partido(resumen: dict, temporada: str, evento: str) -> tuple[list[dict], list[dict]]:
    """Filas jugador-partido y equipo-partido de un resumen de ESPN."""
    comp = resumen["header"]["competitions"][0]
    fecha_utc = pd.Timestamp(comp["date"])
    fecha = fecha_utc.tz_convert(ZONA_NBA).tz_localize(None).normalize()
    tipo = resumen["header"].get("season", {}).get("type")

    marcador = {}
    for c in comp["competitors"]:
        marcador[c["team"]["abbreviation"]] = {
            "local": c["homeAway"] == "home",
            "pts": _num(c.get("score")),
            "team_id": c["team"].get("id"),
        }
    if len(marcador) != 2:
        return [], []
    equipos = list(marcador)
    rival_de = {equipos[0]: equipos[1], equipos[1]: equipos[0]}
    base = {"temporada": temporada, "evento": str(evento), "fecha": fecha,
            "fecha_utc": fecha_utc.tz_localize(None), "tipo": tipo,
            "neutral": bool(comp.get("neutralSite"))}

    jugadores = []
    for bloque in resumen.get("boxscore", {}).get("players", []):
        equipo = bloque["team"]["abbreviation"]
        if equipo not in marcador:
            continue
        stats = bloque["statistics"][0]
        for a in stats.get("athletes", []):
            atleta = a.get("athlete", {})
            no_jugo = bool(a.get("didNotPlay")) or not a.get("stats")
            fila = {**base, "equipo": equipo, "rival": rival_de[equipo],
                    "local": marcador[equipo]["local"],
                    "athlete_id": str(atleta.get("id")),
                    "jugador": atleta.get("displayName"),
                    "posicion": (atleta.get("position") or {}).get("abbreviation"),
                    "titular": bool(a.get("starter")),
                    "no_jugo": no_jugo,
                    "motivo": (a.get("reason") or "").strip() if no_jugo else "",
                    "expulsado": bool(a.get("ejected"))}
            if not no_jugo:
                fila.update(_parsear_stats(stats["labels"], a["stats"]))
            jugadores.append(fila)

    equipos_filas = []
    for bloque in resumen.get("boxscore", {}).get("teams", []):
        equipo = bloque["team"]["abbreviation"]
        if equipo not in marcador:
            continue
        st = {s.get("label") or s.get("name"): s.get("displayValue") for s in bloque.get("statistics", [])}
        fila = {**base, "equipo": equipo, "rival": rival_de[equipo],
                "local": marcador[equipo]["local"],
                "pts": marcador[equipo]["pts"],
                "pts_rival": marcador[rival_de[equipo]]["pts"]}
        for etiqueta, (m, a) in _DOBLES.items():
            hechos, intentos = (str(st.get(etiqueta, "")).split("-") + [None])[:2]
            fila[m], fila[a] = _num(hechos), _num(intentos)
        fila["OREB"] = _num(st.get("Offensive Rebounds"))
        fila["TOV"] = _num(st.get("Turnovers") or st.get("Total Turnovers"))
        equipos_filas.append(fila)
    return jugadores, equipos_filas


def _lineas(temporada: str, evento: str) -> dict:
    ruta = ruta_lineas(temporada, evento)
    if ruta.exists():
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {}


def construir_tablas(temporadas: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee todos los resúmenes cacheados de las temporadas y arma las tablas."""
    jugadores, equipos = [], []
    for temporada in temporadas:
        carpeta = CACHE_ESPN / temporada / "partidos"
        for ruta in sorted(carpeta.glob("*.json.gz")):
            evento = ruta.name.split(".")[0]
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                resumen = json.load(f)
            try:
                j, e = filas_de_partido(resumen, temporada, evento)
            except (KeyError, IndexError, TypeError):
                continue
            lineas = _lineas(temporada, evento)
            for fila in e:
                spread = lineas.get("spread_local")
                fila["spread_equipo"] = (np.nan if spread is None
                                         else (spread if fila["local"] else -spread))
                fila["total_linea"] = lineas.get("total", np.nan)
            jugadores.extend(j)
            equipos.extend(e)

    jp = pd.DataFrame(jugadores)
    for c in _COLS_STATS:
        if c not in jp.columns:
            jp[c] = np.nan
    jp = jp.sort_values(["fecha_utc", "evento", "equipo", "athlete_id"]).reset_index(drop=True)

    ep = pd.DataFrame(equipos)
    # Posesiones estimadas (fórmula estándar de Oliver): miden el ritmo real.
    ep["posesiones"] = ep["FGA"] + 0.44 * ep["FTA"] - ep["OREB"] + ep["TOV"]
    ep = ep.sort_values(["fecha_utc", "evento", "equipo"]).reset_index(drop=True)
    return jp, ep


def cargar_tablas(temporadas: list[str], reconstruir: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tablas jugador-partido y equipo-partido, cacheadas en parquet."""
    clave = "_".join(temporadas)
    rj, re_ = TABLAS / f"jugadores_{clave}.parquet", TABLAS / f"equipos_{clave}.parquet"
    if rj.exists() and re_.exists() and not reconstruir:
        n_partidos = sum(len(list((CACHE_ESPN / t / "partidos").glob("*.json.gz"))) for t in temporadas)
        ep = pd.read_parquet(re_)
        if ep["evento"].nunique() >= n_partidos:
            return pd.read_parquet(rj), ep
    jp, ep = construir_tablas(temporadas)
    TABLAS.mkdir(parents=True, exist_ok=True)
    jp.to_parquet(rj, index=False)
    ep.to_parquet(re_, index=False)
    return jp, ep
