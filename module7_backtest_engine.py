# ================================================
#  NBA PREDICTOR — MÓDULO 7: BACKTEST ENGINE
#  Responsabilidad:
#    - Walk-forward honesto (sin data leakage) sobre
#      gamelogs históricos cacheados.
#    - Línea sintética (media móvil L10) como proxy,
#      ya que no hay líneas reales de props históricas.
#    - Métricas: MAE, sesgo, win rate, ROI proxy y
#      CALIBRACIÓN por bucket de edge (la métrica reina).
#  Es MODEL-AGNOSTIC: recibe un `predictor` (media, sigma).
#  Ref: TRD §5, PLAN Fase 1
# ================================================

import glob
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

# Salida UTF-8 robusta: los reportes usan emojis/em-dash que crashean en
# consolas cp1252 (Windows). Reconfigurar evita UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

CACHE_DIR = Path("cache")

# ── Parámetros del backtest (los MISMOS para baseline y pooled) ──
MIN_HISTORIA   = 20     # partidos mínimos de historia antes de evaluar
ODDS_PROXY     = 1.87   # cuota decimal típica de props en Betano
MIN_EDGE       = 0.05   # edge mínimo para considerar que el modelo "apostaría"
SEED           = 42

# Split temporal: los partidos de 2025-26 después de este percentil de fechas
# forman el set de VALIDACIÓN FINAL (intocable hasta el final). Antes de eso,
# todo es set de ITERACIÓN. TRD §5.2.
VALIDACION_DESDE_PCT = 0.70   # último 30% de 2025-26 = validación


# ─────────────────────────────────────────────
# 1. CARGA DE GAMELOGS DESDE CACHE
# ─────────────────────────────────────────────

def cargar_gamelogs_cache(seasons: list[str]) -> dict[str, pd.DataFrame]:
    """
    Carga todos los gamelogs cacheados de las temporadas dadas.
    Clave: "{player_id}_{season}". El backtest NO golpea la API (TRD §7).
    """
    gamelogs = {}
    for season in seasons:
        for ruta in glob.glob(str(CACHE_DIR / f"gamelog_*_{season}.csv")):
            try:
                df = pd.read_csv(ruta)
                if df.empty or 'GAME_DATE' not in df.columns:
                    continue
                df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
                df = df.sort_values('GAME_DATE').reset_index(drop=True)
                # Filtrar DNP (MIN_num == 0) igual que module1
                if 'MIN_num' in df.columns:
                    df = df[pd.to_numeric(df['MIN_num'], errors='coerce').fillna(0) > 0]
                    df = df.reset_index(drop=True)
                if len(df) < MIN_HISTORIA + 1:
                    continue
                pid = Path(ruta).stem.replace('gamelog_', '').replace(f'_{season}', '')
                gamelogs[f"{pid}_{season}"] = df
            except Exception:
                continue
    return gamelogs


def _cutoff_validacion(gamelogs: dict) -> pd.Timestamp | None:
    """Fecha de corte para el split de validación dentro de 2025-26 (TRD §5.2)."""
    fechas = []
    for key, gl in gamelogs.items():
        if key.endswith('2025-26'):
            fechas.append(gl['GAME_DATE'])
    if not fechas:
        return None
    todas = pd.concat(fechas).sort_values()
    return todas.quantile(VALIDACION_DESDE_PCT)


# ─────────────────────────────────────────────
# 1b. SPLIT TEMPORAL COMPARTIDO (para comparar modelos)
# ─────────────────────────────────────────────
# Para comparar baseline vs pooled de forma JUSTA, ambos se evalúan sobre los
# MISMOS puntos de test. Definimos una ventana temporal dentro de 2025-26:
#   TRAIN      : fecha <  T1   (para el pooled)
#   TEST (dev) : T1 <= fecha < T2   ← aquí se comparan los modelos
#   VALIDACIÓN : fecha >= T2 (= VALIDACION_DESDE_PCT, intocable)

TEST_DESDE_PCT = 0.55   # T1: inicio de la ventana de test/dev


def fechas_corte(gamelogs: dict) -> tuple:
    """Retorna (T1, T2): inicio de test y inicio de validación (2025-26)."""
    fechas = [gl['GAME_DATE'] for k, gl in gamelogs.items() if k.endswith('2025-26')]
    if not fechas:
        return None, None
    todas = pd.concat(fechas).sort_values()
    return todas.quantile(TEST_DESDE_PCT), todas.quantile(VALIDACION_DESDE_PCT)


def construir_test_set(gamelogs: dict, t1, t2,
                       max_por_jugador: int | None = 4,
                       min_historia: int = MIN_HISTORIA) -> list:
    """
    Puntos de test compartidos: partidos de 2025-26 con fecha en [T1, T2),
    con al menos `min_historia` de historia previa. Capea por jugador para
    acotar el costo del baseline (que reentrena por punto). Retorna (key, i).
    """
    test_set = []
    for key, gl in gamelogs.items():
        if not key.endswith('2025-26'):
            continue
        candidatos = [i for i in range(min_historia, len(gl))
                      if t1 <= gl.iloc[i]['GAME_DATE'] < t2]
        if max_por_jugador is not None:
            candidatos = candidatos[-max_por_jugador:]
        for i in candidatos:
            test_set.append((key, i))
    return test_set


def evaluar(predict_for, test_set: list, gamelogs: dict,
            verbose: bool = True, etiqueta: str = "") -> dict:
    """
    Evalúa un `predict_for(key, i, historia) -> (media, sigma) | None` sobre un
    test_set fijo. Reusa la línea sintética y las métricas del backtest, para
    que baseline y pooled sean 100% comparables.
    """
    filas = []
    jugadores = set()
    for key, i in test_set:
        gl = gamelogs[key]
        fecha_F = gl.iloc[i]['GAME_DATE']
        historia = gl.iloc[:i]

        # Anti-leakage (assert duro, TRD §5.1)
        assert historia['GAME_DATE'].max() < fecha_F, f"LEAKAGE en {key} idx {i}"

        actual = pd.to_numeric(gl['PTS'], errors='coerce').iloc[i]
        if not np.isfinite(actual):
            continue

        linea = linea_sintetica(pd.to_numeric(historia['PTS'], errors='coerce'))
        pred = predict_for(key, i, historia)
        if pred is None:
            continue
        media, sigma = pred
        if sigma <= 0 or abs(media - linea) < 1e-9:
            continue

        lado = 'OVER' if media > linea else 'UNDER'
        z = (media - linea) / sigma
        prob = float(norm.cdf(z)) if lado == 'OVER' else float(norm.cdf(-z))
        edge = prob * ODDS_PROXY - 1
        gano = (actual > linea) if lado == 'OVER' else (actual < linea)

        filas.append({
            'key': key, 'actual': float(actual), 'pred': media, 'sigma': sigma,
            'linea': linea, 'lado': lado, 'prob': prob, 'edge': edge,
            'gano': bool(gano), 'error': media - float(actual),
        })
        jugadores.add(key)

    if not filas:
        return {"error": "Sin predicciones en el test_set."}

    df = pd.DataFrame(filas)
    resumen = _resumen_metricas(df, len(jugadores), etiqueta or "test-set")
    if verbose:
        _imprimir_resumen(resumen)
    return {"df": df, "resumen": resumen}


# ─────────────────────────────────────────────
# 2. LÍNEA SINTÉTICA (PROXY)
# ─────────────────────────────────────────────

def linea_sintetica(historia_pts: pd.Series) -> float:
    """
    Proxy de la línea de la casa: media móvil de los últimos 10 partidos,
    redondeada a .5. Usa SOLO datos pasados (la serie que se pasa ya está
    recortada a GAME_DATE < F). Documentado como proxy — no es la línea real.
    """
    l10 = historia_pts.tail(10).mean()
    return round(l10 * 2) / 2


# ─────────────────────────────────────────────
# 3. PREDICTORES (interfaz: historia -> (media, sigma) | None)
# ─────────────────────────────────────────────

def predictor_media_movil(historia: pd.DataFrame) -> tuple[float, float] | None:
    """
    Predictor trivial de referencia (rápido): media y std de los últimos 10.
    Sirve para validar la maquinaria del backtest sin depender del modelo real.
    """
    pts = pd.to_numeric(historia['PTS'], errors='coerce').dropna()
    if len(pts) < 5:
        return None
    media = float(pts.tail(10).mean())
    sigma = float(pts.tail(10).std(ddof=1))
    if not math.isfinite(sigma) or sigma < 3.0:
        sigma = 3.0
    return media, sigma


def predictor_baseline_perjugador(historia: pd.DataFrame) -> tuple[float, float] | None:
    """
    Predictor del MODELO ACTUAL (per-jugador, module2). Envuelve
    entrenar_modelo_props para medir la línea base en backtest (Fase 1.3).
    Lento: reentrena XGBoost en cada llamada.
    """
    from module2_prediction_engine import entrenar_modelo_props
    res = entrenar_modelo_props(historia, 'PTS')
    if res is None:
        return None
    sigma = res.get('std_historico') or res.get('mae', 3.0) * 1.25
    return float(res['prediccion']), max(float(sigma), 3.0)


# ─────────────────────────────────────────────
# 4. WALK-FORWARD
# ─────────────────────────────────────────────

def backtest(predictor,
             seasons: list[str] = ("2024-25", "2025-26"),
             split: str = "iteracion",
             min_historia: int = MIN_HISTORIA,
             max_test_por_jugador: int | None = None,
             verbose: bool = True) -> dict:
    """
    Ejecuta el walk-forward para un `predictor` dado.

    split:
      'iteracion'  → excluye el set de validación final (para desarrollar).
      'validacion' → SOLO el set de validación final (usar una sola vez).
      'todo'       → sin filtro de split.

    Anti-leakage (TRD §5.1): para predecir el partido F solo se pasa
    historia con GAME_DATE < F. Se hace un assert por cada predicción.
    """
    np.random.seed(SEED)
    gamelogs = cargar_gamelogs_cache(list(seasons))
    if not gamelogs:
        return {"error": "No hay gamelogs en cache. Corre descargar_historico.py primero."}

    cutoff = _cutoff_validacion(gamelogs)
    filas = []
    n_jugadores = 0

    for key, gl in gamelogs.items():
        season = key.split('_')[-1]
        pts_col = pd.to_numeric(gl['PTS'], errors='coerce')
        n_test = 0

        # Índices de test: desde min_historia hasta el final del gamelog
        indices = range(min_historia, len(gl))
        if max_test_por_jugador is not None:
            indices = list(indices)[-max_test_por_jugador:]

        for i in indices:
            fecha_F = gl.iloc[i]['GAME_DATE']

            # Filtro de split temporal (solo aplica a 2025-26)
            if cutoff is not None and season == '2025-26':
                es_validacion = fecha_F >= cutoff
                if split == 'iteracion' and es_validacion:
                    continue
                if split == 'validacion' and not es_validacion:
                    continue
            elif split == 'validacion' and season != '2025-26':
                continue  # validación vive solo en 2025-26

            historia = gl.iloc[:i]

            # ── ANTI-LEAKAGE (assert duro) ──
            assert historia['GAME_DATE'].max() < fecha_F, \
                f"LEAKAGE: historia incluye fecha >= F en {key} idx {i}"

            actual = pts_col.iloc[i]
            if not np.isfinite(actual):
                continue

            linea = linea_sintetica(pd.to_numeric(historia['PTS'], errors='coerce'))
            pred = predictor(historia)
            if pred is None:
                continue
            media, sigma = pred
            if sigma <= 0:
                continue

            # Dirección y probabilidad del pick
            if abs(media - linea) < 1e-9:
                continue  # sin señal
            lado = 'OVER' if media > linea else 'UNDER'
            z = (media - linea) / sigma
            prob = float(norm.cdf(z)) if lado == 'OVER' else float(norm.cdf(-z))
            edge = prob * ODDS_PROXY - 1

            gano = (actual > linea) if lado == 'OVER' else (actual < linea)

            filas.append({
                'key': key, 'season': season, 'fecha': fecha_F,
                'actual': float(actual), 'pred': media, 'sigma': sigma,
                'linea': linea, 'lado': lado, 'prob': prob, 'edge': edge,
                'gano': bool(gano), 'error': media - float(actual),
            })
            n_test += 1

        if n_test > 0:
            n_jugadores += 1

    if not filas:
        return {"error": "Sin predicciones generadas (¿pocos datos o split vacío?)."}

    df = pd.DataFrame(filas)
    resumen = _resumen_metricas(df, n_jugadores, split)
    if verbose:
        _imprimir_resumen(resumen)
    return {"df": df, "resumen": resumen}


# ─────────────────────────────────────────────
# 5. MÉTRICAS
# ─────────────────────────────────────────────

def _resumen_metricas(df: pd.DataFrame, n_jugadores: int, split: str) -> dict:
    # Sobre TODAS las predicciones: calidad predictiva
    mae  = float(df['error'].abs().mean())
    sesgo = float(df['error'].mean())

    # Sobre los PICKS que el modelo apostaría (edge >= MIN_EDGE)
    picks = df[df['edge'] >= MIN_EDGE].copy()
    n_picks = len(picks)
    if n_picks > 0:
        win_rate = float(picks['gano'].mean())
        # ROI unitario con cuota proxy
        pnl = np.where(picks['gano'], ODDS_PROXY - 1, -1.0)
        roi = float(pnl.sum() / n_picks)
    else:
        win_rate = roi = 0.0

    # Calibración por bucket de edge (¿edge alto gana más?)
    calibracion = {}
    if n_picks >= 6:
        try:
            picks['bucket'] = pd.qcut(picks['edge'], q=3,
                                      labels=['bajo', 'medio', 'alto'],
                                      duplicates='drop')
            for b, g in picks.groupby('bucket', observed=True):
                calibracion[str(b)] = {
                    'n': int(len(g)),
                    'win_rate': round(float(g['gano'].mean()) * 100, 1),
                    'edge_medio': round(float(g['edge'].mean()) * 100, 1),
                }
        except Exception:
            pass

    return {
        'split': split,
        'n_jugadores': n_jugadores,
        'n_predicciones': len(df),
        'mae': round(mae, 2),
        'sesgo': round(sesgo, 2),
        'n_picks': n_picks,
        'win_rate_pct': round(win_rate * 100, 1),
        'break_even_pct': round(1 / ODDS_PROXY * 100, 1),
        'roi_pct': round(roi * 100, 2),
        'calibracion_por_edge': calibracion,
    }


def _imprimir_resumen(r: dict):
    print("\n" + "=" * 55)
    print(f"  🔬 BACKTEST — split: {r['split']}")
    print("=" * 55)
    print(f"  Jugadores          : {r['n_jugadores']}")
    print(f"  Predicciones        : {r['n_predicciones']}")
    print(f"  MAE                : {r['mae']} pts")
    print(f"  Sesgo (pred-real)  : {r['sesgo']:+.2f} pts "
          f"({'sobreestima' if r['sesgo'] > 0 else 'subestima'})")
    print(f"  Picks (edge≥{MIN_EDGE*100:.0f}%)    : {r['n_picks']}")
    print(f"  Win rate           : {r['win_rate_pct']}%  (break-even {r['break_even_pct']}%)")
    print(f"  ROI proxy          : {r['roi_pct']:+.2f}%")
    if r['calibracion_por_edge']:
        print("  Calibración por edge (¿edge alto gana más?):")
        for b in ['bajo', 'medio', 'alto']:
            if b in r['calibracion_por_edge']:
                c = r['calibracion_por_edge'][b]
                print(f"     {b:<6} edge~{c['edge_medio']}%  →  WR {c['win_rate']}%  (n={c['n']})")
    print("=" * 55)


if __name__ == "__main__":
    # Prueba rápida de la maquinaria con el predictor trivial.
    print("Backtest — prueba con predictor de media móvil (rápido)")
    res = backtest(predictor_media_movil, split="todo", verbose=True)
    if "error" in res:
        print(f"  {res['error']}")
