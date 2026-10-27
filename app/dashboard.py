"""
NBA Predictor · dashboard.

    streamlit run app/dashboard.py

Cuatro pestañas: Hoy (predicciones, líneas y picks), Resultados, Rendimiento
y Modelo. El tema claro u oscuro se elige en ⋮ → Settings.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app import comun                                          # noqa: E402
from app.acceso import exigir_login                            # noqa: E402
from app.vistas import hoy, modelo, rendimiento, resultados    # noqa: E402
from nba_predictor.apuestas.stakes import PARAMS               # noqa: E402
from nba_predictor.modelo import configuracion as cfg          # noqa: E402

st.set_page_config(page_title="NBA Predictor", page_icon=":material/sports_basketball:",
                   layout="wide", initial_sidebar_state="collapsed")
exigir_login()
comun.iniciar_estado()

with st.sidebar:
    st.subheader("Ajustes")
    st.session_state["bankroll_inicial"] = st.number_input(
        "Bankroll inicial (USD)", min_value=50.0, max_value=1_000_000.0, step=50.0,
        value=float(st.session_state["bankroll_inicial"]),
        help="Capital con el que empezó el modo papel. El actual se calcula con los resultados.")
    if st.button("Volver a cargar el día", icon=":material/refresh:", width="stretch"):
        for clave in ("datos", "tabla", "modelo"):
            st.session_state[clave] = None
        st.rerun()
    st.divider()
    st.caption(f"Modo {comun.MODO} · sin dinero real")
    st.caption(f"Modelo {cfg.VERSION} · Kelly {PARAMS['kelly_fraction'] * 100:.0f} % · "
               f"prob. mínima {PARAMS['min_prob'] * 100:.0f} %")
    if st.user.get("is_logged_in"):
        st.divider()
        st.caption(st.user.get("email", ""))
        st.button("Cerrar sesión", icon=":material/logout:", on_click=st.logout, width="stretch")

cab, fecha = st.columns([4, 1], vertical_alignment="bottom")
cab.title("NBA Predictor")
cab.caption("Puntos de jugadores · picks en papel contra las líneas de Betano")
bk = comun.bankroll()
variacion = bk["bankroll_actual"] - bk["bankroll_inicial"]
fecha.metric(comun.fecha_es(datetime.now()), comun.dinero(bk["bankroll_actual"]),
             delta=comun.dinero(variacion, signo=True) if abs(variacion) >= 0.005 else None)

t_hoy, t_res, t_rend, t_mod = st.tabs(["Hoy", "Resultados", "Rendimiento", "Modelo"])
with t_hoy:
    hoy.mostrar()
with t_res:
    resultados.mostrar()
with t_rend:
    rendimiento.mostrar()
with t_mod:
    modelo.mostrar()
