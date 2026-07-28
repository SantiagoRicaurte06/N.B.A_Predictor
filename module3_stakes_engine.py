# ================================================
#  NBA PREDICTOR — MÓDULO 3: STAKES ENGINE
#  Responsabilidad:
#    - Kelly Criterion fraccionado
#    - Gestión de bankroll
#    - Clasificación de picks por valor
#    - Registro histórico de apuestas
# ================================================

from datetime import datetime

import module8_tracking as trk

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE RIESGO — fuente única (PARAMS)
# ─────────────────────────────────────────────
# Todos los parámetros viven aquí. El dashboard los LEE de PARAMS en vez de
# tener textos hardcodeados que se desincronizan del código.

PARAMS = {
    'kelly_fraction': 0.10,   # Kelly fraccionado
    'min_edge':       0.08,   # Edge mínimo para considerar un pick
    'max_bet_pct':    0.08,   # Tope: 8% del bankroll por apuesta
    'min_bet_usd':    2.0,    # Apuesta mínima en USD
    'confianza_mult': {'ALTA': 1.0, 'MEDIA': 0.50, 'BAJA': 0.25},
    'mercados_activos': ['PTS'],   # v1 PTS-only (ADR-001)
    'bankroll_inicial': 300.0,
}

# Alias de compatibilidad para el resto del módulo (leen de PARAMS).
KELLY_FRACTION = PARAMS['kelly_fraction']
MIN_EDGE       = PARAMS['min_edge']
MAX_BET_PCT    = PARAMS['max_bet_pct']
MIN_BET_USD    = PARAMS['min_bet_usd']
CONFIANZA_MULT = PARAMS['confianza_mult']

# ─────────────────────────────────────────────
# 1. BANKROLL — DERIVADO del ledger (ADR-007)
# ─────────────────────────────────────────────
# El bankroll ya no se almacena como número mutable. Se deriva del ledger de
# module8 (suma de PnL). `cargar_bankroll` devuelve un dict con la misma forma
# que antes para compatibilidad con el dashboard, pero todo se calcula en vivo.

def cargar_bankroll(bankroll_inicial: float | None = None, modo: str = "PAPEL") -> dict:
    """Estado del bankroll derivado del ledger. No lee ni escribe archivo mutable."""
    inicial = bankroll_inicial if bankroll_inicial is not None else PARAMS['bankroll_inicial']
    m = trk.metricas(modo)
    return {
        'bankroll_actual':   trk.bankroll_actual(inicial, modo),
        'bankroll_inicial':  inicial,
        'apuestas_ganadas':  m.get('ganadas', 0),
        'apuestas_perdidas': m.get('perdidas', 0),
        'roi_total':         m.get('roi_pct', 0.0),
        'total_apostado':    m.get('apostado_total', 0.0),
    }

# ─────────────────────────────────────────────
# 2. KELLY CRITERION
# ─────────────────────────────────────────────

def kelly_criterion(prob_modelo: float,
                     odds_decimal: float,
                     fraccion: float = KELLY_FRACTION) -> float:
    """
    Calcula el porcentaje óptimo del bankroll a apostar.

    Fórmula Kelly: f = (b*p - q) / b
    donde:
        b = odds - 1 (ganancia neta por unidad)
        p = probabilidad de ganar (modelo)
        q = 1 - p (probabilidad de perder)

    Retorna fracción del bankroll (0 a MAX_BET_PCT).
    """
    if odds_decimal <= 1.0 or prob_modelo <= 0 or prob_modelo >= 1:
        return 0.0

    b = odds_decimal - 1  # ganancia neta
    p = prob_modelo
    q = 1 - p

    kelly_full = (b * p - q) / b

    if kelly_full <= 0:
        return 0.0  # no hay edge

    # Aplicar fracción y límite máximo
    kelly_fraccionado = kelly_full * fraccion
    kelly_limitado = min(kelly_fraccionado, MAX_BET_PCT)

    return round(kelly_limitado, 4)


def calcular_stake_usd(kelly_pct: float,
                        bankroll: float,
                        confianza: str = 'MEDIA',
                        es_gtd: bool = False) -> float:
    """
    Convierte el porcentaje Kelly a un monto en USD.
    Aplica ajustes por confianza del modelo y estado GTD.
    """
    mult_confianza = CONFIANZA_MULT.get(confianza, 0.5)
    mult_gtd = 0.5 if es_gtd else 1.0  # reducir stake si es GTD

    stake = bankroll * kelly_pct * mult_confianza * mult_gtd

    # Redondear a múltiplos de $0.50 para practicidad
    stake = round(stake * 2) / 2

    # Aplicar mínimo
    if stake < MIN_BET_USD:
        return 0.0  # no vale la pena apostar tan poco

    return stake

# ─────────────────────────────────────────────
# 3. ANÁLISIS DE PICKS
# ─────────────────────────────────────────────
def calcular_edge(prob_modelo: float, odds_decimal: float) -> float:
    """Edge esperado vs la casa. Positivo = valor a favor del apostador."""
    if odds_decimal <= 1:
        return 0.0
    return round((prob_modelo * odds_decimal) - 1, 4)


def validar_prediccion(prediccion: float, target: str, avg_historico: float) -> tuple[bool, str]:
    """
    Valida que la predicción sea razonable.
    Retorna (es_valida, razon).
    """
    # Umbrales de validación por mercado
    umbrales = {
        'PTS': {'min': 3.0, 'max': 50.0, 'ratio_max': 2.5},
        'REB': {'min': 1.0, 'max': 25.0, 'ratio_max': 3.0},
        'AST': {'min': 0.5, 'max': 20.0, 'ratio_max': 3.0}
    }

    params = umbrales.get(target, umbrales['PTS'])

    # Predicción fuera de rango absoluto
    if prediccion < params['min']:
        return False, f"Predicción {prediccion:.1f} demasiado baja para {target}"
    if prediccion > params['max']:
        return False, f"Predicción {prediccion:.1f} demasiado alta para {target}"

    # Predicción muy alejada del promedio histórico
    if avg_historico > 0:
        ratio = prediccion / avg_historico
        if ratio > params['ratio_max']:
            return False, f"Predicción {prediccion:.1f} es {ratio:.1f}x el promedio ({avg_historico:.1f})"
        if ratio < 1 / params['ratio_max']:
            return False, f"Predicción {prediccion:.1f} es solo {ratio:.1f}x el promedio ({avg_historico:.1f})"

    return True, ""


def analizar_pick_prop(prediccion_resultado: dict,
                        linea_casa: float,
                        odds_over: float,
                        odds_under: float,
                        bankroll: float) -> dict | None:
    """
    Analiza si hay valor en Over o Under para una prop.
    Retorna pick con stake si hay edge, None si no hay valor.
    """
    prediccion = prediccion_resultado['prediccion']
    mae        = prediccion_resultado['mae']
    confianza  = prediccion_resultado.get('confianza', 'MEDIA')
    es_gtd     = prediccion_resultado.get('es_gtd', False)
    target     = prediccion_resultado.get('target', 'PTS')
    avg_historico = prediccion_resultado.get('avg_historico', prediccion)

    # ── FILTRO: Predicciones absurdas ──
    es_valida, razon = validar_prediccion(prediccion, target, avg_historico)
    if not es_valida:
        print(f"  ⚠️  Predicción filtrada: {razon}")
        return None

    # ── CÁLCULO DE PROBABILIDADES CORREGIDO ──
    # Usar desviación estándar histórica como sigma, no MAE
    # El MAE subestima la varianza real, multiplicar por 1.25 para aproximar STD
    from scipy.stats import norm

    # Sigma basado en STD histórica (del modelo) con floor de 3.0 para props
    std_historico = prediccion_resultado.get('std_historico', mae * 1.25)
    sigma = max(std_historico, 3.0)  # Mínimo 3 puntos de desviación

    # Calcular distancia a la línea en unidades de sigma
    z_score = (prediccion - linea_casa) / sigma

    # Limitar z_score para evitar probabilidades extremas
    # Un z-score de 3 ya da 99.87%, más allá es overconfidence
    z_score = max(min(z_score, 3.0), -3.0)

    # Si prediccion > linea, z_score positivo -> prob_over debe ser alta
    prob_over  = float(norm.cdf(z_score))
    prob_under = float(1 - norm.cdf(z_score))

    # ── FILTRO 3: Probabilidades extremas (overconfidence) ──
    # No confiar en predicciones con >95% de probabilidad
    if prob_over > 0.95 or prob_under > 0.95:
        # Reducir la probabilidad excesiva
        if prob_over > 0.95:
            prob_over = 0.85
            prob_under = 0.15
        else:
            prob_under = 0.85
            prob_over = 0.15

    # ── LÓGICA CORREGIDA: Dirección basada en predicción vs línea ──
    diferencia = prediccion - linea_casa

    # Advertencia si la predicción está muy cerca de la línea
    if abs(diferencia) < 1.5:
        print(f"  [WARN] Baja conviccion: prediccion ({prediccion:.1f}) muy cerca de linea ({linea_casa:.1f})")
        return None  # No generar pick sin convicción clara

    # Determinar lado por lógica de dirección
    if diferencia > 0:
        # Predicción > línea → solo considerar OVER
        lado   = 'OVER'
        prob   = prob_over
        odds   = odds_over
    else:
        # Predicción < línea → solo considerar UNDER
        lado   = 'UNDER'
        prob   = prob_under
        odds   = odds_under

    # Calcular edge solo para el lado lógico
    edge = calcular_edge(prob, odds)

    if edge < MIN_EDGE:
        return None  # Edge insuficiente

    # Kelly y stake
    kelly_pct = kelly_criterion(prob, odds)
    if kelly_pct <= 0:
        return None

    stake = calcular_stake_usd(kelly_pct, bankroll, confianza, es_gtd)
    if stake <= 0:
        return None

    ganancia_potencial = round(stake * (odds - 1), 2)

    return {
        'jugador':            prediccion_resultado.get('jugador', ''),
        'mercado':            prediccion_resultado.get('target', 'PTS'),
        'tipo':               f'PROP {prediccion_resultado.get("target", "PTS")} {lado} {linea_casa}',
        'lado':               lado,
        'linea':              linea_casa,
        'prediccion_modelo':  prediccion,
        'mae':                mae,
        'prob_modelo':        round(prob, 3),
        'odds':               odds,
        'edge_pct':           round(edge * 100, 1),
        'kelly_pct':          round(kelly_pct * 100, 2),
        'stake_usd':          stake,
        'ganancia_potencial': ganancia_potencial,
        'confianza':          confianza,
        'es_gtd':             es_gtd,
        'ajustado_ausencias': prediccion_resultado.get('ajustado', False),
        'ajustes_ausencias':  prediccion_resultado.get('ajustes_ausencias', []),
        'timestamp':          datetime.now().isoformat()
    }


def analizar_pick_total(total_resultado: dict,
                         odds_over: float,
                         odds_under: float,
                         bankroll: float,
                         home_team: str,
                         away_team: str) -> dict | None:
    """Analiza picks de totales O/U."""
    prob_over  = total_resultado['prob_over']
    prob_under = total_resultado['prob_under']
    linea      = total_resultado['linea']

    edge_over  = calcular_edge(prob_over, odds_over)
    edge_under = calcular_edge(prob_under, odds_under)

    if edge_over >= edge_under and edge_over >= MIN_EDGE:
        lado, prob, odds, edge = 'OVER', prob_over, odds_over, edge_over
    elif edge_under > edge_over and edge_under >= MIN_EDGE:
        lado, prob, odds, edge = 'UNDER', prob_under, odds_under, edge_under
    else:
        return None

    kelly_pct = kelly_criterion(prob, odds)
    stake = calcular_stake_usd(kelly_pct, bankroll, 'MEDIA')
    if stake <= 0:
        return None

    return {
        'jugador':            f'{home_team} vs {away_team}',
        'mercado':            'TOTAL',
        'tipo':               f'TOTAL {lado} {linea}',
        'lado':               lado,
        'linea':              linea,
        'prediccion_modelo':  total_resultado['total_esperado'],
        'mae':                None,
        'prob_modelo':        round(prob, 3),
        'odds':               odds,
        'edge_pct':           round(edge * 100, 1),
        'kelly_pct':          round(kelly_pct * 100, 2),
        'stake_usd':          stake,
        'ganancia_potencial': round(stake * (odds - 1), 2),
        'confianza':          'MEDIA',
        'es_gtd':             False,
        'ajustado_ausencias': False,
        'ajustes_ausencias':  [],
        'timestamp':          datetime.now().isoformat()
    }


def analizar_pick_spread(spread_resultado: dict,
                          odds_home: float,
                          odds_away: float,
                          bankroll: float,
                          home_team: str,
                          away_team: str) -> dict | None:
    """Analiza picks de spread/handicap."""
    prob_home = spread_resultado['prob_home_cover']
    prob_away = spread_resultado['prob_away_cover']
    linea     = spread_resultado['linea_spread']

    edge_home = calcular_edge(prob_home, odds_home)
    edge_away = calcular_edge(prob_away, odds_away)

    if edge_home >= edge_away and edge_home >= MIN_EDGE:
        lado, prob, odds, edge = home_team, prob_home, odds_home, edge_home
    elif edge_away > edge_home and edge_away >= MIN_EDGE:
        lado, prob, odds, edge = away_team, prob_away, odds_away, edge_away
    else:
        return None

    kelly_pct = kelly_criterion(prob, odds)
    stake = calcular_stake_usd(kelly_pct, bankroll, 'MEDIA')
    if stake <= 0:
        return None

    return {
        'jugador':            f'{home_team} vs {away_team}',
        'mercado':            'SPREAD',
        'tipo':               f'SPREAD {lado} {linea:+.1f}',
        'lado':               lado,
        'linea':              linea,
        'prediccion_modelo':  spread_resultado['margen_esperado'],
        'mae':                None,
        'prob_modelo':        round(prob, 3),
        'odds':               odds,
        'edge_pct':           round(edge * 100, 1),
        'kelly_pct':          round(kelly_pct * 100, 2),
        'stake_usd':          stake,
        'ganancia_potencial': round(stake * (odds - 1), 2),
        'confianza':          'MEDIA',
        'es_gtd':             False,
        'ajustado_ausencias': False,
        'ajustes_ausencias':  [],
        'timestamp':          datetime.now().isoformat()
    }

# ─────────────────────────────────────────────
# 4. HISTORIAL DE APUESTAS — vía ledger de module8
# ─────────────────────────────────────────────

def guardar_picks_del_dia(picks: list[dict], modo: str = "PAPEL") -> list[int]:
    """
    Registra los picks del día en el ledger (module8). Cada pick de
    analizar_pick_prop se mapea al contrato del ledger. Retorna los ids.
    """
    ids = []
    for p in picks:
        pick_ledger = {
            'jugador':     p.get('jugador', ''),
            'target':      p.get('mercado', 'PTS'),
            'lado':        p.get('lado', ''),
            'linea':       p.get('linea'),
            'odds':        p.get('odds'),
            'pred_media':  p.get('prediccion_modelo'),
            'pred_sigma':  p.get('pred_sigma'),   # None en v1 (llega en Fase 2)
            'prob_modelo': p.get('prob_modelo'),
            'edge_pct':    p.get('edge_pct'),
            'stake':       p.get('stake_usd'),
        }
        ids.append(trk.registrar_pick(pick_ledger, modo=modo))
    return ids


def calcular_estadisticas_historial(modo: str = "PAPEL") -> dict:
    """Estadísticas del historial, derivadas del ledger (module8)."""
    m = trk.metricas(modo)
    if m.get('total_resueltos', 0) == 0:
        return {'mensaje': 'Sin resultados registrados aún'}

    edges = m.get('calibracion_por_edge', {})
    avg_edge = round(
        sum(b['edge_medio'] for b in edges.values()) / len(edges), 1
    ) if edges else 0

    return {
        'total_picks':    m['total_resueltos'],
        'ganadas':        m['ganadas'],
        'perdidas':       m['perdidas'],
        'anuladas':       m['anuladas'],
        'win_rate':       m['win_rate'],
        'apostado_total': m['apostado_total'],
        'roi_pct':        m['roi_pct'],
        'avg_edge_pct':   avg_edge,
    }

# ─────────────────────────────────────────────
# 5. PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def generar_stakes(predicciones: list[dict],
                   lineas_manuales: dict,
                   bankroll_inicial: float | None = None,
                   modo: str = "PAPEL") -> tuple[list[dict], dict, dict]:
    """
    Recibe predicciones del Módulo 2 y líneas ingresadas manualmente.
    v1 procesa SOLO mercados activos (PTS, ADR-001). Registra los picks en
    el ledger con el modo indicado (PAPEL por defecto — sin dinero real).
    Retorna (picks, estado_bankroll_derivado, stats).
    """
    print("\n" + "="*55)
    print("  💰 MÓDULO 3: STAKES ENGINE (Kelly Criterion)")
    print("="*55)

    estado_bankroll = cargar_bankroll(bankroll_inicial, modo)
    bankroll = estado_bankroll['bankroll_actual']
    print(f"\n  💵 Bankroll actual ({modo}): ${bankroll:.2f}")

    picks_con_valor = []

    for pred in predicciones:
        target = pred.get('target', '')
        # v1: solo mercados activos (PTS)
        if target not in PARAMS['mercados_activos']:
            continue

        jugador = pred.get('jugador', '')
        key     = f"{jugador}_{target}"
        if key not in lineas_manuales:
            continue

        datos_linea = lineas_manuales[key]
        linea       = datos_linea.get('linea', 0)
        odds_over   = datos_linea.get('odds_over', 1.87)
        odds_under  = datos_linea.get('odds_under', 1.87)

        pick = analizar_pick_prop(pred, linea, odds_over, odds_under, bankroll)
        if pick:
            picks_con_valor.append(pick)

    # Ordenar por edge descendente
    picks_con_valor.sort(key=lambda x: x['edge_pct'], reverse=True)

    # Registrar en el ledger (modo PAPEL por defecto)
    if picks_con_valor:
        guardar_picks_del_dia(picks_con_valor, modo=modo)

    print(f"\n  ✅ {len(picks_con_valor)} picks con valor encontrados")

    stats = calcular_estadisticas_historial(modo)
    return picks_con_valor, estado_bankroll, stats


if __name__ == "__main__":
    print("Módulo 3 — Stakes Engine (PTS-only, ADR-001)")
    print(f"Parámetros: {PARAMS}")
    print(f"Edge mínimo: {MIN_EDGE*100}% | Máximo por apuesta: {MAX_BET_PCT*100}%")
