# ================================================
#  NBA PREDICTOR — BASELINE: MODELO POR JUGADOR
#  Un XGBoost diminuto por jugador. Era el modelo
#  original; hoy solo sirve de referencia en el
#  backtest para medir si el pooled lo supera.
# ================================================

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor

from nba_predictor.modelo.features import (
    VENTANA,
    build_player_features,
    get_feature_cols_props,
)

MIN_JUEGOS = 5     # mínimo para entrenar


def entrenar_modelo_props(df: pd.DataFrame, target: str) -> dict | None:
    """
    Entrena modelo XGBoost para predecir una stat individual.
    Retorna dict con modelo, MAE, y metadata.
    """
    df = build_player_features(df)
    feature_cols = [c for c in get_feature_cols_props(target) if c in df.columns]

    df_clean = df[feature_cols + [target]].dropna()

    if len(df_clean) < MIN_JUEGOS:
        return None

    X = df_clean[feature_cols]
    y = df_clean[target]

    modelo = XGBRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        random_state=42,
        verbosity=0
    )

    # Walk-forward validation
    tscv = TimeSeriesSplit(n_splits=3)
    maes = []

    for train_idx, test_idx in tscv.split(X):
        if len(test_idx) < 2:
            continue
        modelo.fit(X.iloc[train_idx], y.iloc[train_idx], verbose=False)
        preds = modelo.predict(X.iloc[test_idx])
        maes.append(mean_absolute_error(y.iloc[test_idx], preds))

    # Entrenar final con todos los datos
    modelo.fit(X, y, verbose=False)

    # Predicción del próximo partido (usando la última fila disponible)
    ultima = df[feature_cols].dropna().tail(1)
    if ultima.empty:
        return None

    prediccion = float(modelo.predict(ultima)[0])
    if prediccion <= 0.5:
        return None

    # Stats históricas para contexto
    avg_historico = float(y.tail(VENTANA).mean())
    std_historico = float(y.tail(VENTANA).std())

    # Validación de outlier: si predicción > 150% del promedio histórico, limitar al 120%
    if avg_historico > 0 and prediccion > 1.5 * avg_historico:
        prediccion_original = prediccion
        prediccion = 1.2 * avg_historico
        print(f"\n  ⚠️  WARNING: Predicción outlier detectada para {target}")
        print(f"      Predicción original: {prediccion_original:.1f}")
        print(f"      Promedio histórico: {avg_historico:.1f}")
        print(f"      Predicción ajustada: {prediccion:.1f} (120% del promedio)\n")

    mae = float(np.mean(maes)) if maes else float(mean_absolute_error(y, modelo.predict(X)))

    return {
        'modelo': modelo,
        'target': target,
        'prediccion': round(prediccion, 1),
        'mae': round(mae, 2),
        'avg_historico': round(avg_historico, 1),
        'std_historico': round(std_historico, 2),
        'n_juegos': len(df_clean),
        'feature_cols': feature_cols,
        'confianza': calcular_confianza_props(mae, std_historico)
    }


def calcular_confianza_props(mae: float, std: float) -> str:
    """Calcula nivel de confianza basado en error relativo al spread."""
    if std == 0:
        return 'BAJA'
    ratio = mae / std
    if ratio < 0.5:
        return 'ALTA'
    elif ratio < 0.75:
        return 'MEDIA'
    else:
        return 'BAJA'
