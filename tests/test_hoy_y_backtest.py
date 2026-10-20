"""
Flujo del día (filas de hoy a partir de la historia y el reporte de
lesiones) y aritmética de la simulación de apuestas del backtest.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nba_predictor.backtest import temporadas as bt
from nba_predictor.datos.hoy import filas_de_hoy, temporada_de
from nba_predictor.modelo import factores as fx
from tests.test_factores import temporada_sintetica


@pytest.mark.parametrize("dia, esperado", [
    (date(2026, 10, 20), "2026-27"), (date(2027, 3, 1), "2026-27"), (date(2026, 6, 10), "2025-26"),
])
def test_temporada_de(dia, esperado):
    assert temporada_de(dia) == esperado


def test_filas_de_hoy_marcan_las_bajas_y_se_pueden_predecir():
    jp, ep = temporada_sintetica()
    hoy = (jp["fecha"].max() + pd.Timedelta(days=2)).date()
    partidos = [{"id": "999", "fecha": f"{hoy}T23:30Z", "local": "BOS", "visitante": "NY", "tipo": 2}]
    reporte = pd.DataFrame({"athlete_id": ["BOS0", "NY3"], "estado": ["Out", "Questionable"]})
    lineas = {"999": {"spread_local": -4.5, "total": 228.5}}

    plantillas = {eq: [{"athlete_id": f"{eq}{j}", "jugador": f"{eq} {j}", "posicion": "GFC"[j % 3]}
                       for j in range(9)] for eq in ("BOS", "NY")}
    jh, eh = filas_de_hoy(plantillas, partidos, reporte, lineas, hoy)
    assert set(jh["equipo"]) == {"BOS", "NY"}
    assert jh.set_index("athlete_id").loc["BOS0", "no_jugo"]
    assert jh.set_index("athlete_id").loc["NY3", "es_duda"]
    assert eh.set_index("equipo").loc["NY", "spread_equipo"] == 4.5

    df = fx.construir(pd.concat([jp, jh], ignore_index=True), pd.concat([ep, eh], ignore_index=True))
    hoy_df = df[df["es_hoy"].fillna(False).astype(bool)]
    assert len(hoy_df) > 0 and "BOS0" not in set(hoy_df["athlete_id"])
    # La baja de la estrella de BOS se refleja en sus compañeros.
    assert hoy_df[hoy_df["equipo"] == "BOS"]["estrella_fuera"].eq(1).all()


def test_apuestas_eligen_el_lado_probable_y_cuentan_bien():
    pred = pd.DataFrame({
        "PTS": [30, 10, 20, 25], "semana": ["s1"] * 4,
        "linea_ingenua": [24.5, 15.5, 19.5, 25.5],
        "p_over_ingenua": [0.70, 0.20, 0.52, 0.66],
    })
    picks = bt.apuestas(pred, "ingenua", 0.60)
    # 0.70 OVER (gana), 0.20 → UNDER al 0.80 (gana), 0.66 OVER con 25 < 25.5 (pierde)
    assert picks["lado"].tolist() == ["OVER", "UNDER", "OVER"]
    assert picks["gana"].tolist() == [True, True, False]
    r = bt.resumen_apuestas(picks, semanas=1)
    assert r["acierto"] == pytest.approx(2 / 3)
    assert r["roi"] == pytest.approx((2 * 0.87 - 1) / 3)
