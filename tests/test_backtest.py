"""
Backtest walk-forward: lo crítico es que no haya leakage, que la línea
sintética sea la esperada y que un predictor que iguala la línea no invente
edge. Usa gamelogs sintéticos, no datos reales.
"""

import numpy as np
import pandas as pd
import pytest

import nba_predictor.backtest.walk_forward as bt


def gamelog_sintetico(n=40, seed=0):
    rng = np.random.default_rng(seed)
    fechas = pd.date_range('2025-11-01', periods=n, freq='2D')
    return pd.DataFrame({
        'GAME_DATE': fechas,
        'PTS': rng.integers(10, 35, n),
        'MIN_num': rng.integers(20, 38, n),
    })


@pytest.fixture
def cache_sintetico(monkeypatch):
    gl = gamelog_sintetico()
    monkeypatch.setattr(bt, 'cargar_gamelogs_cache',
                        lambda seasons: {'999_2025-26': gl.copy()})


def predictor_media_l5(historia):
    pts = pd.to_numeric(historia['PTS'], errors='coerce').dropna()
    if len(pts) < 5:
        return None
    return float(pts.tail(5).mean()), 5.0


def predictor_igual_linea(historia):
    # Misma media L10 que la línea sintética: no hay desviación, no hay edge.
    pts = pd.to_numeric(historia['PTS'], errors='coerce').dropna()
    if len(pts) < 5:
        return None
    return float(pts.tail(10).mean()), 6.0


def test_linea_sintetica_redondea_a_medio_punto():
    serie = pd.Series([20, 22, 24, 26, 28, 30, 21, 23, 25, 27])  # media 24.6
    assert bt.linea_sintetica(serie) == 24.5


def test_backtest_sin_leakage_genera_predicciones(cache_sintetico):
    # El assert anti-leakage vive dentro del backtest: si saltara, no habría 'df'.
    res = bt.backtest(predictor_media_l5, seasons=['2025-26'], split='todo',
                      min_historia=20, verbose=False)
    assert 'df' in res, res.get('error', '')
    assert res['resumen']['n_predicciones'] > 0
    mae = res['resumen']['mae']
    assert mae >= 0 and np.isfinite(mae)


def test_predictor_igual_a_la_linea_no_inventa_edge(cache_sintetico):
    res = bt.backtest(predictor_igual_linea, seasons=['2025-26'], split='todo',
                      min_historia=20, verbose=False)
    assert 'df' in res
    # La línea se redondea a .5, así que puede quedar una desviación mínima,
    # pero no debe producir picks ganadores de forma sistemática.
    r = res['resumen']
    assert r['n_picks'] == 0 or r['win_rate_pct'] < 60
