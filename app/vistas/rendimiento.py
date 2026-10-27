"""Pestaña Rendimiento: bankroll, ROI, calibración en vivo y gate papel → real."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import nba_predictor.seguimiento.ledger as ledger
from app.comun import MODO, bankroll, dinero, pct
from nba_predictor.apuestas.stakes import PARAMS


def _serie_bankroll(df: pd.DataFrame, inicial: float) -> pd.DataFrame:
    jugados = df[df["resultado"].isin(["W", "L", "VOID"])].copy()
    if jugados.empty:
        return pd.DataFrame(columns=["dia", "bankroll"])
    jugados["dia"] = pd.to_datetime(jugados["fecha"]).dt.normalize()
    diario = jugados.groupby("dia")["pnl"].sum().astype(float)
    return (inicial + diario.cumsum()).rename("bankroll").reset_index()


def _curva_bankroll(serie: pd.DataFrame) -> None:
    grafico = alt.Chart(serie).mark_line(strokeWidth=2).encode(
        x=alt.X("dia:T", title=None, axis=alt.Axis(format="%d/%m", labelAngle=0)),
        y=alt.Y("bankroll:Q", title="USD", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("dia:T", title="Día", format="%d/%m/%Y"),
                 alt.Tooltip("bankroll:Q", title="Bankroll", format=",.2f")],
    ).properties(height=240)
    st.altair_chart(grafico, width="stretch")


def _calibracion(df: pd.DataFrame) -> None:
    if df.empty:
        st.caption("La calibración en vivo aparece con 20 picks resueltos.")
        return
    jugados = df[df["resultado"].isin(["W", "L"])].dropna(subset=["prob_modelo"]).copy()
    if len(jugados) < 20:
        st.caption("La calibración en vivo aparece con 20 picks resueltos.")
        return
    jugados["prob_modelo"] = jugados["prob_modelo"].astype(float)
    cortes = [0.5, 0.6, 0.65, 0.7, 0.75, 1.0]
    nombres = ["50–60 %", "60–65 %", "65–70 %", "70–75 %", "75 % o más"]
    jugados["tramo"] = pd.cut(jugados["prob_modelo"], cortes, right=False, labels=nombres)
    tabla = jugados.groupby("tramo", observed=True).agg(
        Picks=("resultado", "size"),
        Declarada=("prob_modelo", lambda p: 100 * p.mean()),
        Real=("resultado", lambda r: 100 * (r == "W").mean()),
    ).reset_index().rename(columns={"tramo": "Probabilidad"})
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        "Declarada": st.column_config.NumberColumn(format="%.1f %%"),
        "Real": st.column_config.NumberColumn(format="%.1f %%"),
    })
    st.caption("Si el acierto real queda muy por debajo del declarado en varios tramos, "
               "el modelo se está sobrevalorando.")


def _gate() -> None:
    g = ledger.estado_gate(MODO)
    c = g["criterios"]
    st.progress(g["progreso_picks"],
                text=f"Muestra: {c['picks']['actual']} de {c['picks']['meta']} picks resueltos")
    ic = c.get("ic_supera_break_even", {})
    # Sin picks resueltos no hay acierto ni ROI que medir: se muestran vacíos, no como 0 % cumplido.
    hay = c["picks"]["actual"] > 0
    filas = [
        ("Muestra", f"{c['picks']['actual']}", f"≥ {c['picks']['meta']}", c["picks"]["ok"]),
        ("Acierto", pct(c["win_rate"]["actual"] if hay else None), f"≥ {c['win_rate']['meta']} %",
         hay and c["win_rate"]["ok"]),
        ("ROI", pct(c["roi"]["actual"] if hay else None), f"≥ {c['roi']['meta']} %", hay and c["roi"]["ok"]),
        ("IC 95 % (Wilson), límite inferior", pct(ic.get("actual") if hay else None),
         f"> {g['break_even_pct']} %", hay and ic.get("ok", False)),
    ]
    st.dataframe(pd.DataFrame(filas, columns=["Criterio", "Actual", "Meta", "Cumple"]),
                 hide_index=True, width="stretch",
                 column_config={"Cumple": st.column_config.CheckboxColumn()})
    if g["aprobado"]:
        st.success("Gate superado: el sistema demostró ventaja en papel con una muestra suficiente.")
    else:
        st.info("Gate no superado: seguir en papel. El criterio decisivo es el intervalo de "
                "confianza, que separa una ventaja real de una buena racha.")


def mostrar() -> None:
    bk = bankroll()
    m = ledger.metricas(MODO)
    be = ledger.BREAK_EVEN_PCT

    df = ledger._cargar_ledger()
    df = df[df["modo"] == MODO] if not df.empty else df
    serie = _serie_bankroll(df, bk["bankroll_inicial"]) if not df.empty else pd.DataFrame()

    k1, k2, k3, k4 = st.columns(4)
    variacion = bk["bankroll_actual"] - bk["bankroll_inicial"]
    k1.metric("Bankroll", dinero(bk["bankroll_actual"]),
              delta=dinero(variacion, signo=True) if abs(variacion) >= 0.005 else None, border=True,
              chart_data=list(serie["bankroll"]) if len(serie) > 1 else None, chart_type="area")
    if m.get("total_resueltos", 0):
        k2.metric("ROI", pct(m["roi_pct"], signo=True), border=True)
        k3.metric("Acierto", pct(m["win_rate"]), delta=f"{m['win_rate'] - be:+.1f} pts vs break-even",
                  border=True)
    else:
        k2.metric("ROI", "—", border=True)
        k3.metric("Acierto", "—", border=True)
    k4.metric("Resueltos", m.get("total_resueltos", 0),
              delta=f"{m.get('pendientes', 0)} pendientes", delta_color="off", delta_arrow="off",
              border=True)

    izq, der = st.columns([3, 2], gap="large")
    with izq:
        st.subheader("Bankroll")
        if len(serie) < 2:
            st.caption("La curva aparece cuando haya picks resueltos en dos días distintos.")
        else:
            _curva_bankroll(serie)
        st.subheader("Calibración en vivo")
        _calibracion(df)
    with der:
        st.subheader("Gate papel → dinero real")
        _gate()
        st.subheader("Gestión del riesgo")
        st.markdown(
            f"- Kelly fraccionado al **{PARAMS['kelly_fraction'] * 100:.0f} %**.\n"
            f"- Probabilidad mínima para apostar: **{PARAMS['min_prob'] * 100:.0f} %**.\n"
            f"- Tope por apuesta: **{PARAMS['max_bet_pct'] * 100:.0f} %** del bankroll; "
            f"jugadores en duda, la mitad.\n"
            f"- Break-even a cuota 1.87: **{be} %**.\n\n"
            "El bankroll se deriva del registro de picks: no se edita a mano."
        )
