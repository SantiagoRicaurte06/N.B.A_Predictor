# ================================================
#  NBA PREDICTOR — MÓDULO 9: MODELO POOLED
#  Un solo modelo entrenado con MUCHOS jugadores a la
#  vez (miles de partidos-jugador), en vez de un modelo
#  diminuto por jugador. La identidad/forma del jugador
#  entra como features, no como partición. (ADR-002)
#
#  Emite media y una estimación de incertidumbre
#  (pred_sigma) empírica por bucket de minutos. (ADR-008)
#
#  Solo usa features REALES: se excluyen las fingidas
#  (usage_rate con TEAM_FGA×5, reb_rate por defaults,
#   opponent_pace circular, minutes_restriction sin
#   datos de lesión). DATA_SPEC §7.4.
#  Ref: PLAN Fase 2, TRD §6
# ================================================

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from module2_prediction_engine import build_player_features

FEATURES_VERSION = "pooled-v1"

# Features REALES (derivadas del propio box score del jugador o del contexto
# del partido). NADA de features fingidas (DATA_SPEC §7.4).
FEATURES = [
    'avg_PTS_L10', 'std_PTS_L10', 'avg_PTS_L5', 'trend_PTS',
    'avg_REB_L10', 'avg_AST_L10',
    'avg_MIN_num_L10', 'avg_FGA_L10', 'avg_FG3A_L10', 'avg_FTA_L10', 'avg_FG_PCT_L10',
    'is_home', 'win_rate_L10', 'rest_days', 'game_number', 'dd_rate_L10',
    'avg_pace_L10', 'is_b2b', 'b2b_last_5',
]
TARGET = 'PTS'


class ModeloPooled:
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.modelo = None
        self.sigma_buckets = None   # (edges, sigmas) por avg_MIN_num_L10
        self.sigma_global = 6.0
        self._feat_cache = {}       # cache de features por gamelog (perf)

    # ── Construcción del dataset pooled ──
    def _features_de_gamelog(self, gl: pd.DataFrame) -> pd.DataFrame:
        feats = build_player_features(gl.copy())
        cols = [c for c in FEATURES if c in feats.columns]
        feats = feats[cols + [TARGET, 'GAME_DATE']].copy()
        return feats

    def construir_dataset(self, gamelogs: dict, cutoff_date) -> pd.DataFrame:
        """Apila (features, PTS) de todos los jugadores para partidos con fecha < cutoff."""
        piezas = []
        for key, gl in gamelogs.items():
            try:
                feats = self._features_de_gamelog(gl)
            except Exception:
                continue
            feats = feats[feats['GAME_DATE'] < cutoff_date]
            piezas.append(feats)
        if not piezas:
            return pd.DataFrame()
        data = pd.concat(piezas, ignore_index=True)
        cols = [c for c in FEATURES if c in data.columns]
        data = data.dropna(subset=cols + [TARGET])
        return data

    # ── Entrenamiento ──
    def entrenar(self, gamelogs: dict, cutoff_date) -> dict:
        data = self.construir_dataset(gamelogs, cutoff_date)
        if len(data) < 500:
            raise ValueError(f"Dataset pooled muy pequeño ({len(data)} filas)")

        cols = [c for c in FEATURES if c in data.columns]
        X = data[cols].values
        y = data[TARGET].values

        self.modelo = XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=4,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            reg_lambda=1.0, random_state=self.random_state, verbosity=0,
        )
        self.modelo.fit(X, y)
        self._cols = cols

        # Sigma empírico por bucket de minutos (ADR-008): residuos in-sample,
        # segmentados por terciles de avg_MIN_num_L10.
        preds = self.modelo.predict(X)
        resid = y - preds
        min_col = data['avg_MIN_num_L10'].values
        self.sigma_global = float(np.std(resid))
        try:
            edges = np.quantile(min_col, [1/3, 2/3])
            sigmas = []
            grupos = [min_col <= edges[0],
                      (min_col > edges[0]) & (min_col <= edges[1]),
                      min_col > edges[1]]
            for g in grupos:
                s = float(np.std(resid[g])) if g.sum() > 20 else self.sigma_global
                sigmas.append(max(s, 3.0))
            self.sigma_buckets = (edges, sigmas)
        except Exception:
            self.sigma_buckets = None

        return {"n_filas": len(data), "n_features": len(cols),
                "sigma_global": round(self.sigma_global, 2)}

    def _sigma_para(self, avg_min: float) -> float:
        if self.sigma_buckets is None or not np.isfinite(avg_min):
            return max(self.sigma_global, 3.0)
        edges, sigmas = self.sigma_buckets
        if avg_min <= edges[0]:
            return sigmas[0]
        if avg_min <= edges[1]:
            return sigmas[1]
        return sigmas[2]

    # ── Predicción (interfaz del backtest: (key, i, historia) -> (media, sigma)) ──
    def predict_for(self, key: str, i: int, historia: pd.DataFrame):
        """
        Predice el próximo partido usando la última fila de features de la
        historia (misma convención que el modelo baseline, para comparar justo).
        """
        if self.modelo is None:
            return None
        try:
            feats = build_player_features(historia.copy())
        except Exception:
            return None
        cols = self._cols
        fila = feats[cols].dropna().tail(1)
        if fila.empty:
            return None
        media = float(self.modelo.predict(fila.values)[0])
        avg_min = float(fila['avg_MIN_num_L10'].iloc[0]) if 'avg_MIN_num_L10' in fila else np.nan
        sigma = self._sigma_para(avg_min)
        if media <= 0:
            return None
        return media, sigma


# ─────────────────────────────────────────────
# FLUJO DIARIO — predicciones con el pooled
# ─────────────────────────────────────────────

def generar_predicciones_pooled(datos: dict, modelo: "ModeloPooled | None" = None,
                                 seasons=("2024-25", "2025-26")):
    """
    Genera las predicciones PTS del día con el modelo pooled, en el formato que
    espera module3.generar_stakes. Entrena el pooled sobre TODO el histórico
    cacheado (si no se pasa un modelo ya entrenado) y predice para los jugadores
    de hoy. Retorna (predicciones, modelo) para poder reutilizar el modelo.
    Ref: PLAN Fase 2.3.
    """
    import module7_backtest_engine as bt

    if modelo is None:
        gamelogs_hist = bt.cargar_gamelogs_cache(list(seasons))
        modelo = ModeloPooled()
        # cutoff en el futuro → entrena con todo lo disponible (predicción en vivo)
        modelo.entrenar(gamelogs_hist, cutoff_date=pd.Timestamp('2100-01-01'))

    predicciones = []
    for j in datos.get('jugadores_hoy', []):
        if not j.get('disponible', True):
            continue
        nombre = j['nombre']
        gl = datos.get('gamelogs', {}).get(nombre)
        if gl is None or len(gl) < 10:
            continue
        pred = modelo.predict_for(nombre, len(gl), gl)
        if pred is None:
            continue
        media, sigma = pred
        avg_hist = float(pd.to_numeric(gl['PTS'], errors='coerce').tail(10).mean())
        predicciones.append({
            'jugador':       nombre,
            'target':        'PTS',
            'prediccion':    round(media, 1),
            'pred_media':    round(media, 1),
            'pred_sigma':    round(sigma, 2),
            'avg_historico': round(avg_hist, 1),
            'mae':           round(sigma, 2),          # aproximación para la UI
            'std_historico': round(sigma, 2),
            'confianza':     'MEDIA',
            'es_gtd':        j.get('es_gtd', False),
            'features_version': FEATURES_VERSION,
        })

    print(f"  ✅ {len(predicciones)} predicciones pooled generadas")
    return predicciones, modelo


if __name__ == "__main__":
    print("Módulo 9 — Modelo pooled multi-jugador (ADR-002)")
    print(f"Features ({len(FEATURES)}): {FEATURES}")
