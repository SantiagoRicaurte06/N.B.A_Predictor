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
from module9_pooled_model import generar_predicciones_pooled
from module3_stakes_engine import (
    generar_stakes, cargar_bankroll,
    calcular_estadisticas_historial, PARAMS,
)
import module8_tracking as trk
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
    st.caption(f"Kelly Criterion al {PARAMS['kelly_fraction']*100:.0f}%")
    st.caption(f"Edge mínimo: {PARAMS['min_edge']*100:.0f}%")
    st.caption(f"Máx por apuesta: {PARAMS['max_bet_pct']*100:.0f}% bankroll")

    st.markdown("---")
    st.markdown("### 🎯 Alcance v1")
    st.info(f"Mercado activo: **{', '.join(PARAMS['mercados_activos'])}**")
    st.caption("v1 enfocada en PTS (ADR-001). Modo PAPEL — sin dinero real.")

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

# Totales & Spread fuera de alcance v1 (ADR-001) — el código queda latente en module2.
tab_picks, tab_lineas, tab_historial, tab_paper, tab_bankroll, tab_analisis = st.tabs([
    "🎯 Picks del Día",
    "📥 Ingresar Líneas",
    "📋 Historial",
    "📈 Paper Trading",
    "💰 Bankroll",
    "🔍 Diagnóstico"
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
            with st.spinner("Descargando datos NBA y entrenando modelo pooled... (2-3 min)"):
                try:
                    datos = cargar_todos_los_datos()
                    st.session_state.datos_cargados = datos

                    # Modelo pooled (ADR-002): entrena una vez y se reutiliza.
                    predicciones, modelo = generar_predicciones_pooled(
                        datos, st.session_state.get('modelo_pooled')
                    )
                    st.session_state['modelo_pooled'] = modelo
                    st.session_state.predicciones = predicciones

                    st.success(f"✅ {len(predicciones)} predicciones generadas (modelo pooled)")
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

# NOTA: la pestaña "Totales & Spread" se retiró en v1 (ADR-001). Las funciones
# predecir_total_poisson / predecir_spread siguen en module2 como código latente.

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

    ledger = trk._cargar_ledger()
    if not ledger.empty:
        st.markdown("---")

        # Registrar resultados pendientes (marca por id → module8; el bankroll
        # se re-deriva solo, ADR-007).
        pendientes = ledger[ledger['resultado'].isna()]
        if not pendientes.empty:
            st.markdown(f"#### ⏳ {len(pendientes)} picks pendientes de resultado")

            for _, row in pendientes.tail(20).iterrows():
                pick_id = int(row['id'])
                col_i, col_r = st.columns([4, 1])
                with col_i:
                    st.markdown(
                        f"**{row.get('jugador','')}** — "
                        f"{row.get('target','')} {row.get('lado','')} {row.get('linea','')} "
                        f"| Stake: ${float(row.get('stake', 0) or 0):.2f}"
                    )
                with col_r:
                    resultado = st.selectbox(
                        "Resultado",
                        ["—", "✅ Ganó", "❌ Perdió", "⚪ Anulada"],
                        key=f"res_{pick_id}"
                    )
                    if resultado != "—":
                        codigo = ("VOID" if "Anulada" in resultado
                                  else ("W" if "Ganó" in resultado else "L"))
                        trk.registrar_resultado(pick_id, codigo)
                        st.session_state.bankroll = cargar_bankroll()
                        st.rerun()

        # Tabla completa
        st.markdown("#### 📊 Todos los picks (ledger)")
        cols_mostrar = ['id', 'jugador', 'target', 'lado', 'linea', 'odds',
                        'edge_pct', 'stake', 'resultado', 'pnl']
        cols_disponibles = [c for c in cols_mostrar if c in ledger.columns]
        st.dataframe(ledger[cols_disponibles].tail(50), use_container_width=True)

# ════════════════════════════════════════════
# TAB PAPER TRADING — validación en papel (Fase 3)
# ════════════════════════════════════════════

with tab_paper:
    st.markdown("### 📈 Paper Trading — validación en papel")
    st.caption("Modo PAPEL: sin dinero real. La meta es demostrar edge aquí antes "
               "de arriesgar un peso (ADR-003).")

    m = trk.metricas("PAPEL")
    be = trk.BREAK_EVEN_PCT

    if m.get("total_resueltos", 0) == 0:
        st.info("Aún no hay picks resueltos. Genera picks, márcalos en **Historial** "
                "y aquí verás el ROI, el win rate y la calibración en vivo.")
    else:
        wr  = m["win_rate"]
        roi = m["roi_pct"]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("ROI papel", f"{roi:+.1f}%")
        with col2:
            st.metric("Win rate", f"{wr}%", delta=f"{wr - be:+.1f} vs break-even",
                      delta_color="normal")
        with col3:
            st.metric("Picks resueltos", m["total_resueltos"])
        with col4:
            st.metric("PnL papel", f"${m['pnl_total']:+.2f}")

        st.caption(f"Break-even a cuota 1.87 ≈ {be}%. Por debajo de eso, el sistema pierde.")

        # ── Calibración en vivo ──
        st.markdown("#### 🎯 Calibración en vivo (¿el edge alto gana más?)")
        cal = m.get("calibracion_por_edge", {})
        if cal:
            filas = []
            for b in ["bajo", "medio", "alto"]:
                if b in cal:
                    c = cal[b]
                    filas.append({"Bucket edge": b, "Edge medio": f"{c['edge_medio']}%",
                                  "Win rate": f"{c['win_rate']}%", "N": c["n"]})
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
            st.caption("Si el win rate NO sube del bucket bajo al alto, el modelo sobreestima su edge.")
        else:
            st.caption("Se necesitan ~6 picks resueltos para el desglose de calibración.")

    # ── Gate papel → real ──
    st.markdown("---")
    st.markdown("#### 🚦 Gate: ¿listo para dinero real?")
    gate = trk.estado_gate("PAPEL")
    st.progress(gate["progreso_picks"],
                text=f"Muestra: {gate['criterios']['picks']['actual']} / "
                     f"{gate['criterios']['picks']['meta']} picks")

    crit = gate["criterios"]
    def _fmt(c, sufijo=""):
        return ("✅" if c["ok"] else "⬜") + f" {c['actual']}{sufijo} (meta ≥ {c['meta']}{sufijo})"

    st.markdown(f"- **Muestra:** {_fmt(crit['picks'])}")
    st.markdown(f"- **Win rate:** {_fmt(crit['win_rate'], '%')}")
    st.markdown(f"- **ROI:** {_fmt(crit['roi'], '%')}")

    if gate["aprobado"]:
        st.success("✅ Gate superado: el sistema demostró edge en papel. Recién aquí "
                   "tendría sentido evaluar dinero real (con reglas de riesgo estrictas).")
    else:
        st.warning("⬜ Gate no superado todavía. Seguir en papel — sin arriesgar dinero.")


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
    st.markdown("#### ℹ️ Cómo funciona el sizing")
    st.markdown(f"""
    - **Kelly Criterion al {PARAMS['kelly_fraction']*100:.0f}%** (fraccionado) para limitar el riesgo de ruina.
    - **Edge mínimo {PARAMS['min_edge']*100:.0f}%** filtra apuestas sin valor real.
    - **Máximo {PARAMS['max_bet_pct']*100:.0f}%** del bankroll por apuesta.

    El bankroll se **deriva del ledger** (suma de PnL), no se ajusta a mano —
    así es siempre reproducible y auditable (ADR-007). Modo actual: **PAPEL**
    (sin dinero real hasta validar edge por backtest, ADR-003).
    """)

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
