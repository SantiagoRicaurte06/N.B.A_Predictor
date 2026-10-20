"""
Pipeline con datos simulados: features → modelo por jugador → pick con stake.
Comprueba sobre todo que el lado del pick (OVER/UNDER) siga a la predicción.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from nba_predictor.apuestas.stakes import (
    analizar_pick_prop,
    calcular_edge,
    kelly_criterion,
)
from nba_predictor.modelo.baseline import entrenar_modelo_props
from nba_predictor.modelo.features import (
    build_player_features,
    detectar_back_to_back,
)


@pytest.fixture
def gamelog():
    rng = np.random.default_rng(42)
    n = 20
    return pd.DataFrame({
        'GAME_DATE': pd.date_range(end=datetime(2026, 3, 1), periods=n, freq='2D'),
        'PTS': rng.integers(15, 35, n),
        'REB': rng.integers(5, 15, n),
        'AST': rng.integers(3, 12, n),
        'STL': rng.integers(0, 3, n),
        'BLK': rng.integers(0, 3, n),
        'TOV': rng.integers(1, 5, n),
        'FGA': rng.integers(10, 25, n),
        'FGM': rng.integers(5, 15, n),
        'FG3A': rng.integers(2, 10, n),
        'FG3M': rng.integers(1, 5, n),
        'FTA': rng.integers(3, 10, n),
        'FTM': rng.integers(2, 8, n),
        'OREB': rng.integers(1, 5, n),
        'DREB': rng.integers(3, 10, n),
        'MIN': [f"{m}:00" for m in rng.integers(25, 40, n)],
        'MATCHUP': ['vs. LAL' if i % 2 == 0 else '@ GSW' for i in range(n)],
        'WL': ['W' if i % 2 == 0 else 'L' for i in range(n)],
    })


def pred(prediccion, std=4.0, avg=25.0):
    return {'jugador': 'Test', 'target': 'PTS', 'prediccion': prediccion,
            'mae': 4.0, 'std_historico': std, 'confianza': 'ALTA',
            'es_gtd': False, 'avg_historico': avg}


def test_features_usan_solo_partidos_anteriores(gamelog):
    feats = build_player_features(gamelog)
    for col in ['avg_PTS_L10', 'trend_PTS', 'is_b2b', 'rest_days', 'is_home']:
        assert col in feats.columns
    # El promedio del partido 5 sale de los partidos 0-4, nunca del propio.
    esperado = gamelog['PTS'].iloc[:5].astype(float).mean()
    assert feats['avg_PTS_L5'].iloc[5] == pytest.approx(esperado)


def test_back_to_back_se_detecta_por_fechas():
    df = pd.DataFrame({'GAME_DATE': ['2026-01-01', '2026-01-02', '2026-01-05']})
    assert detectar_back_to_back(df).tolist() == [False, True, False]


def test_modelo_por_jugador_predice_un_valor_razonable(gamelog):
    r = entrenar_modelo_props(gamelog, 'PTS')
    assert r is not None
    assert 5 < r['prediccion'] < 45


def test_edge_y_kelly():
    assert calcular_edge(0.55, 1.91) == pytest.approx(0.0505, abs=1e-3)
    assert kelly_criterion(0.55, 1.91) > 0
    assert kelly_criterion(0.45, 1.91) == 0


def test_prediccion_sobre_la_linea_da_over():
    pick = analizar_pick_prop(pred(32.0), linea_casa=24.5,
                              odds_over=1.91, odds_under=1.87, bankroll=300)
    assert pick is not None and pick['lado'] == 'OVER'


def test_prediccion_bajo_la_linea_da_under():
    pick = analizar_pick_prop(pred(18.0), linea_casa=25.5,
                              odds_over=1.91, odds_under=1.87, bankroll=300)
    assert pick is not None and pick['lado'] == 'UNDER'


def test_prediccion_pegada_a_la_linea_no_da_pick():
    pick = analizar_pick_prop(pred(25.0, std=5.0), linea_casa=25.5,
                              odds_over=1.91, odds_under=1.87, bankroll=300)
    assert pick is None
