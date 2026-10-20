"""
Resolución automática de picks con ESPN y registro de líneas reales.
La API se reemplaza por un día de partidos falso: las pruebas no salen a red.
"""

from datetime import date

import pandas as pd
import pytest

import nba_predictor.seguimiento.ledger as ledger
from nba_predictor.seguimiento import lineas_reales, resolver

DIA = date(2026, 11, 3)
PUNTOS = pd.DataFrame({
    "athlete_id": ["1", "2", "3"],
    "jugador": ["Jalen Brunson", "Tyrese Maxey", "Joel Embiid"],
    "PTS": [31.0, 18.0, None],
    "no_jugo": [False, False, True],
})


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_FILE", tmp_path / "ledger.csv")
    monkeypatch.setattr(lineas_reales, "ARCHIVO", tmp_path / "lineas.csv")
    monkeypatch.setattr(resolver, "puntos_del_dia", lambda dia: PUNTOS if dia == DIA else PUNTOS.iloc[0:0])


@pytest.mark.parametrize("lado, linea, pts, no_jugo, esperado", [
    ("OVER", 27.5, 31, False, "W"), ("OVER", 27.5, 20, False, "L"),
    ("UNDER", 21.5, 18, False, "W"), ("UNDER", 21.5, 25, False, "L"),
    ("OVER", 20.5, None, True, "VOID"),
])
def test_resultado_de_un_pick(lado, linea, pts, no_jugo, esperado):
    assert resolver.resultado_pick(lado, linea, pts, no_jugo) == esperado


def test_resuelve_por_id_y_por_nombre_y_anula_si_no_jugo(aislado):
    base = {"fecha": f"{DIA}T18:00:00", "target": "PTS", "odds": 1.87, "stake": 10.0}
    a = ledger.registrar_pick({**base, "jugador": "Jalen Brunson", "athlete_id": "1",
                               "lado": "OVER", "linea": 27.5})
    b = ledger.registrar_pick({**base, "jugador": "Tyrese Maxey", "lado": "UNDER", "linea": 21.5})
    c = ledger.registrar_pick({**base, "jugador": "Joel Embiid", "athlete_id": "3",
                               "lado": "OVER", "linea": 24.5})
    hoy_pendiente = ledger.registrar_pick({**base, "fecha": "2026-11-04T18:00:00",
                                           "jugador": "Jalen Brunson", "lado": "OVER", "linea": 27.5})

    resueltos = {pid: res for pid, res, _ in
                 resolver.resolver_pendientes(ledger._cargar_ledger(), hoy=date(2026, 11, 4))}
    assert resueltos == {a: "W", b: "W", c: "VOID"}
    assert hoy_pendiente not in resueltos      # su partido aún no se juega


def test_ledger_guarda_el_athlete_id_como_texto(aislado):
    ledger.registrar_pick({"jugador": "X", "athlete_id": "4433188", "lado": "OVER",
                           "linea": 10.5, "odds": 1.87, "stake": 5.0})
    assert ledger._cargar_ledger()["athlete_id"].iloc[0] == "4433188"


def test_lineas_reales_se_completan_y_resumen(aislado):
    filas = [
        {"athlete_id": "1", "jugador": "Jalen Brunson", "linea": 27.5, "prediccion": 29.0, "prob_over": 0.72},
        {"athlete_id": "2", "jugador": "Tyrese Maxey", "linea": 21.5, "prediccion": 19.0, "prob_over": 0.30},
        {"athlete_id": "3", "jugador": "Joel Embiid", "linea": 24.5, "prediccion": 26.0, "prob_over": 0.60},
    ]
    assert lineas_reales.registrar(filas, dia=DIA) == 3
    # Volver a registrar el mismo jugador el mismo día reemplaza la línea.
    lineas_reales.registrar([{**filas[0], "linea": 28.5}], dia=DIA)
    df = lineas_reales.cargar()
    assert len(df) == 3 and df.set_index("athlete_id").loc["1", "linea"] == 28.5

    assert lineas_reales.completar_resultados(hoy=date(2026, 11, 4)) == 2   # Embiid no jugó
    r = lineas_reales.resumen()
    # Brunson OVER 28.5 con 31 (gana) y Maxey UNDER 21.5 con 18 (gana).
    assert r["n"] == 2 and r["acierto"] == 1.0
