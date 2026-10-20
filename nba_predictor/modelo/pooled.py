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

from nba_predictor.modelo.features import build_player_features

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

# Nº de tramos temporales para estimar la sigma fuera de muestra.
# 5 tramos = 4 reentrenamientos extra; sobre ~33k filas cuesta segundos.
N_TRAMOS_SIGMA = 5
MIN_FILAS_OOF = 2000    # por debajo de esto, los tramos quedan demasiado flacos

# Puntos de la rejilla con la que se guarda la distribución empírica del error.
# 201 cuantiles bastan para reconstruir la CDF con precisión de medio punto
# porcentual, y ocupan nada.
N_CUANTILES = 201
MIN_RESID_BUCKET = 300  # menos que esto y la cola no es fiable: se usa la global

# La probabilidad nunca se deja llegar a 0 o 1: aunque la muestra no contenga
# ningún caso extremo, eso no significa que sea imposible.
PROB_MIN, PROB_MAX = 0.02, 0.98


class ModeloPooled:
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.modelo = None
        self.sigma_buckets = None   # (edges, sigmas) por avg_MIN_num_L10
        self.sigma_global = 6.0
        # Rejilla de cuantiles de los residuos out-of-fold, por bucket de
        # minutos. Es la distribución REAL del error, sin suponer normalidad.
        self.resid_q = None         # (edges, [q_bajo, q_medio, q_alto])
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

    def _nuevo_estimador(self) -> XGBRegressor:
        """Los hiperparámetros viven en un solo sitio: el modelo final y los
        tramos que estiman la sigma tienen que ser el MISMO modelo, o la sigma
        mediría la dispersión de otra cosa."""
        return XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=4,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            reg_lambda=1.0, random_state=self.random_state, verbosity=0,
        )

    def _residuos_fuera_de_muestra(self, X, y, fechas):
        """
        Residuos out-of-fold por ventana temporal expansiva.

        POR QUÉ EXISTE ESTA FUNCIÓN
        ---------------------------
        Antes la sigma salía de los residuos IN-SAMPLE, es decir del error del
        modelo sobre los datos con los que ya se había entrenado. XGBoost ajusta
        muy fino su propio entrenamiento, así que ese error es artificialmente
        pequeño. Medido en el backtest: sigma declarada 5.99 contra 6.42 real,
        un 7 % baja.

        Como `prob = Φ((media − línea) / sigma)`, una sigma corta infla TODAS las
        probabilidades. De ahí salía que el modelo declarara un 72.6 % y acertara
        un 59.1 %: no es que fallara la predicción, es que mentía la confianza.

        Aquí los datos se ordenan por fecha y se parten en tramos: cada tramo se
        predice con un modelo entrenado SOLO con lo anterior. Es el mismo error
        que se verá en producción, que es justo lo que la sigma debe medir.

        Devuelve un vector alineado con las filas de entrada (NaN en el primer
        tramo, que no tiene pasado con el que predecirse), o None si no hay
        datos suficientes.
        """
        n = len(y)
        if n < MIN_FILAS_OOF:
            return None

        orden = np.argsort(fechas, kind='stable')
        Xo, yo = X[orden], y[orden]

        cortes = np.linspace(0, n, N_TRAMOS_SIGMA + 1).astype(int)
        resid_ord = np.full(n, np.nan)

        for t in range(1, N_TRAMOS_SIGMA):
            fin_train = cortes[t]
            ini_test, fin_test = cortes[t], cortes[t + 1]
            if fin_train < 500 or fin_test <= ini_test:
                continue
            m = self._nuevo_estimador()
            m.fit(Xo[:fin_train], yo[:fin_train])
            resid_ord[ini_test:fin_test] = (
                yo[ini_test:fin_test] - m.predict(Xo[ini_test:fin_test])
            )

        # Deshacer la ordenación para volver al orden original de las filas.
        resid = np.full(n, np.nan)
        resid[orden] = resid_ord
        return resid if np.isfinite(resid).sum() >= 500 else None

    # ── Entrenamiento ──
    def entrenar(self, gamelogs: dict, cutoff_date) -> dict:
        data = self.construir_dataset(gamelogs, cutoff_date)
        if len(data) < 500:
            raise ValueError(f"Dataset pooled muy pequeño ({len(data)} filas)")

        cols = [c for c in FEATURES if c in data.columns]
        X = data[cols].values
        y = data[TARGET].values

        self.modelo = self._nuevo_estimador()
        self.modelo.fit(X, y)
        self._cols = cols

        # Sigma empírica por bucket de minutos (ADR-008), a partir de residuos
        # FUERA DE MUESTRA. Si no se pueden calcular, se cae a los in-sample
        # avisando: son optimistas y hay que saber que se están usando.
        min_col_todo = data['avg_MIN_num_L10'].values
        resid_oof = self._residuos_fuera_de_muestra(X, y, data['GAME_DATE'].values)

        if resid_oof is not None:
            usable = np.isfinite(resid_oof)
            resid = resid_oof[usable]
            min_col = min_col_todo[usable]
            metodo = "out-of-fold"
        else:
            resid = y - self.modelo.predict(X)
            min_col = min_col_todo
            metodo = "in-sample (FALLBACK: sigma optimista)"

        self.sigma_global = float(np.std(resid))
        probs = np.linspace(0, 1, N_CUANTILES)
        q_global = np.quantile(resid, probs)
        try:
            edges = np.quantile(min_col, [1/3, 2/3])
            sigmas, cuantiles = [], []
            grupos = [min_col <= edges[0],
                      (min_col > edges[0]) & (min_col <= edges[1]),
                      min_col > edges[1]]
            for g in grupos:
                s = float(np.std(resid[g])) if g.sum() > 20 else self.sigma_global
                sigmas.append(max(s, 3.0))
                # La distribución empírica necesita bastante más muestra que la
                # desviación: una cola mal estimada envenena justo los picks de
                # alta confianza, que es donde se juega todo.
                cuantiles.append(np.quantile(resid[g], probs)
                                 if g.sum() >= MIN_RESID_BUCKET else q_global)
            self.sigma_buckets = (edges, sigmas)
            self.resid_q = (edges, cuantiles)
        except Exception:
            self.sigma_buckets = None
            self.resid_q = None

        self._q_global = q_global
        asim = float(pd.Series(resid).skew())

        return {"n_filas": len(data), "n_features": len(cols),
                "sigma_global": round(self.sigma_global, 2),
                "sigma_metodo": metodo, "n_resid": int(len(resid)),
                "asimetria_resid": round(asim, 3)}

    # ── Probabilidad SIN suponer normalidad ──
    def _cuantiles_para(self, avg_min: float):
        if self.resid_q is None or not np.isfinite(avg_min):
            return getattr(self, "_q_global", None)
        edges, cuantiles = self.resid_q
        if avg_min <= edges[0]:
            return cuantiles[0]
        if avg_min <= edges[1]:
            return cuantiles[1]
        return cuantiles[2]

    def prob_supera(self, media: float, linea: float, avg_min: float) -> float | None:
        """
        P(puntos reales > línea), leída de la distribución EMPÍRICA del error.

        POR QUÉ NO SE USA UNA NORMAL
        ----------------------------
        El resto del sistema calcula `prob = Φ((media − línea) / sigma)`. Eso
        supone que el error se reparte de forma simétrica, y no es el caso: los
        puntos anotados tienen cola derecha (un jugador puede explotar a 40, no
        puede bajar de 0). Una normal sobre una distribución sesgada exagera las
        colas — justo donde viven los picks de alta confianza.

        Aquí, en vez de suponer la forma, se usa la que se midió:
            actual = media + residuo   →   P(actual > línea) = P(residuo > línea − media)
        que sobre la muestra de residuos es contar qué fracción la supera.
        """
        q = self._cuantiles_para(avg_min)
        if q is None or len(q) == 0:
            return None
        p = float(np.mean(q > (linea - media)))
        return min(max(p, PROB_MIN), PROB_MAX)

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
    import nba_predictor.backtest.walk_forward as bt

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
