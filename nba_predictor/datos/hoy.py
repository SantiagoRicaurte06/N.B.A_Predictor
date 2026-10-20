"""
Datos del día desde ESPN: pone al día la temporada en curso, trae los
partidos de hoy con sus líneas y el reporte de lesiones, y arma las filas
"de hoy" que el constructor de factores completa con la historia.

Los días pasados se cachean (no cambian); hoy siempre se consulta en vivo.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from nba_predictor.datos import espn
from nba_predictor.datos.boxscore import cargar_tablas, construir_tablas

# Estado del reporte de lesiones → qué significa para el modelo.
BAJA = {"Out", "Doubtful", "Suspension"}          # no juega: cuenta como ausencia
DUDA = {"Questionable", "Day-To-Day", "Probable"}  # juega con riesgo: stake reducido

TEMPORADAS_HISTORICAS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def temporada_de(dia: date) -> str:
    """La temporada NBA arranca en octubre: oct-2026 → '2026-27'."""
    anio = dia.year if dia.month >= 8 else dia.year - 1
    return f"{anio}-{(anio + 1) % 100:02d}"


def _partidos_dia_cacheado(temporada: str, dia: date) -> list[dict]:
    ruta = espn.CACHE_ESPN / temporada / "dias" / f"{dia:%Y%m%d}.json.gz"
    if ruta.exists():
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)
    partidos = espn.partidos_del_dia(dia)
    if all(p["terminado"] for p in partidos):
        espn._escribir_gz(ruta, partidos)
    return partidos


def actualizar_temporada(temporada: str, hasta: date) -> int:
    """Descarga los partidos terminados de la temporada hasta `hasta` (excluido)."""
    inicio, _ = espn.rango_temporada(temporada)
    nuevos = 0
    dia = inicio
    while dia < hasta:
        for p in _partidos_dia_cacheado(temporada, dia):
            if not p["terminado"]:
                continue
            if not espn.ruta_resumen(temporada, p["id"]).exists():
                try:
                    espn.resumen_partido(p["id"], temporada)
                    nuevos += 1
                except Exception:
                    continue
            if not espn.ruta_lineas(temporada, p["id"]).exists():
                espn._intentar(espn.lineas_partido, p["id"], temporada)
        dia += timedelta(days=1)
    return nuevos


def lesiones() -> pd.DataFrame:
    df = pd.DataFrame(espn.reporte_lesiones())
    if df.empty:
        return pd.DataFrame(columns=["equipo", "jugador", "athlete_id", "estado", "detalle"])
    return df


def historial(hoy: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tablas jugador-partido y equipo-partido de las temporadas cerradas más
    lo jugado de la temporada en curso."""
    jp, ep = cargar_tablas(TEMPORADAS_HISTORICAS)
    actual = temporada_de(hoy)
    if actual not in TEMPORADAS_HISTORICAS:
        actualizar_temporada(actual, hoy)
        if (espn.CACHE_ESPN / actual / "partidos").exists():
            jpa, epa = construir_tablas([actual])
            if len(epa):
                jp, ep = pd.concat([jp, jpa], ignore_index=True), pd.concat([ep, epa], ignore_index=True)
    return jp, ep


def filas_de_hoy(plantillas: dict[str, list[dict]], partidos: list[dict], reporte: pd.DataFrame,
                 lineas: dict[str, dict], hoy: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Filas jugador-partido y equipo-partido para los partidos de hoy.

    La plantilla de cada equipo es la vigente en ESPN (con traspasos y
    fichajes). Quien figura como baja en el reporte entra como "no juega":
    así el modelo ve las ausencias de hoy igual que las veía en la historia.
    """
    temporada = temporada_de(hoy)
    estado = dict(zip(reporte.get("athlete_id", []), reporte.get("estado", [])))
    filas_j, filas_e = [], []
    for p in partidos:
        fecha_utc = pd.Timestamp(p["fecha"])
        fecha_utc = fecha_utc.tz_convert("UTC").tz_localize(None) if fecha_utc.tzinfo else fecha_utc
        l = lineas.get(p["id"], {})
        for equipo, rival, local in ((p["local"], p["visitante"], True), (p["visitante"], p["local"], False)):
            base = {"temporada": temporada, "evento": str(p["id"]), "fecha": pd.Timestamp(hoy),
                    "fecha_utc": fecha_utc, "tipo": p.get("tipo", 2), "neutral": False,
                    "equipo": equipo, "rival": rival, "local": local}
            spread = l.get("spread_local")
            filas_e.append({**base, "pts": np.nan, "pts_rival": np.nan, "posesiones": np.nan,
                            "spread_equipo": np.nan if spread is None else (spread if local else -spread),
                            "total_linea": l.get("total", np.nan)})
            for j in plantillas.get(equipo, []):
                # El reporte general manda; si no lo trae, el estado de la plantilla.
                st = estado.get(j["athlete_id"]) or j.get("estado", "")
                j = {k: v for k, v in j.items() if k != "estado"}
                filas_j.append({**base, **j, "titular": False, "no_jugo": st in BAJA,
                                "motivo": st, "expulsado": False, "es_hoy": True,
                                "estado_lesion": st, "es_duda": st in DUDA})
    return pd.DataFrame(filas_j), pd.DataFrame(filas_e)


def datos_del_dia(hoy: date | None = None) -> dict:
    """Todo lo que el modelo necesita para predecir los partidos de hoy."""
    hoy = hoy or datetime.now().date()
    jp, ep = historial(hoy)
    partidos = [p for p in espn.partidos_del_dia(hoy) if not p["terminado"]]
    reporte = lesiones()
    lineas = {p["id"]: espn._intentar(espn.lineas_partido, p["id"]) or {} for p in partidos}
    equipos = {e for p in partidos for e in (p["local"], p["visitante"])}
    plantillas = {e: espn._intentar(espn.plantilla, e) or [] for e in equipos}
    jh, eh = filas_de_hoy(plantillas, partidos, reporte, lineas, hoy)
    return {"hoy": hoy, "jp": jp, "ep": ep, "jp_hoy": jh, "ep_hoy": eh,
            "partidos": partidos, "lesiones": reporte}
