"""
Modelo de puntos por jugador y su probabilidad de superar una línea.

Tres formas de predecir, que se comparan en validación:
- "directo": un XGBoost que predice los puntos.
- "minutos": un XGBoost predice los minutos y otro los puntos por minuto;
  la predicción es su producto. Las ausencias, las palizas y el descanso
  actúan sobre todo a través de los minutos, y separarlos puede captarlo mejor.
- "mezcla": el promedio de las dos anteriores.

La probabilidad de superar la línea sale de una normal cuya dispersión crece
con la media (un anotador de 30 varía más que uno de 8), estimada con
residuos FUERA DE MUESTRA, y luego se recalibra con isotónica sobre esos
mismos residuos: así la probabilidad declarada coincide con la frecuencia real.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBRegressor

VERSION = "puntos-v2"

PARAMS_XGB = dict(
    n_estimators=500, learning_rate=0.03, max_depth=5, subsample=0.8,
    colsample_bytree=0.8, min_child_weight=20, reg_lambda=2.0,
    tree_method="hist", n_jobs=4, verbosity=0,
)

N_TRAMOS_OOF = 4          # tramos temporales para los residuos fuera de muestra
PROB_MIN, PROB_MAX = 0.02, 0.98


def _xgb(semilla: int = 42, **extra) -> XGBRegressor:
    return XGBRegressor(random_state=semilla, **{**PARAMS_XGB, **extra})


def linea_sintetica(pts_l10: pd.Series) -> pd.Series:
    """Línea ingenua: media de los últimos 10 partidos redondeada a .5,
    con el .5 obligatorio de las líneas reales (no hay empate)."""
    return np.floor(pts_l10) + 0.5


class ModeloPuntos:
    def __init__(self, features: list[str], modo: str = "directo", semilla: int = 42,
                 calibrar: bool = True):
        if modo not in ("directo", "minutos", "mezcla"):
            raise ValueError(modo)
        self.features = list(features)
        self.modo = modo
        self.semilla = semilla
        self.calibrar = calibrar
        self._modelos = {}
        self._sigma = (2.0, 0.25)      # sigma = a + b * media
        self._iso = None

    # ── Ajuste de la media ──
    def _ajustar_media(self, df: pd.DataFrame) -> dict:
        X = df[self.features]
        modelos = {}
        if self.modo in ("directo", "mezcla"):
            modelos["pts"] = _xgb(self.semilla)
            modelos["pts"].fit(X, df["PTS"])
        if self.modo == "directo":
            return modelos
        mins = _xgb(self.semilla)
        mins.fit(X, df["MIN"])
        ppm = _xgb(self.semilla + 1)
        # Puntos por minuto, ponderado por minutos: un partido de 4 minutos
        # dice poco sobre el ritmo de anotación.
        ppm.fit(X, df["PTS"] / df["MIN"].clip(lower=1), sample_weight=df["MIN"].clip(lower=1))
        return {**modelos, "min": mins, "ppm": ppm}

    @staticmethod
    def _predecir_media(modelos: dict, X: pd.DataFrame) -> np.ndarray:
        estimaciones = []
        if "pts" in modelos:
            estimaciones.append(modelos["pts"].predict(X))
        if "min" in modelos:
            estimaciones.append(modelos["min"].predict(X).clip(0, 48) * modelos["ppm"].predict(X).clip(0, 2))
        # En "mezcla" se promedian las dos vías: errores distintos se compensan.
        return np.clip(np.mean(estimaciones, axis=0), 0.5, None)

    # ── Entrenamiento completo ──
    def entrenar(self, df: pd.DataFrame, oof: bool = True) -> dict:
        """Ajusta la media y, con oof=True, la dispersión y la calibración.
        Sin oof es mucho más rápido: sirve para comparar errores de la media."""
        df = df.sort_values("fecha_utc")
        self._modelos = self._ajustar_media(df)
        if not oof:
            return {"n": len(df), "oof": 0}

        # Residuos fuera de muestra: cada tramo se predice con un modelo
        # entrenado solo con los tramos anteriores (como en producción).
        cortes = np.linspace(0, len(df), N_TRAMOS_OOF + 2).astype(int)
        mus, ys, lineas = [], [], []
        for t in range(1, N_TRAMOS_OOF + 1):
            entreno, prueba = df.iloc[:cortes[t]], df.iloc[cortes[t]:cortes[t + 1]]
            if len(entreno) < 2000 or prueba.empty:
                continue
            mods = self._ajustar_media(entreno)
            mus.append(self._predecir_media(mods, prueba[self.features]))
            ys.append(prueba["PTS"].to_numpy())
            lineas.append(linea_sintetica(prueba["pts_l10"]).to_numpy())
        if not mus:
            return {"n": len(df), "oof": 0}
        mu, y, lin = map(np.concatenate, (mus, ys, lineas))

        # Dispersión que crece con la media: E|e| = sigma * sqrt(2/pi).
        A = np.column_stack([np.ones_like(mu), mu])
        coef, *_ = np.linalg.lstsq(A, np.abs(y - mu) * np.sqrt(np.pi / 2), rcond=None)
        self._sigma = (max(coef[0], 1.0), max(coef[1], 0.05))

        if self.calibrar:
            # Isotónica sobre P(supera) cruda → frecuencia real, con varias
            # líneas por partido para cubrir todo el rango de probabilidades.
            ps, hits = [], []
            for desp in (-3, -1.5, 0, 1.5, 3):
                linea = lin + desp
                ps.append(self._prob_cruda(mu, linea))
                hits.append((y > linea).astype(float))
            self._iso = IsotonicRegression(y_min=PROB_MIN, y_max=PROB_MAX, out_of_bounds="clip")
            self._iso.fit(np.concatenate(ps), np.concatenate(hits))
        return {"n": len(df), "oof": len(mu), "mae_oof": float(np.mean(np.abs(y - mu))),
                "sigma": tuple(round(v, 3) for v in self._sigma)}

    # ── Predicción ──
    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        return self._predecir_media(self._modelos, df[self.features])

    def sigma(self, mu: np.ndarray) -> np.ndarray:
        a, b = self._sigma
        return a + b * np.asarray(mu)

    def _prob_cruda(self, mu, linea) -> np.ndarray:
        return norm.sf(np.asarray(linea), loc=mu, scale=self.sigma(mu))

    def prob_supera(self, mu, linea) -> np.ndarray:
        """P(puntos > línea) calibrada."""
        p = self._prob_cruda(mu, linea)
        if self._iso is not None:
            p = self._iso.predict(p)
        return np.clip(p, PROB_MIN, PROB_MAX)
