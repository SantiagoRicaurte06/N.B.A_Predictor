"""
Registro de TODAS las líneas reales de Betano que se ingresan, apostadas o no.

El backtest usa líneas sintéticas; el edge real contra la casa solo se
puede medir con sus líneas. Guardando cada línea con la predicción y la
probabilidad del modelo, y completando después los puntos reales, se
acumula con el tiempo un backtest contra líneas reales sin sesgo de
selección (no solo los picks que el modelo eligió).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from nba_predictor.seguimiento import resolver

ARCHIVO = Path("cache") / "lineas_betano.csv"
COLUMNAS = ["fecha", "athlete_id", "jugador", "equipo", "rival", "linea", "cuota_over",
            "cuota_under", "prediccion", "prob_over", "version_modelo", "pts_reales"]


def cargar() -> pd.DataFrame:
    if not ARCHIVO.exists():
        return pd.DataFrame(columns=COLUMNAS)
    df = pd.read_csv(ARCHIVO, dtype={"athlete_id": str})
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = pd.NA
    return df[COLUMNAS]


def registrar(filas: list[dict], dia: date | None = None) -> int:
    """Guarda las líneas del día. Una línea repetida (mismo día y jugador)
    reemplaza a la anterior: vale la última que se ingresó."""
    if not filas:
        return 0
    dia = (dia or datetime.now().date()).isoformat()
    nuevas = pd.DataFrame([{**{c: f.get(c) for c in COLUMNAS}, "fecha": dia} for f in filas])
    df = cargar()
    clave = set(zip(nuevas["fecha"], nuevas["athlete_id"].astype(str)))
    df = df[[(f, str(a)) not in clave for f, a in zip(df["fecha"], df["athlete_id"])]]
    df = nuevas if df.empty else pd.concat([df, nuevas], ignore_index=True)
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ARCHIVO, index=False)
    return len(nuevas)


def completar_resultados(hoy: date | None = None) -> int:
    """Rellena los puntos reales de las líneas de días ya jugados."""
    hoy = hoy or datetime.now().date()
    df = cargar()
    faltan = df[df["pts_reales"].isna() & (pd.to_datetime(df["fecha"]).dt.date < hoy)]
    completadas = 0
    for dia, grupo in faltan.groupby("fecha"):
        puntos = resolver.puntos_del_dia(pd.Timestamp(dia).date())
        if puntos.empty:
            continue
        for idx, fila in grupo.iterrows():
            j = resolver.buscar(puntos, fila["athlete_id"], fila["jugador"])
            if j is not None and not j["no_jugo"]:
                df.loc[idx, "pts_reales"] = j["PTS"]
                completadas += 1
    if completadas:
        df.to_csv(ARCHIVO, index=False)
    return completadas


def resumen(cuota: float = 1.87, umbral: float = 0.5) -> dict:
    """Acierto del lado que eligió el modelo contra las líneas reales."""
    df = cargar().dropna(subset=["pts_reales", "prob_over"])
    if df.empty:
        return {"n": 0}
    p = df["prob_over"].astype(float)
    over = p >= 0.5
    prob = p.where(over, 1 - p)
    gana = (df["pts_reales"].astype(float) > df["linea"].astype(float)).where(
        over, df["pts_reales"].astype(float) < df["linea"].astype(float))
    sel = prob >= umbral
    n = int(sel.sum())
    acierto = float(gana[sel].mean()) if n else float("nan")
    return {"n": n, "acierto": acierto, "roi": acierto * (cuota - 1) - (1 - acierto) if n else float("nan"),
            "mae_modelo": float((df["pts_reales"].astype(float) - df["prediccion"].astype(float)).abs().mean()),
            "mae_linea": float((df["pts_reales"].astype(float) - df["linea"].astype(float)).abs().mean())}
