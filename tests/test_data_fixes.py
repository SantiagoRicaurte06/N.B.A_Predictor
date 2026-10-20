"""
Arreglos de datos de la fuente NBA (DATA_SPEC §7): filtro de partidos sin
jugar (DNP), normalización de equipos y matching del reporte de lesiones.
"""

import pandas as pd
import pytest

import nba_predictor.datos.fuente_nba as fuente


# ── §7.2 normalización de equipos ──

@pytest.mark.parametrize('a, b', [('NOP', 'NO'), ('GS', 'GSW'), ('phx', 'PHO')])
def test_variantes_de_equipo_normalizan_igual(a, b):
    assert fuente.normalizar_team(a) == fuente.normalizar_team(b)


def test_equipo_desconocido_pasa_en_mayusculas():
    assert fuente.normalizar_team('lal') == 'LAL'


def test_jugador_juega_hoy_cruza_abreviaturas_nba_y_espn():
    assert fuente.jugador_juega_hoy('NOP', {'NO', 'LAL'}) is True
    assert fuente.jugador_juega_hoy('BOS', {'NO', 'LAL'}) is False


def test_sin_calendario_no_filtra():
    assert fuente.jugador_juega_hoy('BOS', set()) is True


# ── §7.1 filtro DNP ──

def test_filtro_dnp_quita_partidos_sin_minutos():
    df = pd.DataFrame({'MIN': ['30:00', '0:00', '', '25:00'], 'PTS': [20, 0, 0, 15]})
    filtrado = fuente._filtrar_dnp(fuente._asegurar_min_num(df))
    assert len(filtrado) == 2
    assert (filtrado['MIN_num'] > 0).all()


# ── §7.3 matching de lesiones ──

@pytest.fixture
def reporte():
    return pd.DataFrame({
        'player_name': ['LeBron James', 'Anthony Davis', 'Jaylen Brown'],
        'status':      ['Out', 'Available', 'GTD'],
        'reason':      ['ankle', '', 'knee'],
    })


def test_nombre_completo_detecta_out(reporte):
    disponible, _ = fuente.is_player_available('LeBron James', reporte)
    assert disponible is False


def test_jugador_fuera_del_reporte_esta_disponible(reporte):
    disponible, _ = fuente.is_player_available('Stephen Curry', reporte)
    assert disponible is True


def test_nombre_completo_evita_ambiguedad_de_apellido():
    reporte = pd.DataFrame({
        'player_name': ['Jaylen Brown', 'Kobe Brown'],
        'status':      ['Out', 'Available'],
        'reason':      ['knee', ''],
    })
    disponible, _ = fuente.is_player_available('Kobe Brown', reporte)
    assert disponible is True
