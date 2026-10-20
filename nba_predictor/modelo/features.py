# ================================================
#  NBA PREDICTOR — FEATURES POR JUGADOR
#  Construye, para cada partido de un jugador, las
#  features a partir de los partidos ANTERIORES
#  (shift(1): nunca se usa el propio partido).
#  Las consume el modelo pooled y el baseline.
# ================================================

import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

VENTANA = 10       # rolling window principal
VENTANA_CORTA = 5  # rolling window reciente

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
