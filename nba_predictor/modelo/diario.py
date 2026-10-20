"""
Predicciones del día con el modelo de puntos.

El modelo se entrena una vez al día con toda la historia disponible y se
guarda en cache/modelos/: abrir el dashboard varias veces no lo reentrena.
"""

from __future__ import annotations

import pickle
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from nba_predictor.modelo import configuracion as cfg
from nba_predictor.modelo import factores as fx
from nba_predictor.modelo.puntos import ModeloPuntos

CACHE_MODELOS = Path("cache") / "modelos"

# Factores que se muestran junto a cada predicción para entender el porqué.
FACTORES_VISIBLES = ["pts_l10", "pts_temporada", "min_l10", "aus_pts", "estrella_fuera",
                     "rango_pts_hoy", "spread_equipo", "total_implicito", "partidos_perdidos"]


def modelo_del_dia(df_hist: pd.DataFrame, hoy: date, reentrenar: bool = False) -> ModeloPuntos:
    ruta = CACHE_MODELOS / f"{cfg.VERSION}_{hoy:%Y%m%d}.pkl"
    if ruta.exists() and not reentrenar:
        with open(ruta, "rb") as f:
            return pickle.load(f)
    modelo = ModeloPuntos(fx.columnas(cfg.GRUPOS), modo=cfg.MODO)
    modelo.entrenar(df_hist)
    CACHE_MODELOS.mkdir(parents=True, exist_ok=True)
    for viejo in CACHE_MODELOS.glob(f"{cfg.VERSION}_*.pkl"):
        viejo.unlink()
    with open(ruta, "wb") as f:
        pickle.dump(modelo, f)
    return modelo


def predecir(datos: dict, reentrenar: bool = False) -> tuple[pd.DataFrame, ModeloPuntos]:
    """
    Predicción de puntos para cada jugador de rotación que juega hoy.

    `datos` es la salida de nba_predictor.datos.hoy.datos_del_dia. Devuelve
    una fila por jugador con la media esperada, su dispersión y los factores
    que más pesan, y el modelo (para calcular la probabilidad de cualquier línea).
    """
    jp = pd.concat([datos["jp"], datos["jp_hoy"]], ignore_index=True)
    ep = pd.concat([datos["ep"], datos["ep_hoy"]], ignore_index=True)
    df = fx.construir(jp, ep)
    es_hoy = df["es_hoy"].fillna(False).astype(bool) if "es_hoy" in df else pd.Series(False, index=df.index)

    modelo = modelo_del_dia(df[~es_hoy & df["PTS"].notna()], datos["hoy"], reentrenar)
    hoy = df[es_hoy].copy()
    if hoy.empty:
        return hoy, modelo

    hoy["prediccion"] = modelo.predecir(hoy).round(1)
    hoy["sigma"] = modelo.sigma(hoy["prediccion"].to_numpy()).round(2)
    hoy["es_duda"] = hoy.get("es_duda", False)
    cols = ["jugador", "athlete_id", "equipo", "rival", "local", "posicion", "evento",
            "prediccion", "sigma", "es_duda", "estado_lesion"] + FACTORES_VISIBLES
    salida = hoy[[c for c in cols if c in hoy.columns]].sort_values("prediccion", ascending=False)
    return salida.reset_index(drop=True), modelo


def probabilidad(modelo: ModeloPuntos, prediccion: float, linea: float) -> tuple[float, float]:
    """(P over, P under) calibradas para una línea concreta."""
    p_over = float(modelo.prob_supera(np.array([prediccion]), np.array([linea]))[0])
    return p_over, 1 - p_over
