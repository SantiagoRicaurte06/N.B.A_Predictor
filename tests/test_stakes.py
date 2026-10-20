"""
Stakes: edge, Kelly y elección del pick. Con probabilidad calibrada del
modelo, el lado del pick sigue a la probabilidad y se respeta el piso de
convicción; sin ella, el lado sigue a la predicción frente a la línea.
"""

import pytest

from nba_predictor.apuestas import stakes
from nba_predictor.apuestas.stakes import analizar_pick_prop, calcular_edge, kelly_criterion


def pred(prediccion, std=4.0, avg=25.0):
    return {'jugador': 'Test', 'target': 'PTS', 'prediccion': prediccion,
            'mae': 4.0, 'std_historico': std, 'confianza': 'ALTA',
            'es_gtd': False, 'avg_historico': avg}


def test_edge_y_kelly():
    assert calcular_edge(0.55, 1.91) == pytest.approx(0.0505, abs=1e-3)
    assert kelly_criterion(0.55, 1.91) > 0
    assert kelly_criterion(0.45, 1.91) == 0


def test_kelly_respeta_el_tope_por_apuesta():
    assert kelly_criterion(0.95, 3.0, fraccion=1.0) == stakes.MAX_BET_PCT


# ── Sin probabilidad calibrada: aproximación normal ──

def test_prediccion_sobre_la_linea_da_over():
    pick = analizar_pick_prop(pred(32.0), 24.5, 1.91, 1.87, bankroll=300)
    assert pick is not None and pick['lado'] == 'OVER'


def test_prediccion_bajo_la_linea_da_under():
    pick = analizar_pick_prop(pred(18.0), 25.5, 1.91, 1.87, bankroll=300)
    assert pick is not None and pick['lado'] == 'UNDER'


def test_prediccion_pegada_a_la_linea_no_da_pick():
    assert analizar_pick_prop(pred(25.0, std=5.0), 25.5, 1.91, 1.87, bankroll=300) is None


# ── Con probabilidad calibrada del modelo ──

def test_probabilidad_calibrada_alta_da_over():
    pick = analizar_pick_prop(pred(27.0), 24.5, 1.87, 1.87, bankroll=1000, prob_over=0.75)
    assert pick['lado'] == 'OVER' and pick['prob_modelo'] == 0.75
    assert pick['stake_usd'] > 0


def test_probabilidad_calibrada_baja_da_under():
    pick = analizar_pick_prop(pred(22.0), 24.5, 1.87, 1.87, bankroll=1000, prob_over=0.22)
    assert pick['lado'] == 'UNDER' and pick['prob_modelo'] == 0.78


def test_bajo_el_piso_de_conviccion_no_hay_pick():
    p = stakes.MIN_PROB - 0.02
    assert analizar_pick_prop(pred(26.0), 24.5, 1.87, 1.87, bankroll=1000, prob_over=p) is None


def test_jugador_en_duda_apuesta_la_mitad():
    sano = analizar_pick_prop(pred(27.0), 24.5, 1.87, 1.87, bankroll=1000, prob_over=0.75)
    duda = analizar_pick_prop({**pred(27.0), 'es_gtd': True}, 24.5, 1.87, 1.87,
                              bankroll=1000, prob_over=0.75)
    assert duda['stake_usd'] == pytest.approx(sano['stake_usd'] / 2, abs=0.5)
