# ================================================
#  NBA PREDICTOR — MÓDULO 4: DASHBOARD
#  Streamlit app — correr con: streamlit run dashboard.py
# ================================================

import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

# Módulos del sistema
import sys
sys.path.append(str(Path(__file__).parent))

from module1_data_engine import cargar_todos_los_datos
from module2_prediction_engine import generar_predicciones, predecir_total_poisson, predecir_spread
from module3_stakes_engine import (
    generar_stakes, cargar_bankroll, actualizar_bankroll_con_resultado,
    calcular_estadisticas_historial, HISTORIAL_FILE
)
from module5_error_analysis import (
    ejecutar_analisis_completo,
    PATRONES_FILE,
)
from module6_odds_engine import (
    get_odds_props,
    get_api_key,
    set_api_key,
    buscar_jugador_en_props
)
# ─────────────────────────────────────────────
# CONFIGURACIÓN DE LA APP
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="NBA Predictor Pro",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS personalizado
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;800&family=DM+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Syne', sans-serif; }

    .main { background: #060a0f; }
    .stApp { background: #060a0f; }

    /* Cards de picks */
    .pick-card {
        background: #0d1520;
        border: 1px solid #1a2d42;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
    }
    .pick-card-hot { border-left: 4px solid #00ff88; }
    .pick-card-mid { border-left: 4px solid #f7931a; }
    .pick-card-low { border-left: 4px solid #5a7a9a; }

    .metric-big {
        font-family: 'DM Mono', monospace;
        font-size: 28px;
        font-weight: 500;
        color: #f7931a;
    }
    .label-small {
        font-size: 11px;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #5a7a9a;
    }

    /* Botones */
    .stButton > button {
        background: #f7931a;
        color: #060a0f;
        font-weight: 800;
        font-family: 'Syne', sans-serif;
        letter-spacing: 1px;
        border: none;
        border-radius: 4px;
        padding: 10px 24px;
    }
    .stButton > button:hover { background: #ffaa44; }

    /* Sidebar */
    .css-1d391kg { background: #0d1520; }

    /* Inputs */
    .stNumberInput input, .stTextInput input {
        background: #0d1520;
        border-color: #1a2d42;
        color: #e8edf5;
        font-family: 'DM Mono', monospace;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SESSION STATE — Persistencia entre rerenders
# ─────────────────────────────────────────────

if 'datos_cargados' not in st.session_state:
    st.session_state.datos_cargados = None
if 'predicciones' not in st.session_state:
    st.session_state.predicciones = None
if 'picks' not in st.session_state:
    st.session_state.picks = []
if 'bankroll' not in st.session_state:
    st.session_state.bankroll = cargar_bankroll()

# ─────────────────────────────────────────────
# SIDEBAR — Configuración
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Configuración")

    bankroll_inicial = st.number_input(
        "💵 Bankroll ($)",
        min_value=50.0,
        max_value=100000.0,
        value=float(st.session_state.bankroll.get('bankroll_actual', 300.0)),
        step=10.0,
        help="Tu capital total disponible para apostar"
    )

    st.markdown("---")
    st.markdown("### 🔑 Odds API")
    odds_key_actual = get_api_key()
    nueva_key = st.text_input(
        "API Key (the-odds-api.com)",
        value=odds_key_actual if odds_key_actual else "",
        type="password",
        help="Obtén una key gratis en the-odds-api.com (500 requests/mes)"
    )
    if nueva_key and nueva_key != odds_key_actual:
        set_api_key(nueva_key)
        st.success("✅ API Key guardada")

    st.markdown("---")
    st.markdown("### 🏠 Casa de apuestas")
    st.info("**Betano** — Odds decimales")

    st.markdown("---")
    st.markdown("### ⚠️ Riesgo")
    st.caption("Kelly Criterion al 10%")
    st.caption("Edge mínimo: 8%")
    st.caption("Máx por apuesta: 8% bankroll")

    # Mercados suspendidos temporalmente
    st.markdown("---")
    st.markdown("### 🚫 Mercados Suspendidos")
    st.error("**AST y REB** temporalmente desactivados")
    st.caption("Win rate < 35% — Solo PTS disponible")

    st.markdown("---")
    if st.button("🔄 Recargar Datos", use_container_width=True):
        st.session_state.datos_cargados = None
        st.session_state.predicciones = None
        st.session_state.picks = []
        st.rerun()

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("""
    <h1 style='font-family:Syne;font-size:48px;font-weight:800;
               background:linear-gradient(135deg,#fff,#00d4ff);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;
               margin-bottom:4px;'>
        🏀 NBA PREDICTOR PRO
    </h1>
    <p style='color:#5a7a9a;font-family:DM Mono,monospace;font-size:12px;
              letter-spacing:2px;text-transform:uppercase;'>
        Props · Totales · Spread · Kelly Stakes · Betano
    </p>
    """, unsafe_allow_html=True)

with col_h2:
    hoy = datetime.now().strftime('%d %b %Y')
    st.markdown(f"""
    <div style='text-align:right;padding-top:12px;'>
        <div style='font-family:DM Mono,monospace;font-size:11px;
                    color:#5a7a9a;letter-spacing:2px;'>{hoy}</div>
        <div style='font-size:24px;margin-top:4px;'>📊</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ─────────────────────────────────────────────
# TABS PRINCIPALES
# ─────────────────────────────────────────────

tab_picks, tab_lineas, tab_totales, tab_historial, tab_bankroll, tab_analisis = st.tabs([
    "🎯 Picks del Día",
    "📥 Ingresar Líneas",
    "📊 Totales & Spread",
    "📋 Historial",
    "💰 Bankroll",
    "🔍 Análisis de Errores"
])

# ════════════════════════════════════════════
# TAB 1: PICKS DEL DÍA
# ════════════════════════════════════════════

with tab_picks:
    col1, col2, col3 = st.columns(3)

    bankroll_actual = st.session_state.bankroll.get('bankroll_actual', bankroll_inicial)

    with col1:
        st.metric("💵 Bankroll", f"${bankroll_actual:.2f}")
    with col2:
        picks_hoy = len(st.session_state.picks)
        st.metric("🎯 Picks hoy", picks_hoy)
    with col3:
        total_en_juego = sum(p.get('stake_usd', 0) for p in st.session_state.picks)
        st.metric("💸 En juego", f"${total_en_juego:.2f}")

    st.markdown("### Análisis de Jugadores")

    if st.session_state.datos_cargados is None:
        if st.button("🚀 Cargar datos NBA y generar predicciones", use_container_width=True):
            with st.spinner("Descargando datos de la NBA... (puede tardar 2-3 min)"):
                try:
                    datos = cargar_todos_los_datos()
                    st.session_state.datos_cargados = datos

                    predicciones = generar_predicciones(datos)
                    st.session_state.predicciones = predicciones

                    st.success(f"✅ {len(predicciones)} predicciones generadas")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error cargando datos: {e}")
                    st.info("Verifica tu conexión a internet y que nba_api esté instalado.")
    else:
        datos = st.session_state.datos_cargados

        # Mostrar injury report
        injury_df = datos.get('injury_df', pd.DataFrame())
        ausentes = [j for j in datos.get('jugadores_hoy', []) if not j['disponible']]

        if ausentes:
            with st.expander(f"❌ {len(ausentes)} jugadores fuera/dudosos hoy", expanded=False):
                for j in ausentes:
                    st.markdown(f"- **{j['nombre']}**: {j['estado']}")

        # Picks generados
        if st.session_state.picks:
            st.markdown(f"#### 🔥 {len(st.session_state.picks)} picks con valor (edge ≥ 5%)")

            for pick in st.session_state.picks:
                edge = pick['edge_pct']
                css_class = 'hot' if edge >= 10 else ('mid' if edge >= 7 else 'low')
                emoji = "🔥" if edge >= 10 else ("⚡" if edge >= 7 else "📌")

                ajuste_txt = ""
                if pick.get('ajustado_ausencias'):
                    ausentes_nombres = [a['ausente'] for a in pick.get('ajustes_ausencias', [])]
                    ajuste_txt = f" · ⚠️ Ajustado por ausencia de {', '.join(ausentes_nombres)}"

                gtd_txt = " · 🟡 GTD" if pick.get('es_gtd') else ""

                with st.container():
                    st.markdown(f"""
                    <div class='pick-card pick-card-{css_class}'>
                        <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
                            <div>
                                <span style='font-size:18px;font-weight:800;color:#e8edf5;'>
                                    {emoji} {pick['jugador']}
                                </span>
                                <span style='margin-left:10px;font-family:DM Mono,monospace;
                                             font-size:12px;color:#5a7a9a;'>
                                    {pick['tipo']}{gtd_txt}{ajuste_txt}
                                </span>
                            </div>
                            <div style='text-align:right;'>
                                <div style='font-family:DM Mono,monospace;font-size:22px;
                                            color:#f7931a;font-weight:500;'>
                                    ${pick['stake_usd']:.2f}
                                </div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>STAKE</div>
                            </div>
                        </div>
                        <div style='display:flex;gap:24px;margin-top:14px;flex-wrap:wrap;'>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>PREDICCIÓN</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#e8edf5;'>
                                    {pick['prediccion_modelo']}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>LÍNEA</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#e8edf5;'>
                                    {pick['linea']}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>ODDS</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#e8edf5;'>
                                    {pick['odds']}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>EDGE</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#00ff88;'>
                                    +{pick['edge_pct']}%
                                </div>
                            </div>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>CONFIANZA</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#e8edf5;'>
                                    {pick['confianza']}
                                </div>
                            </div>
                            <div>
                                <div style='font-size:11px;color:#5a7a9a;letter-spacing:1px;'>GANANCIA POT.</div>
                                <div style='font-family:DM Mono,monospace;font-size:16px;color:#00d4ff;'>
                                    +${pick['ganancia_potencial']}
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("👆 Ve a **Ingresar Líneas** para añadir las odds de Betano y generar picks.")

# ════════════════════════════════════════════
# TAB 2: INGRESAR LÍNEAS
# ════════════════════════════════════════════

with tab_lineas:
    st.markdown("### 📥 Ingresa las líneas de Betano")
    st.caption("Ingresa las odds decimales y líneas para los jugadores disponibles hoy.")

    # ── BOTÓN CARGAR ODDS AUTOMÁTICAMENTE ──
    api_key = get_api_key()
    if not api_key:
        st.info("""
        🔑 **Configura tu API Key de The Odds API**

        Obtén una key gratis en [the-odds-api.com](https://the-odds-api.com)
        - 500 requests gratis por mes
        - Datos en tiempo real de Betano y otras casas
        - Configúrala en el sidebar ←
        """)
    else:
        if st.button("⚡ Cargar Odds Automáticamente desde Betano", use_container_width=True):
            with st.spinner("Conectando a The Odds API y obteniendo líneas..."):
                try:
                    odds_data = get_odds_props()
                    if odds_data:
                        st.session_state['odds_automaticas'] = odds_data
                        st.success(f"✅ {len(odds_data)} líneas de odds cargadas")
                        st.rerun()
                    else:
                        st.warning("""
                        ⚠️ **No se encontraron player props disponibles**

                        El plan gratuito de The Odds API incluye:
                        - Spreads (líneas de partido)
                        - Totals (over/under de puntos del partido)
                        - Moneylines (quién gana)

                        **Los player props (PTS/REB/AST por jugador) requieren un plan de pago.**

                        💡 Opciones:
                        1. Ingresa las líneas manualmente abajo
                        2. Usa la API de Betano directamente si tienes acceso
                        """)
                except Exception as e:
                    st.error(f"Error al obtener odds: {e}")

    if st.session_state.predicciones is None:
        st.warning("Primero carga los datos en la pestaña **Picks del Día**")
    else:
        predicciones = st.session_state.predicciones
        lineas = {}

        # Agrupar por jugador
        jugadores_pred = list(set(p['jugador'] for p in predicciones))
        jugadores_pred.sort()

        # Recuperar odds automáticas si existen
        odds_auto = st.session_state.get('odds_automaticas', {})

        for jugador in jugadores_pred:
            preds_jugador = [p for p in predicciones if p['jugador'] == jugador]

            with st.expander(f"🏀 {jugador}", expanded=False):
                for pred in preds_jugador:
                    target = pred['target']
                    avg    = pred.get('avg_historico', 0)
                    mae    = pred.get('mae', 0)
                    pred_val = pred.get('prediccion', avg)

                    # Buscar odds automáticas para este jugador+target
                    key_busqueda = f"{jugador}_{target}"
                    odds_match = None
                    if odds_auto:
                        # Buscar por coincidencia exacta o por nombre parcial
                        for key_auto, datos_auto in odds_auto.items():
                            if key_auto == key_busqueda:
                                odds_match = datos_auto
                                break
                            # Buscar por nombre parcial (sin el _PTS/_REB/_AST)
                            if target in ['PTS', 'REB', 'AST']:
                                nombre_key = f"{jugador}_{target}"
                                if key_auto == nombre_key:
                                    odds_match = datos_auto
                                    break

                    # Valores por defecto: automáticos si hay, sino manuales
                    linea_default = float(avg)
                    odds_over_default = 1.87
                    odds_under_default = 1.87

                    if odds_match:
                        linea_default = float(odds_match.get('linea', avg))
                        odds_over_default = float(odds_match.get('odds_over', 1.87))
                        odds_under_default = float(odds_match.get('odds_under', 1.87))
                        badge = " 📡"  # Indicador de odds automáticas
                    else:
                        badge = ""

                    st.markdown(f"**{target}** — Modelo predice: `{pred_val}` | Promedio L10: `{avg}` | MAE: ±`{mae}`{badge}")

                    col_l, col_o, col_u = st.columns(3)
                    with col_l:
                        linea = st.number_input(
                            f"Línea {target}",
                            min_value=0.0, max_value=100.0,
                            value=linea_default, step=0.5,
                            key=f"linea_{jugador}_{target}"
                        )
                    with col_o:
                        odds_over = st.number_input(
                            "Odds Over",
                            min_value=1.01, max_value=10.0,
                            value=odds_over_default, step=0.01,
                            key=f"odds_over_{jugador}_{target}"
                        )
                    with col_u:
                        odds_under = st.number_input(
                            "Odds Under",
                            min_value=1.01, max_value=10.0,
                            value=odds_under_default, step=0.01,
                            key=f"odds_under_{jugador}_{target}"
                        )

                    lineas[f"{jugador}_{target}"] = {
                        'linea': linea,
                        'odds_over': odds_over,
                        'odds_under': odds_under
                    }
                    st.markdown("---")

        if st.button("⚡ Calcular Picks y Stakes", use_container_width=True):
            with st.spinner("Calculando Kelly Criterion..."):
                picks, estado_bk, stats = generar_stakes(
                    predicciones, lineas, bankroll_inicial
                )
                st.session_state.picks = picks
                st.session_state.bankroll = estado_bk
                st.success(f"✅ {len(picks)} picks con valor generados — ve a **Picks del Día**")
                st.rerun()

# ════════════════════════════════════════════
# TAB 3: TOTALES & SPREAD
# ════════════════════════════════════════════

with tab_totales:
    st.markdown("### 📊 Totales O/U y Spread")
    st.caption("Ingresa los promedios de los equipos para generar predicciones de partido completo.")

    col_a, col_b = st.columns(2)

    with col_a:
        home_team = st.text_input("Equipo Local", value="LAL")
        home_pts  = st.number_input("Promedio puntos LOCAL (L10)", value=113.0, step=0.5)
        home_def  = st.number_input("Puntos recibidos LOCAL (L10)", value=110.0, step=0.5)

    with col_b:
        away_team = st.text_input("Equipo Visitante", value="GSW")
        away_pts  = st.number_input("Promedio puntos VISITANTE (L10)", value=115.0, step=0.5)
        away_def  = st.number_input("Puntos recibidos VISITANTE (L10)", value=112.0, step=0.5)

    st.markdown("---")
    col_t, col_s = st.columns(2)

    with col_t:
        linea_total    = st.number_input("Línea Total (O/U)", value=225.5, step=0.5)
        odds_over_tot  = st.number_input("Odds Over", value=1.87, step=0.01, key="to")
        odds_under_tot = st.number_input("Odds Under", value=1.87, step=0.01, key="tu")

    with col_s:
        linea_spread   = st.number_input("Spread (+ favorece visitante)", value=-5.5, step=0.5)
        odds_home_sp   = st.number_input("Odds Local cubre spread", value=1.87, step=0.01, key="sh")
        odds_away_sp   = st.number_input("Odds Visitante cubre spread", value=1.87, step=0.01, key="sa")

    if st.button("🔢 Analizar Partido", use_container_width=True):
        # Total
        resultado_total = predecir_total_poisson(home_pts, away_pts, linea_total)
        resultado_spread = predecir_spread(home_pts, away_pts, home_def, away_def, linea_spread)

        st.markdown("---")
        col_r1, col_r2 = st.columns(2)

        with col_r1:
            st.markdown("#### 🔢 Total O/U")
            st.metric("Total esperado", f"{resultado_total['total_esperado']} pts")
            st.metric("Prob OVER", f"{resultado_total['prob_over']*100:.1f}%")
            st.metric("Prob UNDER", f"{resultado_total['prob_under']*100:.1f}%")

            edge_over  = (resultado_total['prob_over'] * odds_over_tot) - 1
            edge_under = (resultado_total['prob_under'] * odds_under_tot) - 1

            if max(edge_over, edge_under) >= 0.05:
                lado = "OVER" if edge_over > edge_under else "UNDER"
                edge = max(edge_over, edge_under)
                st.success(f"✅ **{lado}** {linea_total} | Edge: {edge*100:.1f}%")
            else:
                st.warning("Sin valor claro en totales")

        with col_r2:
            st.markdown("#### 📏 Spread")
            st.metric("Margen esperado", f"{resultado_spread['margen_esperado']:+.1f}")
            st.metric(f"Prob {home_team} cubre", f"{resultado_spread['prob_home_cover']*100:.1f}%")
            st.metric(f"Prob {away_team} cubre", f"{resultado_spread['prob_away_cover']*100:.1f}%")

            edge_home = (resultado_spread['prob_home_cover'] * odds_home_sp) - 1
            edge_away = (resultado_spread['prob_away_cover'] * odds_away_sp) - 1

            if max(edge_home, edge_away) >= 0.05:
                lado  = home_team if edge_home > edge_away else away_team
                edge  = max(edge_home, edge_away)
                st.success(f"✅ **{lado}** {linea_spread:+.1f} | Edge: {edge*100:.1f}%")
            else:
                st.warning("Sin valor claro en spread")

# ════════════════════════════════════════════
# TAB 4: HISTORIAL
# ════════════════════════════════════════════

with tab_historial:
    st.markdown("### 📋 Historial de Apuestas")

    stats = calcular_estadisticas_historial()

    if not stats or 'mensaje' in stats:
        st.info("El historial se irá llenando conforme registres resultados.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Win Rate", f"{stats.get('win_rate', 0)}%")
        with col2: st.metric("ROI", f"{stats.get('roi_pct', 0)}%")
        with col3: st.metric("Total picks", stats.get('total_picks', 0))
        with col4: st.metric("Edge promedio", f"{stats.get('avg_edge_pct', 0)}%")

    if HISTORIAL_FILE.exists():
        df_hist = pd.read_csv(HISTORIAL_FILE)
        st.markdown("---")

        # Registrar resultados pendientes
        pendientes = df_hist[df_hist['resultado'].isna()]
        if not pendientes.empty:
            st.markdown(f"#### ⏳ {len(pendientes)} picks pendientes de resultado")

            for idx, row in pendientes.tail(20).iterrows():
                col_i, col_r = st.columns([4, 1])
                with col_i:
                    st.markdown(f"**{row.get('jugador','')}** — {row.get('tipo','')} | Stake: ${row.get('stake_usd', 0):.2f}")
                with col_r:
                    resultado = st.selectbox(
                        "Resultado",
                        ["—", "✅ Ganó", "❌ Perdió", "⚪ Anulada"],
                        key=f"res_{idx}"
                    )
                    if resultado != "—":
                        if 'Anulada' in resultado:
                            # Apuesta anulada: no afecta bankroll, se devuelve el stake
                            df_hist.at[idx, 'resultado'] = 'VOID'
                            df_hist.to_csv(HISTORIAL_FILE, index=False)
                            st.success(f"⚪ Apuesta anulada — stake devuelto")
                            st.rerun()
                        else:
                            wl = 'W' if 'Ganó' in resultado else 'L'
                            df_hist.at[idx, 'resultado'] = wl
                            df_hist.to_csv(HISTORIAL_FILE, index=False)
                            estado_bk = actualizar_bankroll_con_resultado(
                                wl, float(row.get('stake_usd', 0)),
                                float(row.get('odds', 1.87)),
                                st.session_state.bankroll
                            )
                            st.session_state.bankroll = estado_bk
                            st.rerun()

        # Tabla completa
        st.markdown("#### 📊 Todos los picks")
        cols_mostrar = ['jugador', 'tipo', 'prediccion_modelo', 'linea',
                        'odds', 'edge_pct', 'stake_usd', 'ganancia_potencial', 'resultado']
        cols_disponibles = [c for c in cols_mostrar if c in df_hist.columns]
        st.dataframe(df_hist[cols_disponibles].tail(50), use_container_width=True)

# ════════════════════════════════════════════
# TAB 5: BANKROLL
# ════════════════════════════════════════════

with tab_bankroll:
    st.markdown("### 💰 Estado del Bankroll")

    bk = st.session_state.bankroll

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Bankroll actual",
            f"${bk.get('bankroll_actual', 0):.2f}",
            delta=f"${bk.get('bankroll_actual', 0) - bk.get('bankroll_inicial', 300):.2f}"
        )
    with col2:
        total_ap = bk.get('apuestas_ganadas', 0) + bk.get('apuestas_perdidas', 0)
        ganadas  = bk.get('apuestas_ganadas', 0)
        wr = round(ganadas / total_ap * 100, 1) if total_ap > 0 else 0
        st.metric("Win Rate", f"{wr}%", delta=f"{ganadas}W / {bk.get('apuestas_perdidas', 0)}L")
    with col3:
        st.metric("ROI Total", f"{bk.get('roi_total', 0):.1f}%")

    st.markdown("---")
    st.markdown("#### ℹ️ Cómo funciona el Kelly Criterion")
    st.markdown("""
    El sistema usa **Kelly Criterion al 25%** (fraccionado) para proteger tu bankroll:

    - **Kelly completo** maximiza el crecimiento pero es muy agresivo
    - **25% del Kelly** reduce el riesgo de ruina manteniendo el crecimiento
    - **Edge mínimo 5%** filtra apuestas sin valor real
    - **Máximo 8%** del bankroll por apuesta para diversificar riesgo

    Con $300 de bankroll, las apuestas típicas serán entre **$3 y $24**.
    """)

    st.markdown("---")
    nuevo_bankroll = st.number_input(
        "Ajustar bankroll manualmente ($)",
        value=float(bk.get('bankroll_actual', 300)),
        step=10.0
    )
    if st.button("💾 Guardar ajuste de bankroll"):
        from module3_stakes_engine import guardar_bankroll
        bk['bankroll_actual'] = nuevo_bankroll
        guardar_bankroll(bk)
        st.session_state.bankroll = bk
        st.success("Bankroll actualizado")
        st.rerun()

# ════════════════════════════════════════════
# TAB 6: ANÁLISIS DE ERRORES
# ════════════════════════════════════════════

with tab_analisis:
    st.markdown("### 🔍 Diagnóstico de Errores")
    st.caption("Solo lectura: muestra dónde falla el modelo. NO aplica cambios "
               "automáticos — las decisiones se toman con evidencia de backtest (ADR-004).")

    # Ejecutar análisis
    if st.button("🔍 Ejecutar Diagnóstico", use_container_width=True):
        with st.spinner("Analizando picks resueltos del ledger..."):
            try:
                resultado = ejecutar_analisis_completo()
                if resultado:
                    st.session_state['ultimo_analisis'] = resultado
                    st.success("✅ Diagnóstico completado")
                    st.rerun()
                else:
                    st.warning("Necesitas al menos 10 picks con resultado registrado para analizar.")
            except Exception as e:
                st.error(f"Error en análisis: {e}")

    # Mostrar último análisis
    if 'ultimo_analisis' in st.session_state:
        analisis = st.session_state['ultimo_analisis']
        patrones = analisis.get('patrones', {})
        problemas = analisis.get('problemas', [])

        # Resumen
        resumen = patrones.get('resumen', {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Win Rate global", f"{resumen.get('win_rate_global', 0)}%")
        with col2:
            st.metric("ROI global", f"{resumen.get('roi_global', 0)}%")
        with col3:
            tendencia = patrones.get('tendencia_temporal', {})
            delta = tendencia.get('delta', 0)
            st.metric("Tendencia reciente", f"{delta:+.1f}%",
                      delta=delta, delta_color="normal")

        # Por mercado
        st.markdown("#### 📊 Rendimiento por mercado")
        mercados = patrones.get('por_mercado', {})
        if mercados:
            df_merc = pd.DataFrame([
                {
                    'Mercado': k,
                    'Win Rate': f"{v['win_rate']}%",
                    'Picks': v['n_picks'],
                    'Rentable': "✅" if v['rentable'] else "❌"
                }
                for k, v in mercados.items()
            ])
            st.dataframe(df_merc, use_container_width=True, hide_index=True)

        # Por jugador
        jugadores_prob = {
            j: s for j, s in patrones.get('por_jugador', {}).items()
            if s.get('problema')
        }
        if jugadores_prob:
            st.markdown("#### ⚠️ Jugadores problemáticos")
            for jugador, stats in jugadores_prob.items():
                st.error(f"**{jugador}** — {stats['win_rate']}% en {stats['n_picks']} picks")

        # Problemas detectados (informativos — no se aplican solos)
        if problemas:
            st.markdown(f"#### 🚨 {len(problemas)} problemas detectados")
            st.caption("Sugerencias para revisar con backtest. El sistema NO las aplica automáticamente.")
            for p in problemas:
                emoji = "🔴" if p['severidad'] == 'ALTA' else "🟡"
                with st.expander(f"{emoji} {p['descripcion']}"):
                    st.markdown(f"**Sugerencia (revisar con backtest):** {p['accion']}")
                    if p.get('feature_sugerida'):
                        st.code(f"Feature sugerida: {p['feature_sugerida']}")

        # Reporte completo
        with st.expander("📄 Ver reporte completo en texto"):
            st.text(analisis.get('reporte', ''))

    else:
        st.info("👆 Ejecuta el diagnóstico cuando tengas al menos 10 picks con resultado registrado. "
                "Identificará patrones de fallo para que decidas con evidencia (no aplica cambios solo).")
