"""
Factores del modelo. Lo crítico: ningún factor puede usar el propio partido
ni partidos posteriores; si lo hiciera, el backtest prometería un edge falso.
"""

import numpy as np
import pandas as pd
import pytest

from nba_predictor.datos.arenas import distancia_km
from nba_predictor.datos.boxscore import _parsear_stats, filas_de_partido
from nba_predictor.modelo import factores as fx

EQUIPOS = ["BOS", "NY", "LAL", "GS"]


def temporada_sintetica(n_fechas=40, seed=0, temporada="2024-25"):
    """Dos partidos por fecha entre cuatro equipos, 9 jugadores por equipo."""
    rng = np.random.default_rng(seed)
    jugadores, equipos = [], []
    for d in range(n_fechas):
        fecha = pd.Timestamp("2024-11-01") + pd.Timedelta(days=2 * d)
        cruces = [("BOS", "NY"), ("LAL", "GS")] if d % 2 else [("BOS", "LAL"), ("NY", "GS")]
        for k, (loc, vis) in enumerate(cruces):
            evento = f"{d:03d}{k}"
            pts = {}
            for eq, es_local in ((loc, True), (vis, False)):
                total = 0
                for j in range(9):
                    no_jugo = (eq == "BOS" and j == 0 and d % 7 == 3)   # la estrella falta a veces
                    p = 0 if no_jugo else int(rng.poisson(28 - 3 * j if j < 8 else 2))
                    total += p
                    jugadores.append({
                        "temporada": temporada, "evento": evento, "fecha": fecha,
                        "fecha_utc": fecha + pd.Timedelta(hours=23 + k), "tipo": 2,
                        "neutral": False, "equipo": eq, "rival": vis if eq == loc else loc,
                        "local": es_local, "athlete_id": f"{eq}{j}", "jugador": f"{eq} {j}",
                        "posicion": "GFC"[j % 3], "titular": j < 5, "no_jugo": no_jugo,
                        "motivo": "LESION" if no_jugo else "", "expulsado": False,
                        "MIN": np.nan if no_jugo else 36 - 3 * j, "PTS": np.nan if no_jugo else p,
                        "FGM": 5, "FGA": 12 - j, "FG3M": 1, "FG3A": 4, "FTM": 2, "FTA": 3,
                        "OREB": 1, "DREB": 3, "REB": 4, "AST": 2, "STL": 1, "BLK": 0,
                        "TOV": 2, "PF": 2, "PLUS_MINUS": 0,
                    })
                pts[eq] = total
            for eq, es_local in ((loc, True), (vis, False)):
                riv = vis if eq == loc else loc
                equipos.append({
                    "temporada": temporada, "evento": evento, "fecha": fecha,
                    "fecha_utc": fecha + pd.Timedelta(hours=23 + k), "tipo": 2, "neutral": False,
                    "equipo": eq, "rival": riv, "local": es_local, "pts": pts[eq],
                    "pts_rival": pts[riv], "FGM": 40, "FGA": 88, "FG3M": 12, "FG3A": 35,
                    "FTM": 15, "FTA": 20, "OREB": 10, "TOV": 13,
                    "spread_equipo": -3.0 if es_local else 3.0, "total_linea": 225.0,
                    "posesiones": 88 + 0.44 * 20 - 10 + 13,
                })
    return pd.DataFrame(jugadores), pd.DataFrame(equipos)


@pytest.fixture(scope="module")
def tablas():
    return temporada_sintetica()


def test_construye_filas_con_todos_los_factores(tablas):
    df = fx.construir(*tablas)
    assert len(df) > 100
    faltan = [c for c in fx.columnas(list(fx.GRUPOS)) if c not in df.columns]
    assert faltan == []


def test_ningun_factor_mira_el_propio_partido_ni_el_futuro(tablas):
    jp, ep = tablas
    base = fx.construir(jp, ep)
    ultimo = jp["fecha_utc"].max()

    # Cambiar el resultado del último partido no puede mover sus factores.
    jp2 = jp.copy()
    mask = (jp2["fecha_utc"] == ultimo) & ~jp2["no_jugo"]
    jp2.loc[mask, "PTS"] = jp2.loc[mask, "PTS"] + 25
    jp2.loc[mask, "MIN"] = jp2.loc[mask, "MIN"] - 10
    ep2 = ep.copy()
    ep2.loc[ep2["fecha_utc"] == ultimo, "pts"] += 60
    alterado = fx.construir(jp2, ep2)

    cols = fx.columnas(list(fx.GRUPOS))
    a = base[base["fecha_utc"] == ultimo].set_index("athlete_id")[cols].sort_index()
    b = alterado[alterado["fecha_utc"] == ultimo].set_index("athlete_id")[cols].sort_index()
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)


def test_ausencia_de_la_estrella_se_detecta(tablas):
    df = fx.construir(*tablas)
    bos = df[df["equipo"] == "BOS"]
    falta = bos.groupby("evento")["estrella_fuera"].first()
    # La estrella de BOS falta cada 7 fechas: algunos partidos tienen que marcarlo.
    assert falta.sum() >= 2
    # Y sus compañeros ven más puntos libres esos días.
    con = bos[bos["estrella_fuera"] == 1]["aus_pts"].mean()
    assert con > 15


def test_parseo_de_stats_parte_anotados_e_intentos():
    fila = _parsear_stats(["MIN", "PTS", "FG", "3PT", "+/-"], ["34", "27", "10-19", "3-8", "+12"])
    assert fila == {"MIN": 34.0, "PTS": 27.0, "FGM": 10.0, "FGA": 19.0,
                    "FG3M": 3.0, "FG3A": 8.0, "PLUS_MINUS": 12.0}


def test_filas_de_partido_lee_un_resumen_de_espn():
    resumen = {
        "header": {"season": {"type": 2}, "competitions": [{
            "date": "2025-01-16T00:30Z", "neutralSite": False,
            "competitors": [
                {"homeAway": "home", "score": "110", "team": {"abbreviation": "PHI", "id": "20"}},
                {"homeAway": "away", "score": "100", "team": {"abbreviation": "NY", "id": "18"}}]}]},
        "boxscore": {"players": [{"team": {"abbreviation": "NY"}, "statistics": [{
            "labels": ["MIN", "PTS", "FG"],
            "athletes": [
                {"athlete": {"id": "1", "displayName": "A", "position": {"abbreviation": "G"}},
                 "starter": True, "didNotPlay": False, "stats": ["40", "30", "11-20"]},
                {"athlete": {"id": "2", "displayName": "B", "position": {"abbreviation": "C"}},
                 "starter": False, "didNotPlay": True, "reason": "SPRAINED ANKLE", "stats": []}]}]}],
            "teams": []},
    }
    jugadores, _ = filas_de_partido(resumen, "2024-25", "1")
    a, b = jugadores
    # 00:30 UTC del 16 es la noche del 15 en la costa este.
    assert a["fecha"] == pd.Timestamp("2025-01-15")
    assert a["PTS"] == 30 and a["rival"] == "PHI" and a["local"] is False
    assert b["no_jugo"] and b["motivo"] == "SPRAINED ANKLE"


def test_distancia_entre_arenas():
    assert distancia_km("BOS", "BOS") == 0
    assert 3900 < distancia_km("NY", "LAL") < 4000
