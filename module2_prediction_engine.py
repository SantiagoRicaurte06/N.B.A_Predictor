# ================================================
#  NBA PREDICTOR — MÓDULO 2: PREDICTION ENGINE
#  Responsabilidad:
#    - Feature engineering por mercado
#    - Modelos ML: Props, Totales O/U, Spread
#    - Ajuste por ausencias
#    - Calibración de probabilidades
# ================================================

import pandas as pd
import numpy as np
import warnings
from datetime import datetime
warnings.filterwarnings('ignore')

from xgboost import XGBRegressor, XGBClassifier
from sklearn.linear_model import PoissonRegressor, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, accuracy_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV
from scipy.stats import poisson as poisson_dist

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

VENTANA = 10       # rolling window principal
VENTANA_CORTA = 5  # rolling window reciente
MIN_JUEGOS = 5     # mínimo para entrenar (reducido por filtro de 2 meses)

# ─────────────────────────────────────────────
# NUEVAS FEATURES CRÍTICAS (v2)
# ─────────────────────────────────────────────
# 1. Defensive Rating del rival: cuántos puntos permite el oponente
# 2. Pace del partido: posesiones por 48 min (infla stats)
# 3. Usage Rate: % de posesiones que terminan en el jugador

# ─────────────────────────────────────────────
# 1. FEATURE ENGINEERING — PROPS INDIVIDUALES
# ─────────────────────────────────────────────

def calcular_usage_rate(row: pd.Series) -> float:
    """
    Calcula Usage Rate: % de posesiones del equipo que terminan en el jugador.
    Fórmula aproximada: (FGA + 0.44 * FTA + TOV) / posesiones_equipo
    Usamos team_FGA como proxy si no hay posesiones.
    """
    fga = row.get('FGA', 0) or 0
    fta = row.get('FTA', 0) or 0
    tov = row.get('TOV', 0) or 0

    # Team FGA como proxy de posesiones (correlación ~0.92)
    team_fga = row.get('TEAM_FGA', row.get('FGA', 1)) or 1

    if team_fga <= 0:
        return 0.0

    usage = (fga + 0.44 * fta + tov) / team_fga
    return round(usage, 3)


def calcular_rebound_rate(row: pd.Series, is_offensive: bool = False) -> float:
    """
    Calcula Rebound Rate: % de rebotes disponibles capturados.
    Rebotes ofensivos y defensivos por separado son más predictivos.
    """
    reb = row.get('REB', 0) or 0
    oreb = row.get('OREB', 0) or 0
    dreb = row.get('DREB', 0) or 0

    team_reb = row.get('TEAM_REB', row.get('REB', 1)) or 1
    opponent_reb = row.get('OPP_REB', row.get('REB', 1)) or 1

    if is_offensive:
        # Rebotes ofensivos / rebotes ofensivos totales disponibles
        total_oreb_avail = row.get('TEAM_OREB', 1) or 1
        return round(oreb / total_oreb_avail, 3) if total_oreb_avail > 0 else 0.0
    else:
        # Rebotes defensivos / rebotes defensivos totales disponibles
        total_dreb_avail = row.get('TEAM_DREB', 1) or 1
        return round(dreb / total_dreb_avail, 3) if total_dreb_avail > 0 else 0.0


def calcular_pace_proxy(df: pd.DataFrame) -> pd.Series:
    """
    Calcula Pace (posesiones por 48 min) usando fórmula simplificada.
    Pace = (FGA + 0.44 * FTA + TOV - OREB) * 48 / MIN
    Valores altos (>100) = partido rápido = más oportunidades de stats.
    """
    if 'MIN_num' not in df.columns:
        return pd.Series([95.0] * len(df), index=df.index)

    fga = pd.to_numeric(df['FGA'], errors='coerce').fillna(0)
    fta = pd.to_numeric(df['FTA'], errors='coerce').fillna(0)
    tov = pd.to_numeric(df['TOV'], errors='coerce').fillna(0)
    oreb = pd.to_numeric(df['OREB'], errors='coerce').fillna(0)
    min_played = df['MIN_num'].replace(0, 48)

    pace = (fga + 0.44 * fta + tov - oreb) * 48 / min_played
    return pace.fillna(95.0)


def detectar_back_to_back(df: pd.DataFrame) -> pd.Series:
    """
    Detecta si un partido es back-to-back (días entre juegos = 1).
    Retorna serie booleana: True = es B2B.
    """
    if 'GAME_DATE' not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    dates = pd.to_datetime(df['GAME_DATE'])
    days_diff = dates.diff().dt.days
    # B2B = 1 día de diferencia (jugar noche de por medio)
    return (days_diff == 1).fillna(False)


def calcular_minutes_restriction(row: pd.Series,
                                  fecha_ultimo_juego: datetime | None,
                                  fecha_regreso_lesion: datetime | None) -> float:
    """
    Calcula factor de restricción de minutos si el jugador viene de lesión.
    Retorna factor 0.0 - 1.0 para multiplicar la predicción de minutos.

    Si el partido actual está cerca de la fecha de regreso, aplicar restricción.
    """
    if fecha_regreso_lesion is None or fecha_ultimo_juego is None:
        return 1.0  # Sin restricción

    # Días desde el regreso de lesión
    dias_desde_regreso = (fecha_ultimo_juego - fecha_regreso_lesion).days

    if dias_desde_regreso < 0:
        return 1.0  # Partido antes del regreso, no aplica

    # Restricción típica: 75% minutos primeros 3 juegos, 85% siguientes 2, 100% después
    if dias_desde_regreso <= 7:
        return 0.75  # Primera semana: ~75% minutos
    elif dias_desde_regreso <= 14:
        return 0.85  # Segunda semana: ~85% minutos
    else:
        return 1.0  # Después de 2 semanas: minutos normales


def build_player_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construye features para predicción de props individuales.
    Cada fila = un partido pasado con contexto de los anteriores.

    NUEVAS FEATURES CRÍTICAS (v2):
    - Defensive rating del rival (puntos permitidos por posición)
    - Pace del partido (infla stats en partidos rápidos)
    - Usage rate (% de posesiones que terminan en el jugador)
    - Rebound rate ofensivo/defensivo
    """
    df = df.copy().sort_values('GAME_DATE').reset_index(drop=True)

    # ── Columnas numéricas base
    cols_num = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV',
                'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM',
                'MIN_num', 'PLUS_MINUS']
    for col in cols_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # ── Rolling averages (shift para no filtrar datos futuros)
    for col in ['PTS', 'REB', 'AST', 'FGA', 'FG3A', 'FTA', 'MIN_num']:
        if col not in df.columns:
            continue
        s = df[col].shift(1)
        df[f'avg_{col}_L{VENTANA}']      = s.rolling(VENTANA, min_periods=3).mean()
        df[f'std_{col}_L{VENTANA}']      = s.rolling(VENTANA, min_periods=3).std()
        df[f'avg_{col}_L{VENTANA_CORTA}'] = s.rolling(VENTANA_CORTA, min_periods=2).mean()

    # ── Tendencia: ¿está caliente o frío?
    for col in ['PTS', 'REB', 'AST']:
        if f'avg_{col}_L{VENTANA}' in df.columns and f'avg_{col}_L{VENTANA_CORTA}' in df.columns:
            df[f'trend_{col}'] = (
                df[f'avg_{col}_L{VENTANA_CORTA}'] - df[f'avg_{col}_L{VENTANA}']
            )

    # ── Eficiencia de tiro
    if 'FGM' in df.columns and 'FGA' in df.columns:
        df['FG_PCT_calc'] = (df['FGM'] / df['FGA'].replace(0, np.nan)).fillna(0)
        df['avg_FG_PCT_L10'] = df['FG_PCT_calc'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ── Contexto del partido
    df['is_home'] = df['MATCHUP'].str.contains('vs.', na=False).astype(int)
    df['WL_bin']  = (df['WL'] == 'W').astype(int)
    df['win_rate_L10'] = df['WL_bin'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ── Descanso
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['rest_days'] = df['GAME_DATE'].diff().dt.days.fillna(2).clip(0, 7)

    # ── Número del partido (fatiga de temporada)
    df['game_number'] = range(len(df))

    # ── Double-double flag histórico (contexto de rol)
    if 'PTS' in df.columns and 'REB' in df.columns:
        df['dd_flag'] = ((df['PTS'] >= 10) & (df['REB'] >= 10)).astype(int)
        df['dd_rate_L10'] = df['dd_flag'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ═══════════════════════════════════════════════════════════
    #  NUEVAS FEATURES CRÍTICAS (v2) — Contexto del rival y rol
    # ═══════════════════════════════════════════════════════════

    # ── 1. PACE del partido (infla stats)
    df['pace_game'] = calcular_pace_proxy(df)
    df['avg_pace_L10'] = df['pace_game'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ── 2. OPPONENT PACE (pace del rival en los últimos partidos)
    # Si el rival juega rápido, hay más posesiones = más stats
    # Usamos el pace del juego actual como proxy del opponent pace
    df['opponent_pace'] = df['pace_game']  # Se llenará con datos del rival en module1
    df['avg_opponent_pace_L10'] = df['opponent_pace'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ── 3. BACK-TO-BACK FLAG (fatiga)
    df['is_b2b'] = detectar_back_to_back(df).astype(int)
    df['b2b_last_5'] = df['is_b2b'].shift(1).rolling(5, min_periods=1).sum()  # Cuántos B2B en últimos 5

    # ── 4. MINUTES RESTRICTION (si viene de lesión)
    # Se calcula usando fecha_ultimo_juego y fecha_regreso_lesion que vienen en el df
    if 'fecha_regreso_lesion' in df.columns:
        df['minutes_restriction_factor'] = df.apply(
            lambda row: calcular_minutes_restriction(
                row,
                row.get('GAME_DATE'),
                row.get('fecha_regreso_lesion')
            ), axis=1
        )
    else:
        df['minutes_restriction_factor'] = 1.0

    df['avg_minutes_restriction_L3'] = df['minutes_restriction_factor'].shift(1).rolling(3, min_periods=1).mean()

    # ── 5. USAGE RATE (% de posesiones del equipo que usa el jugador)
    # Necesitamos TEAM_FGA en el dataframe (se agrega desde module1)
    if 'TEAM_FGA' not in df.columns:
        df['TEAM_FGA'] = df['FGA'] * 5  # Estimación grosera si no hay dato
    df['usage_rate'] = df.apply(calcular_usage_rate, axis=1)
    df['avg_usage_L10'] = df['usage_rate'].shift(1).rolling(VENTANA, min_periods=3).mean()

    # ── 6. REBOUND RATE (ofensivo y defensivo por separado)
    if 'OREB' in df.columns and 'DREB' in df.columns:
        df['off_reb_rate'] = df.apply(lambda r: calcular_rebound_rate(r, is_offensive=True), axis=1)
        df['def_reb_rate'] = df.apply(lambda r: calcular_rebound_rate(r, is_offensive=False), axis=1)
        df['avg_off_reb_rate_L10'] = df['off_reb_rate'].shift(1).rolling(VENTANA, min_periods=3).mean()
        df['avg_def_reb_rate_L10'] = df['def_reb_rate'].shift(1).rolling(VENTANA, min_periods=3).mean()

    return df


def get_feature_cols_props(target: str) -> list[str]:
    """Retorna las columnas de features según el target."""
    base = [
        f'avg_PTS_L{VENTANA}', f'std_PTS_L{VENTANA}', f'avg_PTS_L{VENTANA_CORTA}', 'trend_PTS',
        f'avg_REB_L{VENTANA}', f'std_REB_L{VENTANA}', f'avg_REB_L{VENTANA_CORTA}', 'trend_REB',
        f'avg_AST_L{VENTANA}', f'avg_AST_L{VENTANA_CORTA}', 'trend_AST',
        f'avg_MIN_num_L{VENTANA}', f'avg_FGA_L{VENTANA}', f'avg_FG3A_L{VENTANA}',
        f'avg_FTA_L{VENTANA}', 'avg_FG_PCT_L10',
        'is_home', 'win_rate_L10', 'rest_days', 'game_number', 'dd_rate_L10',
        # NUEVAS FEATURES CRÍTICAS (v2)
        'avg_pace_L10',              # partidos rápidos = más stats
        'avg_opponent_pace_L10',     # ritmo del rival
        'avg_usage_L10',             # % de posesiones que usa el jugador
        'is_b2b',                    # back-to-back flag
        'b2b_last_5',                # cuántos B2B en últimos 5 juegos
        'avg_minutes_restriction_L3', # restricción de minutos por lesión
    ]

    # Features específicos por tipo de prop
    if target == 'REB':
        base.extend([
            'avg_off_reb_rate_L10',  # rebote ofensivo
            'avg_def_reb_rate_L10',  # rebote defensivo
        ])

    return base

# ─────────────────────────────────────────────
# 2. MODELOS — PROPS INDIVIDUALES
# ─────────────────────────────────────────────

def entrenar_modelo_props(df: pd.DataFrame, target: str) -> dict | None:
    """
    Entrena modelo XGBoost para predecir una stat individual.
    Retorna dict con modelo, MAE, y metadata.
    """
    df = build_player_features(df)
    feature_cols = [c for c in get_feature_cols_props(target) if c in df.columns]

    df_clean = df[feature_cols + [target]].dropna()

    if len(df_clean) < MIN_JUEGOS:
        return None

    X = df_clean[feature_cols]
    y = df_clean[target]

    modelo = XGBRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        random_state=42,
        verbosity=0
    )

    # Walk-forward validation
    tscv = TimeSeriesSplit(n_splits=3)
    maes = []

    for train_idx, test_idx in tscv.split(X):
        if len(test_idx) < 2:
            continue
        modelo.fit(X.iloc[train_idx], y.iloc[train_idx], verbose=False)
        preds = modelo.predict(X.iloc[test_idx])
        maes.append(mean_absolute_error(y.iloc[test_idx], preds))

    # Entrenar final con todos los datos
    modelo.fit(X, y, verbose=False)

    # Predicción del próximo partido (usando la última fila disponible)
    ultima = df[feature_cols].dropna().tail(1)
    if ultima.empty:
        return None

    prediccion = float(modelo.predict(ultima)[0])
    if prediccion <= 0.5:
        return None

    # Stats históricas para contexto
    avg_historico = float(y.tail(VENTANA).mean())
    std_historico = float(y.tail(VENTANA).std())

    # Validación de outlier: si predicción > 150% del promedio histórico, limitar al 120%
    if avg_historico > 0 and prediccion > 1.5 * avg_historico:
        prediccion_original = prediccion
        prediccion = 1.2 * avg_historico
        print(f"\n  ⚠️  WARNING: Predicción outlier detectada para {target}")
        print(f"      Predicción original: {prediccion_original:.1f}")
        print(f"      Promedio histórico: {avg_historico:.1f}")
        print(f"      Predicción ajustada: {prediccion:.1f} (120% del promedio)\n")

    mae = float(np.mean(maes)) if maes else float(mean_absolute_error(y, modelo.predict(X)))

    return {
        'modelo': modelo,
        'target': target,
        'prediccion': round(prediccion, 1),
        'mae': round(mae, 2),
        'avg_historico': round(avg_historico, 1),
        'std_historico': round(std_historico, 2),
        'n_juegos': len(df_clean),
        'feature_cols': feature_cols,
        'confianza': calcular_confianza_props(mae, std_historico)
    }


def calcular_confianza_props(mae: float, std: float) -> str:
    """Calcula nivel de confianza basado en error relativo al spread."""
    if std == 0:
        return 'BAJA'
    ratio = mae / std
    if ratio < 0.5:
        return 'ALTA'
    elif ratio < 0.75:
        return 'MEDIA'
    else:
        return 'BAJA'

# ─────────────────────────────────────────────
# 3. MODELO — TOTALES O/U (Poisson)
# ─────────────────────────────────────────────

def build_team_features(gamelogs: dict, team_abbrev: str) -> pd.DataFrame | None:
    """
    Agrega stats de equipo desde los gamelogs de sus jugadores All-Star.
    Aproximación: usar el gamelog del equipo directamente.
    """
    # Buscar jugadores de ese equipo
    team_players = []
    for nombre, gl in gamelogs.items():
        if 'Team_Abbreviation' in gl.columns:
            if gl['Team_Abbreviation'].iloc[-1] == team_abbrev:
                team_players.append(gl)

    if not team_players:
        return None

    # Usar el gamelog del primer jugador del equipo como proxy del equipo
    # (mismas fechas, mismos resultados de equipo)
    ref = team_players[0].copy()
    ref = ref.sort_values('GAME_DATE').reset_index(drop=True)

    ref['PTS'] = pd.to_numeric(ref['PTS'], errors='coerce')
    ref['avg_PTS_off_L10'] = ref['PTS'].shift(1).rolling(10, min_periods=3).mean()
    ref['is_home'] = ref['MATCHUP'].str.contains('vs.', na=False).astype(int)
    ref['rest_days'] = ref['GAME_DATE'].diff().dt.days.fillna(2).clip(0, 7)

    return ref


def predecir_total_poisson(avg_pts_home: float,
                            avg_pts_away: float,
                            linea: float) -> dict:
    """
    Modelo Poisson para predecir total de puntos del partido.
    Cada equipo se modela independientemente.
    """
    # Ajuste por ventaja de local (~3-4 pts extra para home)
    lambda_home = avg_pts_home * 1.02
    lambda_away = avg_pts_away * 0.98

    total_esperado = lambda_home + lambda_away

    # Distribución de probabilidades sobre la línea
    # Simular todas las combinaciones de puntajes
    rango = range(70, 180)
    prob_over = 0.0
    prob_under = 0.0

    dist_home = poisson_dist(lambda_home)
    dist_away = poisson_dist(lambda_away)

    for h in rango:
        for a in rango:
            p = dist_home.pmf(h) * dist_away.pmf(a)
            total = h + a
            if total > linea:
                prob_over += p
            elif total < linea:
                prob_under += p

    total_prob = prob_over + prob_under
    if total_prob > 0:
        prob_over  = prob_over / total_prob
        prob_under = prob_under / total_prob

    return {
        'total_esperado': round(total_esperado, 1),
        'lambda_home': round(lambda_home, 1),
        'lambda_away': round(lambda_away, 1),
        'prob_over': round(prob_over, 3),
        'prob_under': round(prob_under, 3),
        'linea': linea
    }

# ─────────────────────────────────────────────
# 4. MODELO — SPREAD / HANDICAP
# ─────────────────────────────────────────────

def predecir_spread(avg_pts_home: float,
                     avg_pts_away: float,
                     avg_def_home: float,
                     avg_def_away: float,
                     linea_spread: float) -> dict:
    """
    Predice el margen de victoria (home - away).
    Combina potencial ofensivo vs defensivo del rival.
    """
    # Puntos esperados ajustados por defensa rival
    pts_home_esperados = (avg_pts_home + avg_def_away) / 2 * 1.02  # ventaja local
    pts_away_esperados = (avg_pts_away + avg_def_home) / 2 * 0.98

    margen_esperado = pts_home_esperados - pts_away_esperados

    # Incertidumbre del modelo (basada en varianza histórica típica NBA)
    sigma = 12.0  # desviación estándar típica de márgenes NBA

    # Probabilidad de cubrir el spread
    from scipy.stats import norm
    prob_home_cover = float(norm.cdf(
        (margen_esperado - linea_spread) / sigma
    ))

    return {
        'margen_esperado': round(margen_esperado, 1),
        'pts_home_esperados': round(pts_home_esperados, 1),
        'pts_away_esperados': round(pts_away_esperados, 1),
        'prob_home_cover': round(prob_home_cover, 3),
        'prob_away_cover': round(1 - prob_home_cover, 3),
        'linea_spread': linea_spread
    }

# ─────────────────────────────────────────────
# 5. CONVERSIÓN DE PROBABILIDADES
# ─────────────────────────────────────────────

def prob_to_decimal_odds(prob: float) -> float:
    """Convierte probabilidad a odds decimales (formato Betano)."""
    if prob <= 0 or prob >= 1:
        return 0.0
    return round(1 / prob, 2)


def calcular_edge(prob_modelo: float, odds_casa: float) -> float:
    """
    Calcula el edge esperado vs la línea de la casa.
    Edge = (prob_modelo * odds_casa) - 1
    Positivo = valor a favor del apostador.
    """
    if odds_casa <= 1:
        return 0.0
    return round((prob_modelo * odds_casa) - 1, 4)


def linea_to_prob(odds_decimal: float) -> float:
    """Convierte odds decimales a probabilidad implícita."""
    if odds_decimal <= 0:
        return 0.5
    return round(1 / odds_decimal, 4)

# ─────────────────────────────────────────────
# 6. PREDICCIÓN CON AJUSTE DE AUSENCIAS
# ─────────────────────────────────────────────

def ajustar_por_defensive_rating(prediccion: float,
                                  target: str,
                                  opponent_stats: dict | None) -> tuple[float, dict]:
    """
    Ajusta la predicción según el defensive rating del rival.
    opponent_stats: dict con 'opp_pts_per_game', 'opp_reb_per_game', etc.

    Retorna: (prediccion_ajustada, info_ajuste)
    """
    if opponent_stats is None:
        return prediccion, {'razon': 'Sin datos del rival'}

    ajuste_info = {'razon': 'Ajuste por defensive rating', 'factor': 1.0}

    # Defensive rating relativo al promedio de liga (~114 pts/100 poss en 2025-26)
    league_avg = 114.0

    if target == 'PTS':
        opp_pts_allowed = opponent_stats.get('opp_pts_per_game', league_avg)
        # Si el rival permite más puntos → inflar predicción
        factor = opp_pts_allowed / league_avg
        factor = np.clip(factor, 0.85, 1.15)  # Máximo ±15%

    elif target == 'REB':
        opp_reb_allowed = opponent_stats.get('opp_reb_per_game', 44.0)
        league_avg_reb = 44.0
        factor = opp_reb_allowed / league_avg_reb
        factor = np.clip(factor, 0.85, 1.15)

    elif target == 'AST':
        opp_ast_allowed = opponent_stats.get('opp_ast_per_game', 27.0)
        league_avg_ast = 27.0
        factor = opp_ast_allowed / league_avg_ast
        factor = np.clip(factor, 0.85, 1.15)

    else:
        return prediccion, ajuste_info

    prediccion_ajustada = prediccion * factor
    ajuste_info['factor'] = round(factor, 3)
    ajuste_info['cambio'] = round(prediccion_ajustada - prediccion, 1)

    return round(prediccion_ajustada, 1), ajuste_info


def predecir_con_ausencias(nombre: str,
                            resultado_modelo: dict,
                            efectos_ausencia: dict,
                            jugadores_ausentes: list[str],
                            opponent_stats: dict | None = None,
                            minutes_restriction: float | None = None) -> dict:
    """
    Ajusta la predicción de un jugador considerando:
    1. Ausencias de compañeros de equipo
    2. Defensive rating del rival
    3. Minutes restriction si viene de lesión (NUEVO)
    """
    if not jugadores_ausentes and opponent_stats is None and minutes_restriction is None:
        return resultado_modelo

    resultado_ajustado = resultado_modelo.copy()
    ajustes_aplicados = []

    # 1. Ajuste por ausencias de compañeros
    for ausente in jugadores_ausentes:
        if ausente in efectos_ausencia.get(nombre, {}):
            ajustes = efectos_ausencia[nombre][ausente]
            target = resultado_modelo['target']

            if target in ajustes:
                mult = ajustes[target]
                pred_anterior = resultado_ajustado['prediccion']
                resultado_ajustado['prediccion'] = round(
                    resultado_ajustado['prediccion'] * mult, 1
                )
                ajustes_aplicados.append({
                    'tipo': 'ausencia',
                    'ausente': ausente,
                    'multiplicador': mult,
                    'cambio': round(resultado_ajustado['prediccion'] - pred_anterior, 1)
                })

    # 2. Ajuste por defensive rating del rival
    target = resultado_ajustado['target']
    if opponent_stats is not None:
        pred_anterior = resultado_ajustado['prediccion']
        resultado_ajustado['prediccion'], def_info = ajustar_por_defensive_rating(
            pred_anterior, target, opponent_stats
        )
        if def_info.get('factor', 1.0) != 1.0:
            ajustes_aplicados.append({
                'tipo': 'defensive_rating',
                'factor': def_info['factor'],
                'cambio': def_info['cambio']
            })

    # 3. Ajuste por minutes restriction (si viene de lesión)
    if minutes_restriction is not None and minutes_restriction < 1.0:
        pred_anterior = resultado_ajustado['prediccion']
        resultado_ajustado['prediccion'] = round(pred_anterior * minutes_restriction, 1)
        ajustes_aplicados.append({
            'tipo': 'minutes_restriction',
            'factor': round(minutes_restriction, 2),
            'cambio': round(resultado_ajustado['prediccion'] - pred_anterior, 1)
        })

    resultado_ajustado['ajustes_ausencias'] = ajustes_aplicados
    resultado_ajustado['ajustado'] = len(ajustes_aplicados) > 0

    return resultado_ajustado

# ─────────────────────────────────────────────
# 7. PIPELINE PRINCIPAL DE PREDICCIONES
# ─────────────────────────────────────────────

def generar_predicciones(datos: dict) -> list[dict]:
    """
    Genera todas las predicciones del día.
    Recibe el output del Módulo 1 y retorna lista de predicciones.
    """
    print("\n" + "="*55)
    print("  🤖 MÓDULO 2: PREDICTION ENGINE")
    print("="*55)

    gamelogs        = datos['gamelogs']
    efectos_ausencia = datos['efectos_ausencia']
    jugadores_hoy   = datos['jugadores_hoy']

    # Identificar quiénes están fuera hoy
    ausentes_hoy = [
        j['nombre'] for j in jugadores_hoy if not j['disponible']
    ]

    if ausentes_hoy:
        print(f"\n  ❌ Ausentes detectados: {', '.join(ausentes_hoy)}")
        print("  → Ajustando predicciones de compañeros...\n")

    predicciones = []

    disponibles = [j for j in jugadores_hoy if j['disponible']]
    print(f"  → Generando predicciones para {len(disponibles)} jugadores...\n")

    for jugador_info in disponibles:
        nombre = jugador_info['nombre']

        if nombre not in gamelogs:
            continue

        gl = gamelogs[nombre]
        print(f"  🏀 {nombre}", end='')
        if jugador_info['es_gtd']:
            print(f" ⚠️  GTD", end='')
        print()

        # Props: Puntos
        for target in ['PTS', 'REB', 'AST']:
            resultado = entrenar_modelo_props(gl, target)
            if resultado is None:
                continue

            # Ajustar por ausencias de compañeros
            resultado = predecir_con_ausencias(
                nombre, resultado, efectos_ausencia, ausentes_hoy
            )

            resultado['jugador'] = nombre
            resultado['es_gtd']  = jugador_info['es_gtd']
            resultado['mercado'] = f'PROP_{target}'
            predicciones.append(resultado)

    print(f"\n  ✅ {len(predicciones)} predicciones generadas")
    return predicciones


if __name__ == "__main__":
    # Test con datos mock
    print("Módulo 2 cargado correctamente.")
    print("Importar y llamar generar_predicciones(datos) para usar.")
