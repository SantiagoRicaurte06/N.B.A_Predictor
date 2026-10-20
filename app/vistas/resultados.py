"""Pestaña Resultados: resolver picks con los box scores de ESPN e historial."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import nba_predictor.seguimiento.ledger as ledger
from app.comun import fecha_es
from nba_predictor.seguimiento import lineas_reales, resolver

ETIQUETAS = {"W": "Ganó", "L": "Perdió", "VOID": "Anulada"}
CODIGOS = {v: k for k, v in ETIQUETAS.items()}


def _resolver_automatico(df: pd.DataFrame) -> None:
    with st.spinner("Buscando los puntos reales en ESPN…"):
        resueltos = resolver.resolver_pendientes(df)
        for pick_id, res, _ in resueltos:
            ledger.registrar_resultado(pick_id, res)
        completadas = lineas_reales.completar_resultados()
    if resueltos or completadas:
        st.toast(f"{len(resueltos)} picks resueltos · {completadas} líneas completadas",
                 icon=":material/check_circle:")
    else:
        st.toast("No hay partidos terminados con picks pendientes", icon=":material/info:")


def mostrar() -> None:
    df = ledger._cargar_ledger()
    if df.empty:
        st.info("Todavía no hay picks registrados. Se crean desde la pestaña Hoy.")
        return

    pendientes = df[df["resultado"].isna()]
    cab1, cab2 = st.columns([3, 1])
    cab1.subheader(f"Pendientes · {len(pendientes)}")
    if cab2.button("Resolver con ESPN", icon=":material/sync:", width="stretch",
                   disabled=pendientes.empty):
        _resolver_automatico(df)
        st.rerun()

    if not pendientes.empty:
        st.caption("Los picks de partidos ya jugados se resuelven solos con el botón. "
                   "Si un jugador no juega, el pick queda anulado. También puedes marcarlos a mano.")
        editable = pendientes[["id", "fecha", "jugador", "lado", "linea", "odds", "stake"]].copy()
        editable["fecha"] = [fecha_es(f, con_anio=False) for f in editable["fecha"]]
        editable["Resultado"] = None
        editado = st.data_editor(
            editable, hide_index=True, width="stretch", key="editor_resultados",
            disabled=["id", "fecha", "jugador", "lado", "linea", "odds", "stake"],
            column_config={
                "id": st.column_config.NumberColumn("#", width="small"),
                "fecha": "Fecha", "jugador": "Jugador", "lado": "Lado",
                "linea": st.column_config.NumberColumn("Línea", format="%.1f"),
                "odds": st.column_config.NumberColumn("Cuota", format="%.2f"),
                "stake": st.column_config.NumberColumn("Stake", format="%.2f USD"),
                "Resultado": st.column_config.SelectboxColumn(options=list(CODIGOS)),
            },
        )
        marcados = editado.dropna(subset=["Resultado"])
        if st.button(f"Guardar {len(marcados)} resultados", disabled=marcados.empty,
                     icon=":material/save:"):
            for fila in marcados.itertuples():
                ledger.registrar_resultado(int(fila.id), CODIGOS[fila.Resultado])
            st.rerun()

    st.subheader("Historial")
    hist = df.dropna(subset=["resultado"]).sort_values("id", ascending=False).copy()
    if hist.empty:
        st.caption("Aún no hay picks resueltos.")
        return
    hist["fecha"] = [fecha_es(f) for f in hist["fecha"]]
    hist["resultado"] = hist["resultado"].map(ETIQUETAS)
    st.dataframe(
        hist[["id", "fecha", "jugador", "lado", "linea", "odds", "prob_modelo", "stake", "resultado", "pnl"]],
        hide_index=True, width="stretch",
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "fecha": "Fecha", "jugador": "Jugador", "lado": "Lado", "resultado": "Resultado",
            "linea": st.column_config.NumberColumn("Línea", format="%.1f"),
            "odds": st.column_config.NumberColumn("Cuota", format="%.2f"),
            "prob_modelo": st.column_config.NumberColumn("Prob.", format="%.2f"),
            "stake": st.column_config.NumberColumn("Stake", format="%.2f USD"),
            "pnl": st.column_config.NumberColumn("PnL", format="%+.2f USD"),
        },
    )
