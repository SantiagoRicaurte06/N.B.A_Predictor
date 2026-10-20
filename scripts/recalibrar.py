"""
Recalibración del modelo de puntos con los datos de ESPN.

    python scripts/recalibrar.py              # validación: 2023-24 y 2024-25
    python scripts/recalibrar.py --holdout    # + la medición única de 2025-26

1. Construye los factores de las cinco temporadas descargadas.
2. Predice las temporadas de validación con reentreno mensual y la
   configuración de nba_predictor/modelo/configuracion.py.
3. Elige, solo con validación, el umbral de probabilidad con mejor ROI que
   da al menos 10 picks por semana.
4. Con --holdout, predice 2025-26 con todo congelado y lo reporta tal cual.

Escribe docs/RECALIBRACION.md (o su sección de holdout) con los números.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nba_predictor.backtest import temporadas as bt
from nba_predictor.datos.boxscore import cargar_tablas
from nba_predictor.datos.hoy import TEMPORADAS_HISTORICAS
from nba_predictor.modelo import configuracion as cfg
from nba_predictor.modelo import factores as fx

SALIDA = Path("cache") / "espn" / "tablas"
RESULTADOS = Path("docs") / "resultados_recalibracion.json"


def _pct(x):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.1f} %"


def evaluar(pred: pd.DataFrame, umbrales: dict | None = None) -> dict:
    out = {"error": bt.error(pred), "lineas": {}}
    semanas = pred["semana"].nunique()
    for linea in ("ingenua", "informada"):
        if umbrales is None:
            u, r = bt.mejor_umbral(pred, linea, cfg.MIN_PICKS_SEMANA)
        else:
            u = umbrales[linea]
            r = bt.resumen_apuestas(bt.apuestas(pred, linea, u), semanas)
        cal = bt.calibracion(pred, linea)
        out["lineas"][linea] = {
            "umbral": u, **r,
            "calibracion": cal.assign(tramo=cal["tramo"].astype(str)).to_dict("records"),
            "por_umbral": {f"{x:.2f}": bt.resumen_apuestas(bt.apuestas(pred, linea, x), semanas)
                           for x in (0.55, 0.60, 0.65, 0.70)},
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true", help="medir 2025-26 (una sola vez)")
    args = ap.parse_args()

    jp, ep = cargar_tablas(TEMPORADAS_HISTORICAS)
    df = fx.construir(jp, ep)
    feats = fx.columnas(cfg.GRUPOS)
    print(f"{len(df)} filas, {len(feats)} factores, modo {cfg.MODO}")

    resultados = json.loads(RESULTADOS.read_text()) if RESULTADOS.exists() else {}

    pred_val = pd.concat([bt.predecir_temporada(df, t, feats, cfg.MODO) for t in bt.VALIDACION])
    pred_val.to_parquet(SALIDA / "pred_validacion.parquet")
    val = evaluar(pred_val)
    resultados["validacion"] = val
    resultados["configuracion"] = {"grupos": cfg.GRUPOS, "modo": cfg.MODO, "version": cfg.VERSION}
    print(json.dumps({k: v for k, v in val["lineas"]["informada"].items() if k != "calibracion"}, indent=1))

    if args.holdout:
        umbrales = {l: val["lineas"][l]["umbral"] for l in val["lineas"]}
        pred_h = bt.predecir_temporada(df, bt.HOLDOUT, feats, cfg.MODO)
        pred_h.to_parquet(SALIDA / "pred_holdout.parquet")
        resultados["holdout"] = evaluar(pred_h, umbrales)
        print(json.dumps({k: v for k, v in resultados["holdout"]["lineas"]["informada"].items()
                          if k != "calibracion"}, indent=1))

    RESULTADOS.write_text(json.dumps(resultados, indent=1, default=float))
    print(f"resultados en {RESULTADOS}")


if __name__ == "__main__":
    main()
