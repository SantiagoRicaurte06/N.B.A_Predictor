"""Estado de sesión y formatos compartidos por las vistas del dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from nba_predictor.apuestas.stakes import PARAMS, cargar_bankroll

MODO = "PAPEL"


def iniciar_estado() -> None:
    st.session_state.setdefault("datos", None)
    st.session_state.setdefault("tabla", None)
    st.session_state.setdefault("modelo", None)
    st.session_state.setdefault("bankroll_inicial", PARAMS["bankroll_inicial"])


def bankroll() -> dict:
    return cargar_bankroll(st.session_state["bankroll_inicial"], MODO)


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_es(fecha, con_anio: bool = True) -> str:
    """'20 oct 2026' sin depender del idioma del sistema."""
    f = pd.Timestamp(fecha)
    texto = f"{f.day} {MESES[f.month - 1]}"
    return f"{texto} {f.year}" if con_anio else texto


def dinero(x: float, signo: bool = False) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+,.2f} USD" if signo else f"{x:,.2f} USD"


def pct(x: float, signo: bool = False, decimales: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.{decimales}f} %" if signo else f"{x:.{decimales}f} %"


def contexto(fila) -> str:
    """Resumen corto de los factores que mueven la predicción de hoy."""
    partes = []
    if getattr(fila, "estrella_fuera", 0) == 1 and getattr(fila, "rango_pts_hoy", 99) <= 3:
        partes.append("falta la estrella")
    aus = getattr(fila, "aus_pts", 0) or 0
    if aus >= 15:
        partes.append(f"{aus:.0f} pts libres en su equipo")
    if getattr(fila, "rango_pts_hoy", 99) == 1:
        partes.append("primera opción")
    perdidos = getattr(fila, "partidos_perdidos", 0) or 0
    if perdidos >= 2:
        partes.append(f"vuelve tras {perdidos:.0f} partidos")
    spread = getattr(fila, "spread_equipo", None)
    if spread is not None and not pd.isna(spread) and abs(spread) >= 10:
        partes.append("posible paliza")
    if getattr(fila, "es_duda", False):
        partes.append("en duda")
    return " · ".join(partes)
