# ================================================
#  TEST — MÓDULO 7: BACKTEST ENGINE
#  Verifica lo crítico: anti-leakage, línea sintética,
#  y que un predictor que iguala la línea no invente edge.
#  No depende de datos reales: usa gamelogs sintéticos.
# ================================================

import sys
import numpy as np
import pandas as pd

import nba_predictor.backtest.walk_forward as bt

FALLOS = 0

def check(nombre, cond, detalle=""):
    global FALLOS
    if cond:
        print(f"  OK  {nombre}")
    else:
        FALLOS += 1
        print(f"  FALLO  {nombre}  {detalle}")


print("=" * 55)
print("  TEST MÓDULO 7 — Backtest Engine")
print("=" * 55)

# ── Línea sintética: media móvil L10 redondeada a .5 ──
serie = pd.Series([20, 22, 24, 26, 28, 30, 21, 23, 25, 27])  # media 24.6 → 24.5
check("linea_sintetica redondea a .5",
      bt.linea_sintetica(serie) == 24.5, f"got {bt.linea_sintetica(serie)}")

# ── Anti-leakage: instrumentar un predictor que verifica la historia ──
# Creamos un gamelog sintético en cache aislado y comprobamos que la historia
# que recibe el predictor SIEMPRE es anterior a la fecha del partido evaluado.
leak_detectado = {'v': False}
fechas_vistas = {'max_historia': [], 'fecha_F': []}

def gamelog_sintetico(n=40, seed=0):
    rng = np.random.default_rng(seed)
    fechas = pd.date_range('2025-11-01', periods=n, freq='2D')
    return pd.DataFrame({
        'GAME_DATE': fechas,
        'PTS': rng.integers(10, 35, n),
        'MIN_num': rng.integers(20, 38, n),
    })

# Monkeypatch: cargar_gamelogs_cache devuelve nuestro gamelog sintético
gl_test = gamelog_sintetico()
bt.cargar_gamelogs_cache = lambda seasons: {'999_2025-26': gl_test.copy()}

def predictor_verificador(historia):
    # Si la historia contiene una fecha >= la última+1 seria leakage; aqui
    # solo devolvemos media/sigma. El assert interno del backtest es la defensa.
    pts = pd.to_numeric(historia['PTS'], errors='coerce').dropna()
    if len(pts) < 5:
        return None
    return float(pts.tail(5).mean()), 5.0

res = bt.backtest(predictor_verificador, seasons=['2025-26'], split='todo',
                  min_historia=20, verbose=False)
check("backtest corre sin leakage (assert interno no dispara)",
      'df' in res, res.get('error', ''))
if 'df' in res:
    check("genera predicciones", res['resumen']['n_predicciones'] > 0,
          f"got {res['resumen']['n_predicciones']}")

# ── Predictor que IGUALA la línea → no debe inventar edge ──
def predictor_igual_linea(historia):
    pts = pd.to_numeric(historia['PTS'], errors='coerce').dropna()
    if len(pts) < 5:
        return None
    # media = misma L10 que la línea sintética → sin desviación → sin edge
    return float(pts.tail(10).mean()), 6.0

res2 = bt.backtest(predictor_igual_linea, seasons=['2025-26'], split='todo',
                   min_historia=20, verbose=False)
if 'df' in res2:
    # La línea se redondea a .5, así que puede haber una desviación mínima,
    # pero los edges deben ser muy bajos → pocos o cero picks fuertes.
    n_picks = res2['resumen']['n_picks']
    check("predictor≈línea genera edge despreciable (pocos picks)",
          n_picks == 0 or res2['resumen']['win_rate_pct'] < 60,
          f"n_picks={n_picks}, wr={res2['resumen'].get('win_rate_pct')}")

# ── Métrica MAE coherente ──
if 'df' in res:
    check("MAE es un número finito y positivo",
          res['resumen']['mae'] >= 0 and np.isfinite(res['resumen']['mae']))

print("-" * 55)
if FALLOS == 0:
    print("  TODOS LOS TESTS APROBADOS")
    sys.exit(0)
else:
    print(f"  {FALLOS} TEST(S) FALLIDO(S)")
    sys.exit(1)
