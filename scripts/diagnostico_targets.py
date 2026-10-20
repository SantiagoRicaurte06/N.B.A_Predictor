# ================================================
#  ¿Queda señal explotable en PTS, REB o AST?
#
#  La línea de la casa se aproxima aquí con la media móvil de 10 partidos
#  (misma proxy que usa el backtest). Para tener ventaja hay que predecir
#  el residuo `real - L10` mejor que "cero". Si ese residuo no tiene
#  estructura, NINGÚN modelo puede batir la línea, por bueno que sea.
#
#  Solo lectura sobre el cache.
#      python diagnostico_targets.py
# ================================================

import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import nba_predictor.backtest.walk_forward as bt

SEASONS = ["2024-25", "2025-26"]   # NBA

TARGETS = ["PTS", "REB", "AST"]
VENTANA = 10
MIN_HIST = bt.MIN_HISTORIA


def construir(gamelogs: dict, target: str) -> pd.DataFrame:
    filas = []
    for key, gl in gamelogs.items():
        y = pd.to_numeric(gl.get(target), errors="coerce")
        if y is None or y.isna().all():
            continue
        mins = pd.to_numeric(gl.get("MIN_num"), errors="coerce")
        for i in range(MIN_HIST, len(gl)):
            hist = y.iloc[:i]
            l10 = hist.tail(VENTANA).mean()
            if not np.isfinite(l10):
                continue
            filas.append({
                "key": key,
                "real": float(y.iloc[i]),
                "l10": float(l10),
                "resid": float(y.iloc[i] - l10),
                # candidatos a explicar el residuo, todos con datos previos
                "resid_prev": float(y.iloc[i - 1] - hist.iloc[:-1].tail(VENTANA).mean())
                              if i > MIN_HIST else np.nan,
                "min_l10": float(mins.iloc[:i].tail(VENTANA).mean()) if mins is not None else np.nan,
                "tendencia": float(hist.tail(3).mean() - l10),
                "casa": 1 if "vs." in str(gl.iloc[i].get("MATCHUP", "")) else 0,
            })
    return pd.DataFrame(filas)


def main():
    gamelogs = bt.cargar_gamelogs_cache(SEASONS)
    print(f"Gamelogs: {len(gamelogs)} jugadora-temporada\n")

    print(f"{'target':>6} {'n':>7} {'media':>7} {'sd real':>8} {'sd resid':>9} "
          f"{'ratio':>7} {'autocorr':>9} {'r casa':>7} {'r tend':>7}")
    print("-" * 78)

    resumen = {}
    for t in TARGETS:
        d = construir(gamelogs, t).dropna(subset=["resid"])
        if d.empty:
            print(f"{t:>6}  sin datos")
            continue

        sd_real = d["real"].std()
        sd_res = d["resid"].std()
        # ratio < 1 significa que la L10 ya explica parte de la varianza
        ratio = sd_res / sd_real
        # ¿el residuo de hoy se parece al de ayer? Si ~0, no hay memoria que explotar
        ac = d[["resid", "resid_prev"]].dropna().corr().iloc[0, 1]
        r_casa = d["resid"].corr(d["casa"])
        r_tend = d["resid"].corr(d["tendencia"])
        resumen[t] = dict(n=len(d), sd_res=sd_res, ac=ac, r_casa=r_casa, r_tend=r_tend)

        print(f"{t:>6} {len(d):>7,} {d['real'].mean():>7.2f} {sd_real:>8.2f} "
              f"{sd_res:>9.2f} {ratio:>7.2f} {ac:>9.3f} {r_casa:>7.3f} {r_tend:>7.3f}")

    print("\nCómo leerlo:")
    print("  autocorr : correlación del residuo con el del partido anterior.")
    print("             ~0 = la desviación sobre la media móvil es ruido puro.")
    print("  r casa   : correlación del residuo con jugar en casa.")
    print("  r tend   : correlación con la tendencia reciente (L3 - L10).")
    print("  Para batir la línea hace falta que ALGUNA de estas sea claramente")
    print("  distinta de cero. |r| < 0.05 no es explotable con esta muestra.")

    # ── Referencia: cuánto se paga por acertar ──
    print(f"\nUmbral de rentabilidad con cuota {bt.ODDS_PROXY}: "
          f"{1 / bt.ODDS_PROXY:.1%} de aciertos.")
    print("Una correlación de 0.05 mueve el acierto menos de 1 punto porcentual.")

    # ── Asimetría de la línea sintética por target ──
    print("\nSesgo de la línea sintética (media móvil) por target:")
    for t in TARGETS:
        d = construir(gamelogs, t).dropna(subset=["resid"])
        if d.empty:
            continue
        over = (d["real"] > d["l10"]).mean()
        print(f"  {t:>4}: {over:.1%} de partidos por encima  "
              f"(50 % sería simétrico)")
    print("  OJO: es un artefacto de usar la MEDIA con distribuciones sesgadas.")
    print("  Una casa real coloca la línea cerca de la MEDIANA, así que este")
    print("  desbalance NO existe contra una línea de verdad.")


if __name__ == "__main__":
    main()
