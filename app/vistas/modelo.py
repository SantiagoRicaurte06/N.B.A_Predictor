"""Pestaña Modelo: qué factores usa, cómo rindió en validación y en el holdout."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from nba_predictor.modelo import configuracion as cfg
from nba_predictor.modelo.factores import GRUPOS
from nba_predictor.seguimiento import lineas_reales
from nba_predictor.seguimiento.diagnostico import ejecutar_analisis_completo

RESULTADOS = Path("docs") / "resultados_recalibracion.json"

NOMBRE_GRUPOS = {
    "base": "Forma reciente", "jugador": "Historia del jugador", "ausencias": "Ausencias del equipo",
    "lineas": "Líneas de la casa", "rival": "Rival", "equipo": "Ritmo del equipo",
    "calendario": "Calendario y viajes", "motivacion": "Motivación",
}

DESCRIPCION_GRUPOS = {
    "base": "Puntos, minutos y tiros de sus últimos partidos; local o visitante; descanso.",
    "jugador": "Promedio de temporada y de la anterior, puntos por minuto, titularidad, vuelta tras lesión.",
    "ausencias": "Compañeros que no juegan: puntos y minutos libres, si falta la estrella.",
    "lineas": "Spread y total de la casa para el partido: ritmo esperado y riesgo de paliza.",
    "rival": "Defensa del rival (por posesión y contra la posición del jugador) y sus propias bajas.",
    "equipo": "Ritmo y eficiencia ofensiva del propio equipo.",
    "calendario": "Tres partidos en cuatro noches, viajes, cambio de huso horario, altitud.",
    "motivacion": "Récord del equipo y del rival, racha, playoffs, tramo final, partido contra su exequipo.",
}


def _tabla_umbral(bloque: dict, linea: str) -> pd.DataFrame:
    filas = []
    for umbral, r in bloque["lineas"][linea]["por_umbral"].items():
        filas.append({"Probabilidad ≥": float(umbral), "Picks/semana": r["picks_semana"],
                      "Acierto": r["acierto"], "ROI": r["roi"]})
    return pd.DataFrame(filas)


def _bloque(nombre: str, bloque: dict) -> None:
    e = bloque["error"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Error medio del modelo", f"{e['mae']:.2f} pts", border=True)
    c2.metric("Promedio de 10 partidos", f"{e['mae_ingenua']:.2f} pts",
              delta=f"{e['mae'] - e['mae_ingenua']:+.2f} pts el modelo", delta_color="inverse", border=True)
    inf = bloque["lineas"]["informada"]
    c3.metric(f"Contra línea informada (≥ {inf['umbral']:.2f})",
              "—" if inf["acierto"] != inf["acierto"] else f"{100 * inf['acierto']:.1f} %",
              delta=None if inf["roi"] != inf["roi"] else f"ROI {100 * inf['roi']:+.1f} %", border=True)

    izq, der = st.columns(2, gap="large")
    for col, linea, titulo in ((izq, "informada", "Contra la línea informada"),
                               (der, "ingenua", "Contra la línea ingenua (últ. 10)")):
        with col:
            st.markdown(f"**{titulo}**")
            st.dataframe(_tabla_umbral(bloque, linea), hide_index=True, width="stretch",
                         column_config={
                             "Probabilidad ≥": st.column_config.NumberColumn(format="%.2f"),
                             "Picks/semana": st.column_config.NumberColumn(format="%.0f"),
                             "Acierto": st.column_config.NumberColumn(format="percent"),
                             "ROI": st.column_config.NumberColumn(format="percent"),
                         })
            cal = pd.DataFrame(bloque["lineas"][linea]["calibracion"])
            if not cal.empty:
                st.caption("Probabilidad declarada frente a acierto real (%)")
                cal["Tramo"] = ["50–55", "55–60", "60–65", "65–70", "70–75", "≥ 75"][:len(cal)]
                cal = cal.assign(Declarada=100 * cal["declarada"], Real=100 * cal["real"])
                st.bar_chart(cal.set_index("Tramo")[["Declarada", "Real"]], height=200,
                             stack=False, y_label="", x_label="")


def mostrar() -> None:
    st.subheader("Factores en uso")
    usados = [{"Grupo": NOMBRE_GRUPOS[g], "Qué mide": DESCRIPCION_GRUPOS[g], "En el modelo": g in cfg.GRUPOS}
              for g in sorted(GRUPOS, key=lambda g: g not in cfg.GRUPOS)]
    st.dataframe(pd.DataFrame(usados), hide_index=True, width="stretch",
                 column_config={"Qué mide": st.column_config.TextColumn(width="large"),
                                "En el modelo": st.column_config.CheckboxColumn(width="small")})
    st.caption(f"Modelo {cfg.VERSION}, modo {cfg.MODO}. Un grupo entra solo si baja el error "
               "en validación; los que no aportaron se dejan fuera para no meter ruido.")

    if RESULTADOS.exists():
        res = json.loads(RESULTADOS.read_text())
        st.subheader("Validación · 2023-24 y 2024-25")
        _bloque("validación", res["validacion"])
        if "holdout" in res:
            st.subheader("Holdout · 2025-26 (medido una sola vez)")
            _bloque("holdout", res["holdout"])
        st.caption("Las líneas son sintéticas: Betano ajusta sus líneas con más información, así que "
                   "la medida que manda es la de tus líneas reales, abajo.")
    else:
        st.info("Corre `python scripts/recalibrar.py` para ver los resultados de validación.")

    st.subheader("Contra tus líneas reales de Betano")
    r = lineas_reales.resumen()
    if r["n"] < 30:
        st.caption(f"{r['n']} líneas reales con resultado. Desde 30 se muestran acierto y ROI; "
                   "se acumulan solas cada vez que registras picks en la pestaña Hoy.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Líneas evaluadas", r["n"], border=True)
        c2.metric("Acierto del lado del modelo", f"{100 * r['acierto']:.1f} %", border=True)
        c3.metric("Error: modelo / línea", f"{r['mae_modelo']:.2f} / {r['mae_linea']:.2f}", border=True)

    with st.expander("Diagnóstico de errores de los picks"):
        st.caption("Solo lectura: muestra dónde falla el sistema; no cambia nada por sí solo.")
        if st.button("Ejecutar diagnóstico", icon=":material/troubleshoot:"):
            resultado = ejecutar_analisis_completo()
            if resultado:
                st.text(resultado.get("reporte", ""))
            else:
                st.info("Hacen falta al menos 10 picks resueltos.")
