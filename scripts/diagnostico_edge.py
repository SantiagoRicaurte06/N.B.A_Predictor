# ================================================
#  DIAGNÓSTICO — ¿por qué los picks de edge alto no ganan?
#
#  Solo lectura: entrena el pooled con el mismo corte que el backtest y
#  analiza el test_set. No escribe nada ni toca el cache.
#
#      python diagnostico_edge.py
# ================================================

import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import nba_predictor.backtest.walk_forward as bt

SEASONS = ["2024-25", "2025-26"]   # NBA
import nba_predictor.modelo.pooled as mp

BREAK_EVEN = 1 / bt.ODDS_PROXY   # 1/1.87 = 53.5 %


def main():
    gamelogs = bt.cargar_gamelogs_cache(SEASONS)
    t1, t2 = bt.fechas_corte(gamelogs)
    test_set = bt.construir_test_set(gamelogs, t1, t2, max_por_jugador=8)

    modelo = mp.ModeloPooled()
    info = modelo.entrenar(gamelogs, cutoff_date=t1)
    res = bt.evaluar(modelo.predict_for, test_set, gamelogs, verbose=False)
    df = res["df"]

    print("=" * 66)
    print(f"  DIAGNÓSTICO — {len(df)} puntos · break-even {BREAK_EVEN:.1%}")
    print("=" * 66)

    # ── 1. ¿La sigma que declara el modelo es la real? ──
    # Si la subestima, la probabilidad sale inflada y el edge es ficticio.
    sigma_declarada = df["sigma"].mean()
    sigma_real = float(np.std(df["pred"] - df["actual"]))
    print("\n1) SIGMA DECLARADA vs REAL")
    print(f"   declarada (in-sample) : {sigma_declarada:.2f}")
    print(f"   real (out-of-sample)  : {sigma_real:.2f}")
    print(f"   ratio                 : {sigma_real / sigma_declarada:.2f}x")
    if sigma_real > sigma_declarada * 1.05:
        print("   -> LA SUBESTIMA: toda probabilidad sale sobreconfiada.")

    # ── 2. Calibración: ¿una prob del 60 % gana el 60 %? ──
    print("\n2) CALIBRACIÓN (prob declarada vs acierto real)")
    df["bucket_prob"] = pd.cut(df["prob"], [0, .55, .60, .65, .70, 1.0])
    cal = df.groupby("bucket_prob", observed=True).agg(
        n=("gano", "size"), prob_media=("prob", "mean"), win_real=("gano", "mean"))
    print(f"   {'prob declarada':>16} {'n':>5} {'esperado':>10} {'real':>8} {'brecha':>8}")
    for b, r in cal.iterrows():
        print(f"   {str(b):>16} {int(r['n']):>5} {r['prob_media']:>9.1%} "
              f"{r['win_real']:>8.1%} {r['win_real'] - r['prob_media']:>+8.1%}")

    # ── 3. ¿Hay asimetría entre OVER y UNDER? ──
    # La línea sintética es una MEDIA móvil y los puntos tienen cola derecha:
    # la mediana queda por debajo de la media, así que los dos lados no son
    # simétricos aunque el modelo los trate igual.
    print("\n3) POR LADO DE LA APUESTA")
    for lado, g in df.groupby("lado"):
        print(f"   {lado:>6}: n={len(g):>4}  win={g['gano'].mean():>6.1%}  "
              f"edge medio={g['edge'].mean():>6.1%}")

    # ── 4. ¿El edge alto es solo "el modelo se aleja más de la línea"? ──
    print("\n4) DISTANCIA A LA LÍNEA vs ACIERTO")
    df["dist"] = (df["pred"] - df["linea"]).abs()
    df["q_dist"] = pd.qcut(df["dist"], 4, labels=["Q1 cerca", "Q2", "Q3", "Q4 lejos"])
    for b, g in df.groupby("q_dist", observed=True):
        print(f"   {str(b):>9}: n={len(g):>4}  dist media={g['dist'].mean():>5.2f} "
              f" win={g['gano'].mean():>6.1%}  |error| medio={(g['pred']-g['actual']).abs().mean():>5.2f}")

    # ── 5. ¿El modelo aporta algo sobre la propia línea? ──
    print("\n5) ¿APORTA EL MODELO SOBRE LA LÍNEA?")
    mae_modelo = (df["pred"] - df["actual"]).abs().mean()
    mae_linea = (df["linea"] - df["actual"]).abs().mean()
    print(f"   MAE del modelo : {mae_modelo:.2f}")
    print(f"   MAE de la línea: {mae_linea:.2f}")
    print(f"   corr(pred, linea) = {df['pred'].corr(df['linea']):.3f}")
    if mae_modelo >= mae_linea:
        print("   -> el modelo NO mejora a la propia línea que intenta batir.")

    # ── 6. Techo teórico: aciertos si conociéramos el signo del error ──
    print("\n6) REFERENCIA")
    over_real = (df["actual"] > df["linea"]).mean()
    print(f"   % de partidos por encima de la línea: {over_real:.1%}")
    print(f"   (si no fuera ~50 %, apostar siempre a un lado ya daría ventaja)")


if __name__ == "__main__":
    main()
