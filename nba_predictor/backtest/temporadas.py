"""
Backtest por temporadas sobre la tabla de factores.

Protocolo (acordado antes de mirar resultados):
- Se ajusta y se eligen factores y umbrales SOLO con las temporadas de
  validación (2023-24 y 2024-25), cada una predicha con un modelo entrenado
  con todo lo anterior.
- 2025-26 es el holdout: se predice UNA vez, al final, con la configuración
  ya congelada. No se vuelve a tocar nada después de verlo.
- Dentro de cada temporada el modelo se reentrena al inicio de cada mes con
  todo lo ocurrido antes, como se haría en producción.

Las apuestas se simulan contra dos líneas, ambas conocidas antes del partido
y puestas en la MEDIANA esperada, como hacen las casas para que over y under
salgan parejos. (Con líneas en la media, la cola derecha de los puntos hacía
ganar al under el 54 % de las veces sin mérito del modelo.)
- ingenua: mediana de los últimos 10 partidos.
- informada: regresión de mediana con forma, minutos, ausencias del equipo y
  el total implícito. Imita a una casa que ajusta por lesiones; ganarle a esta
  es lo que da algo de credibilidad al edge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import QuantileRegressor

from nba_predictor.modelo.puntos import ModeloPuntos, linea_sintetica

VALIDACION = ["2023-24", "2024-25"]
HOLDOUT = "2025-26"
CUOTA = 1.87                       # cuota típica de props en Betano
BREAK_EVEN = 1 / CUOTA             # 53.5 %

FEATS_LINEA_INFORMADA = ["pts_l10", "pts_l20", "pts_temporada", "min_l10", "aus_frac_pts",
                         "cuota_pts", "total_implicito", "local", "b2b"]


def _x_informada(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATS_LINEA_INFORMADA].copy()
    X["pts_temporada"] = X["pts_temporada"].fillna(X["pts_l20"])
    X["cuota_pts"] = X["cuota_pts"].fillna(X["cuota_pts"].median())
    X["total_implicito"] = X["total_implicito"].fillna(113.0)
    return X.fillna(0)


def linea_informada(entreno: pd.DataFrame, prueba: pd.DataFrame, n_muestra: int = 20000) -> np.ndarray:
    """Mediana condicional lineal. Se ajusta sobre una muestra: la regresión
    cuantílica es un problema lineal grande y 20 000 filas bastan para 9 factores."""
    muestra = entreno.sample(min(n_muestra, len(entreno)), random_state=0)
    r = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs")
    r.fit(_x_informada(muestra), muestra["PTS"])
    return np.floor(r.predict(_x_informada(prueba))) + 0.5


def predecir_temporada(df: pd.DataFrame, temporada: str, features: list[str], modo: str = "directo",
                       mensual: bool = True, calibrar: bool = True) -> pd.DataFrame:
    """Predicciones de una temporada con reentrenos sin mirar el futuro."""
    prueba_total = df[df["temporada"] == temporada]
    if mensual:
        bloques = [g for _, g in prueba_total.groupby(prueba_total["fecha"].dt.to_period("M"))]
    else:
        bloques = [prueba_total]

    salida = []
    for bloque in bloques:
        inicio = bloque["fecha_utc"].min()
        entreno = df[df["fecha_utc"] < inicio]
        modelo = ModeloPuntos(features, modo=modo, calibrar=calibrar)
        modelo.entrenar(entreno, oof=calibrar)
        mu = modelo.predecir(bloque)
        out = bloque[["evento", "fecha", "semana", "temporada", "athlete_id", "jugador",
                      "equipo", "PTS", "MIN", "pts_l10"]].copy()
        out["mu"] = mu
        out["linea_ingenua"] = linea_sintetica(bloque["pts_mediana_l10"]).to_numpy()
        out["linea_informada"] = linea_informada(entreno, bloque)
        if calibrar:
            for nombre in ("ingenua", "informada"):
                out[f"p_over_{nombre}"] = modelo.prob_supera(mu, out[f"linea_{nombre}"].to_numpy())
        salida.append(out)
    return pd.concat(salida, ignore_index=True)


# ─────────────────────────────────────────────
# Métricas
# ─────────────────────────────────────────────

def error(pred: pd.DataFrame) -> dict:
    e = pred["PTS"] - pred["mu"]
    return {"n": len(pred), "mae": float(e.abs().mean()), "sesgo": float(e.mean()),
            "mae_ingenua": float((pred["PTS"] - pred["pts_l10"]).abs().mean())}


def apuestas(pred: pd.DataFrame, linea: str, umbral: float) -> pd.DataFrame:
    """Picks con prob >= umbral contra la línea dada, al lado más probable."""
    p_over = pred[f"p_over_{linea}"]
    l = pred[f"linea_{linea}"]
    lado_over = p_over >= 0.5
    prob = np.where(lado_over, p_over, 1 - p_over)
    picks = pred.assign(lado=np.where(lado_over, "OVER", "UNDER"), prob=prob, linea=l)
    picks = picks[picks["prob"] >= umbral].copy()
    picks["gana"] = np.where(picks["lado"] == "OVER", picks["PTS"] > picks["linea"],
                             picks["PTS"] < picks["linea"])
    return picks


def resumen_apuestas(picks: pd.DataFrame, semanas: int) -> dict:
    n = len(picks)
    if n == 0:
        return {"picks": 0, "picks_semana": 0.0, "acierto": np.nan, "roi": np.nan}
    g = picks["gana"].mean()
    return {"picks": n, "picks_semana": n / max(semanas, 1), "acierto": float(g),
            "roi": float(g * (CUOTA - 1) - (1 - g))}


def calibracion(pred: pd.DataFrame, linea: str, cortes=(0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 1.0)) -> pd.DataFrame:
    """Probabilidad declarada vs acierto real, por tramos, al lado elegido."""
    picks = apuestas(pred, linea, 0.5)
    picks["tramo"] = pd.cut(picks["prob"], list(cortes), right=False)
    return picks.groupby("tramo", observed=True).agg(
        n=("gana", "size"), declarada=("prob", "mean"), real=("gana", "mean")).reset_index()


def mejor_umbral(pred: pd.DataFrame, linea: str, min_picks_semana: float = 10.0,
                 candidatos=np.arange(0.54, 0.80, 0.01)) -> tuple[float, dict]:
    """Umbral de probabilidad con mejor ROI que aún da el mínimo de picks por semana."""
    semanas = pred["semana"].nunique()
    mejor = (None, {"roi": -np.inf})
    for u in candidatos:
        r = resumen_apuestas(apuestas(pred, linea, u), semanas)
        if r["picks_semana"] >= min_picks_semana and r["roi"] > mejor[1]["roi"]:
            mejor = (round(float(u), 2), r)
    return mejor
