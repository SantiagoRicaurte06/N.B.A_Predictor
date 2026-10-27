"""Pestaña Hoy: partidos, predicciones, líneas de Betano y picks en un solo flujo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from app.comun import MODO, bankroll, contexto, dinero, fecha_es
from nba_predictor.apuestas.stakes import PARAMS, analizar_pick_prop, guardar_picks_del_dia
from nba_predictor.datos import espn
from nba_predictor.datos.hoy import TEMPORADAS_HISTORICAS, datos_del_dia
from nba_predictor.modelo import configuracion as cfg
from nba_predictor.modelo import diario
from nba_predictor.seguimiento import lineas_reales

CUOTA_DEFECTO = 1.87


PASOS = [
    (":material/download:", "1 · Carga el día",
     "Partidos, reporte de lesiones, plantillas y líneas de partido desde ESPN. "
     "El modelo predice los puntos de cada jugador de rotación."),
    (":material/edit_note:", "2 · Escribe las líneas",
     "Copia la línea de Betano de los jugadores que te interesan. El modelo da la "
     "probabilidad calibrada de over o under y el stake Kelly."),
    (":material/fact_check:", "3 · Resuelve mañana",
     "En Resultados, un botón resuelve los picks con los box scores de ESPN y "
     "actualiza el bankroll en papel."),
]


def _faltan_temporadas() -> list[str]:
    return [t for t in TEMPORADAS_HISTORICAS
            if not any((espn.CACHE_ESPN / t / "partidos").glob("*.json.gz"))]


def _cargar() -> bool:
    with st.status("Preparando el día…", expanded=True) as estado:
        try:
            estado.write("Partidos, lesiones y líneas de ESPN")
            datos = datos_del_dia()
            estado.write("Modelo de puntos (se entrena una vez al día, tarda un minuto)")
            tabla, modelo = diario.predecir(datos)
        except Exception as e:  # red caída o ESPN sin responder: el usuario puede reintentar
            estado.update(label="No se pudo preparar el día", state="error")
            st.error(f"ESPN no respondió o los datos llegaron incompletos ({type(e).__name__}). "
                     "Vuelve a intentarlo en unos minutos.", icon=":material/cloud_off:")
            return False
        st.session_state.update(datos=datos, tabla=tabla, modelo=modelo)
        estado.update(label=f"{len(tabla)} jugadores listos", state="complete")
    return True


def _inicio() -> None:
    st.subheader("Partidos de hoy")
    columnas = st.columns(len(PASOS))
    for col, (icono, titulo, texto) in zip(columnas, PASOS):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{icono} {titulo}**")
            st.caption(texto)

    faltan = _faltan_temporadas()
    if faltan:
        st.warning("Falta el histórico de ESPN de " + ", ".join(faltan) + ". Descárgalo una vez "
                   "con `python -m nba_predictor.datos.espn` (unos minutos) y recarga la página.",
                   icon=":material/database:")
    if st.button("Cargar partidos y predicciones", type="primary", icon=":material/download:",
                 disabled=bool(faltan)):
        if _cargar():
            st.rerun()


def _partidos(datos: dict) -> None:
    ep = datos["ep_hoy"]
    if ep.empty:
        st.info("Hoy no hay partidos NBA.")
        return
    jh = datos["jp_hoy"]
    filas = []
    for p in datos["partidos"]:
        loc = ep[(ep["evento"] == str(p["id"])) & (ep["equipo"] == p["local"])].iloc[0]
        bajas = jh[(jh["evento"] == str(p["id"])) & jh["no_jugo"]]
        filas.append({
            "Partido": f"{p['visitante']} @ {p['local']}",
            "Hora (ET)": pd.Timestamp(p["fecha"]).tz_convert("America/New_York").strftime("%H:%M"),
            "Spread local": loc["spread_equipo"],
            "Total": loc["total_linea"],
            "Bajas": ", ".join(f"{b.jugador} ({b.equipo})" for b in bajas.itertuples()) or "—",
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch",
                 column_config={"Spread local": st.column_config.NumberColumn(format="%+.1f"),
                                "Total": st.column_config.NumberColumn(format="%.1f")})


def _editor(tabla: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame({
        "athlete_id": tabla["athlete_id"],
        "Jugador": tabla["jugador"],
        "Equipo": tabla["equipo"],
        "Rival": tabla["rival"],
        "Predicción": tabla["prediccion"],
        "Últ. 10": tabla["pts_l10"].round(1),
        "Contexto": [contexto(f) for f in tabla.itertuples()],
        "Línea": np.nan,
        "Cuota over": CUOTA_DEFECTO,
        "Cuota under": CUOTA_DEFECTO,
    })
    return st.data_editor(
        base, key="editor_lineas", hide_index=True, width="stretch", height=460,
        disabled=["Jugador", "Equipo", "Rival", "Predicción", "Últ. 10", "Contexto"],
        column_order=["Jugador", "Equipo", "Rival", "Predicción", "Últ. 10", "Contexto",
                      "Línea", "Cuota over", "Cuota under"],
        column_config={
            "Predicción": st.column_config.NumberColumn(format="%.1f", help="Puntos esperados por el modelo"),
            "Últ. 10": st.column_config.NumberColumn(format="%.1f", help="Promedio de sus últimos 10 partidos"),
            "Contexto": st.column_config.TextColumn(width="medium"),
            "Línea": st.column_config.NumberColumn(min_value=0.5, max_value=80.0, step=0.5, format="%.1f",
                                                   help="Línea de puntos de Betano"),
            "Cuota over": st.column_config.NumberColumn(min_value=1.01, max_value=10.0, step=0.01, format="%.2f"),
            "Cuota under": st.column_config.NumberColumn(min_value=1.01, max_value=10.0, step=0.01, format="%.2f"),
        },
    )


def _evaluar(editadas: pd.DataFrame, tabla: pd.DataFrame, modelo, bankroll_actual: float) -> pd.DataFrame:
    con_linea = editadas.dropna(subset=["Línea"])
    if con_linea.empty:
        return con_linea
    info = tabla.set_index("athlete_id")
    filas = []
    for f in con_linea.to_dict("records"):
        j = info.loc[f["athlete_id"]]
        linea, c_over, c_under = float(f["Línea"]), float(f["Cuota over"]), float(f["Cuota under"])
        p_over, _ = diario.probabilidad(modelo, float(j["prediccion"]), linea)
        pred = {"jugador": j["jugador"], "target": "PTS", "prediccion": float(j["prediccion"]),
                "avg_historico": float(j["pts_l10"]), "mae": float(j["sigma"]),
                "es_gtd": bool(j.get("es_duda", False)), "confianza": "MEDIA"}
        pick = analizar_pick_prop(pred, linea, c_over, c_under, bankroll_actual, p_over)
        lado = "OVER" if p_over >= 0.5 else "UNDER"
        filas.append({
            "athlete_id": f["athlete_id"], "Jugador": j["jugador"], "Línea": linea,
            "Predicción": j["prediccion"], "Lado": lado,
            "Probabilidad": max(p_over, 1 - p_over),
            "Edge": pick["edge_pct"] / 100 if pick else np.nan,
            "Stake": pick["stake_usd"] if pick else 0.0,
            "Pick": pick is not None, "_pick": pick, "_p_over": p_over,
            "_equipo": j["equipo"], "_rival": j["rival"],
            "_cuota_over": c_over, "_cuota_under": c_under, "_sigma": float(j["sigma"]),
        })
    return pd.DataFrame(filas).sort_values(["Pick", "Probabilidad"], ascending=False)


def mostrar() -> None:
    datos, tabla, modelo = (st.session_state[k] for k in ("datos", "tabla", "modelo"))
    if datos is None:
        _inicio()
        return

    st.subheader(f"Partidos · {fecha_es(datos['hoy'])}")
    _partidos(datos)
    if tabla is None or tabla.empty:
        return

    st.subheader("Predicciones y líneas de Betano")
    st.caption("Escribe la línea de los jugadores que ofrece Betano. La probabilidad es la "
               "del modelo calibrado; solo se recomienda apostar desde "
               f"{100 * PARAMS['min_prob']:.0f} % (medido en validación).")
    editadas = _editor(tabla)

    bk = bankroll()["bankroll_actual"]
    evaluadas = _evaluar(editadas, tabla, modelo, bk)
    if evaluadas.empty:
        return

    st.subheader("Evaluación")
    st.dataframe(
        evaluadas[["Jugador", "Línea", "Predicción", "Lado", "Probabilidad", "Edge", "Stake", "Pick"]],
        hide_index=True, width="stretch",
        column_config={
            "Línea": st.column_config.NumberColumn(format="%.1f"),
            "Predicción": st.column_config.NumberColumn(format="%.1f"),
            "Probabilidad": st.column_config.ProgressColumn(format="%.2f", min_value=0.5, max_value=1.0),
            "Edge": st.column_config.NumberColumn(format="percent"),
            "Stake": st.column_config.NumberColumn(format="%.2f USD"),
            "Pick": st.column_config.CheckboxColumn("Apostar"),
        },
    )
    picks = [p for p in evaluadas["_pick"] if p]
    col1, col2 = st.columns([3, 1])
    col1.caption(f"{len(picks)} picks · {dinero(sum(p['stake_usd'] for p in picks))} en juego · "
                 f"bankroll {dinero(bk)} · modo {MODO}")
    if col2.button(f"Registrar {len(picks)} picks", type="primary", disabled=not picks,
                   icon=":material/save:", width="stretch"):
        _registrar(evaluadas, picks)


def _registrar(evaluadas: pd.DataFrame, picks: list[dict]) -> None:
    ids = {p["jugador"]: aid for p, aid in zip(evaluadas["_pick"], evaluadas["athlete_id"]) if p}
    for p in picks:
        p["athlete_id"] = ids.get(p["jugador"])
        p["pred_sigma"] = float(evaluadas.loc[evaluadas["Jugador"] == p["jugador"], "_sigma"].iloc[0])
    guardar_picks_del_dia(picks, modo=MODO)
    # Todas las líneas ingresadas, apostadas o no: base del backtest con líneas reales.
    lineas_reales.registrar([{
        "athlete_id": f["athlete_id"], "jugador": f["Jugador"], "equipo": f["_equipo"],
        "rival": f["_rival"], "linea": f["Línea"], "cuota_over": f["_cuota_over"],
        "cuota_under": f["_cuota_under"], "prediccion": f["Predicción"],
        "prob_over": f["_p_over"], "version_modelo": cfg.VERSION,
    } for f in evaluadas.to_dict("records")])
    st.toast(f"{len(picks)} picks registrados en papel", icon=":material/check_circle:")
