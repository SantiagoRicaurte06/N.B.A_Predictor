"""
Ledger: la contabilidad se deriva de los picks registrados, así que con
resultados conocidos el PnL y el bankroll tienen que salir exactos.
Cada prueba usa un ledger temporal aislado; nunca toca el cache real.
"""

import pytest

import nba_predictor.seguimiento.ledger as trk


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(trk, 'LEDGER_FILE', tmp_path / 'ledger.csv')
    return trk


@pytest.fixture
def tres_picks(ledger):
    """A gana a 2.0 (+10), B pierde (-20), C se anula (0)."""
    id1 = ledger.registrar_pick({"jugador": "A", "target": "PTS", "lado": "OVER",
                                 "linea": 25.5, "odds": 2.0, "stake": 10.0,
                                 "edge_pct": 6.0}, modo="PAPEL")
    id2 = ledger.registrar_pick({"jugador": "B", "target": "PTS", "lado": "UNDER",
                                 "linea": 20.5, "odds": 1.90, "stake": 20.0,
                                 "edge_pct": 9.0}, modo="PAPEL")
    id3 = ledger.registrar_pick({"jugador": "C", "target": "PTS", "lado": "OVER",
                                 "linea": 30.5, "odds": 1.80, "stake": 15.0,
                                 "edge_pct": 12.0}, modo="PAPEL")
    return id1, id2, id3


def test_ledger_vacio_deja_el_bankroll_inicial(ledger):
    assert ledger.bankroll_actual(300.0) == 300.0


def test_ids_incrementales_y_pendientes_no_mueven_bankroll(ledger, tres_picks):
    assert tres_picks == (1, 2, 3)
    assert ledger.bankroll_actual(300.0) == 300.0


def test_pnl_y_bankroll_exactos(ledger, tres_picks):
    id1, id2, id3 = tres_picks
    assert ledger.registrar_resultado(id1, "W") == 10.0
    assert ledger.registrar_resultado(id2, "L") == -20.0
    assert ledger.registrar_resultado(id3, "VOID") == 0.0
    assert ledger.bankroll_actual(300.0) == 290.0


def test_metricas_excluyen_los_anulados(ledger, tres_picks):
    for pick_id, res in zip(tres_picks, ["W", "L", "VOID"]):
        ledger.registrar_resultado(pick_id, res)
    m = ledger.metricas("PAPEL")
    assert m["total_resueltos"] == 2
    assert m["win_rate"] == 50.0
    assert m["anuladas"] == 1
    assert m["roi_pct"] == -33.33     # -10 / 30


def test_errores_controlados(ledger, tres_picks):
    with pytest.raises(KeyError):
        ledger.registrar_resultado(999, "W")
    with pytest.raises(ValueError):
        ledger.registrar_resultado(tres_picks[0], "XYZ")


def test_gate_no_aprueba_con_muestra_chica(ledger, tres_picks):
    for pick_id, res in zip(tres_picks, ["W", "L", "VOID"]):
        ledger.registrar_resultado(pick_id, res)
    g = ledger.estado_gate("PAPEL")
    assert g["aprobado"] is False
    assert g["criterios"]["picks"]["ok"] is False
    assert abs(g["break_even_pct"] - 53.5) < 0.2
    assert "ic_supera_break_even" in g["criterios"]


# ── El agujero que tenía el gate: pasarse por suerte ──

def test_100_picks_al_54_no_superan_el_break_even():
    # IC95 de 44 % a 64 %: el break-even queda dentro, no distingue ventaja.
    assert trk._limite_inferior_wilson(54, 100) <= trk.BREAK_EVEN_PCT


def test_600_picks_al_58_si_lo_superan():
    # 600 y no 470: a 470 el intervalo cae justo en el borde y la prueba
    # dependería del redondeo, no de la lógica.
    assert trk._limite_inferior_wilson(348, 600) > trk.BREAK_EVEN_PCT


def test_mas_muestra_estrecha_el_intervalo():
    assert trk._limite_inferior_wilson(580, 1000) > trk._limite_inferior_wilson(58, 100)


def test_wilson_nunca_es_negativo():
    assert trk._limite_inferior_wilson(0, 10) >= 0.0
