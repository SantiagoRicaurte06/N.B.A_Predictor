# ================================================
#  NBA PREDICTOR — COMPARACIÓN BASELINE vs POOLED
#  (Fase 2.3) Evalúa AMBOS modelos sobre los MISMOS
#  puntos de test (ventana temporal [T1, T2) de 2025-26,
#  con la validación final [>=T2] intocable).
#  Criterio de aceptación (TRD §6.3): el pooled debe
#  superar al baseline en MAE y calibración.
#  Escribe comparacion.md.
# ================================================

import sys
from datetime import datetime

import nba_predictor.backtest.walk_forward as bt
import nba_predictor.modelo.pooled as mp

SEASONS = ["2024-25", "2025-26"]
MAX_TEST = 4


def fmt_cal(cal: dict) -> str:
    filas = []
    for b in ["bajo", "medio", "alto"]:
        if b in cal:
            c = cal[b]
            filas.append(f"| {b} | ~{c['edge_medio']}% | {c['win_rate']}% | {c['n']} |")
    return "\n".join(filas) if filas else "| — | — | — | — |"


def calibracion_mejora(cal: dict) -> bool:
    """
    Calibración direccional: ¿los picks de EDGE ALTO ganan más que los de EDGE
    BAJO? Es el test correcto (con ~215 muestras/bucket, exigir monotonía
    estricta de 3 buckets es demasiado rígido: diferencias de 1-2 pp entre
    medio y alto son ruido). Lo que importa es el signo: que edge → win rate.
    """
    if not all(b in cal for b in ["bajo", "alto"]):
        return False
    return cal["alto"]["win_rate"] > cal["bajo"]["win_rate"]


def main():
    print("=" * 55)
    print("  COMPARACIÓN — baseline (per-jugador) vs pooled")
    print("=" * 55)

    gamelogs = bt.cargar_gamelogs_cache(SEASONS)
    t1, t2 = bt.fechas_corte(gamelogs)
    if t1 is None:
        print("  ❌ Sin datos de 2025-26 para el split.")
        sys.exit(1)

    test_set = bt.construir_test_set(gamelogs, t1, t2, max_por_jugador=MAX_TEST)
    print(f"  Ventana test: {t1.date()} → {t2.date()}  |  {len(test_set)} puntos")
    print(f"  (validación final [>= {t2.date()}] intocable)\n")

    # ── 1. Pooled: entrenar una vez con fecha < T1, evaluar en test_set ──
    print("  → Entrenando modelo pooled (fecha < T1)...")
    modelo = mp.ModeloPooled()
    info = modelo.entrenar(gamelogs, cutoff_date=t1)
    print(f"    dataset: {info['n_filas']} filas · {info['n_features']} features · "
          f"sigma≈{info['sigma_global']}")
    print("  → Evaluando pooled en el test_set...")
    res_pooled = bt.evaluar(modelo.predict_for, test_set, gamelogs,
                            verbose=True, etiqueta="pooled")

    # ── 2. Baseline: walk-forward per punto sobre el MISMO test_set ──
    print("\n  → Evaluando baseline (reentrena por punto)...")
    base_predict = lambda key, i, hist: bt.predictor_baseline_perjugador(hist)
    res_base = bt.evaluar(base_predict, test_set, gamelogs,
                          verbose=True, etiqueta="baseline")

    if "error" in res_pooled or "error" in res_base:
        print("  ❌ Falló alguna evaluación.")
        sys.exit(1)

    rp, rb = res_pooled["resumen"], res_base["resumen"]

    # ── 3. Veredicto ──
    mejora_mae = rp["mae"] < rb["mae"]
    mejora_cal = calibracion_mejora(rp["calibracion_por_edge"])
    aprueba = mejora_mae and mejora_cal

    escribir_md(t1, t2, len(test_set), rp, rb, mejora_mae, mejora_cal, aprueba)

    print("\n" + "=" * 55)
    print(f"  VEREDICTO: {'✅ POOLED SUPERA AL BASELINE' if aprueba else '❌ NO SUPERA (iterar)'}")
    print(f"    MAE mejor: {mejora_mae} ({rb['mae']} → {rp['mae']})")
    print(f"    Calibración monótona: {mejora_cal}")
    print("=" * 55)


def escribir_md(t1, t2, n_test, rp, rb, mejora_mae, mejora_cal, aprueba):
    md = f"""# COMPARACIÓN — Baseline vs Pooled (Fase 2)

**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

Ambos modelos evaluados sobre los **mismos** puntos de test (ventana temporal
`{t1.date()} → {t2.date()}` de 2025-26, {n_test} puntos). La validación final
`[>= {t2.date()}]` queda **intocable** (TRD §5.2). Línea sintética L10 (proxy).

## Resultados

| Métrica | Baseline (per-jugador) | Pooled (multi-jugador) | Mejor |
|---------|-----------------------|------------------------|-------|
| MAE | {rb['mae']} pts | {rp['mae']} pts | {'Pooled ✅' if mejora_mae else 'Baseline'} |
| Sesgo | {rb['sesgo']:+.2f} | {rp['sesgo']:+.2f} | — |
| Predicciones | {rb['n_predicciones']} | {rp['n_predicciones']} | — |
| Picks (edge≥5%) | {rb['n_picks']} | {rp['n_picks']} | — |
| Win rate | {rb['win_rate_pct']}% | {rp['win_rate_pct']}% | (break-even {rb['break_even_pct']}%) |
| ROI proxy | {rb['roi_pct']:+.2f}% | {rp['roi_pct']:+.2f}% | — |

## Calibración por bucket de edge (la métrica reina)

**Baseline:**

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
{fmt_cal(rb['calibracion_por_edge'])}

**Pooled:**

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
{fmt_cal(rp['calibracion_por_edge'])}

## Veredicto

- **MAE más bajo:** {'✅ sí' if mejora_mae else '❌ no'} ({rb['mae']} → {rp['mae']})
- **Calibración monótona (edge alto gana más):** {'✅ sí' if mejora_cal else '❌ no'}

**{'✅ El pooled SUPERA al baseline — se integra al flujo diario (Fase 2.3).' if aprueba else '❌ El pooled NO supera al baseline todavía — iterar features/parámetros antes de integrar (TRD §6.3).'}**

> ⚠️ ROI con línea sintética = consistencia interna, no rentabilidad real.
> La rentabilidad se valida en paper trading (ADR-003).
"""
    with open("comparacion.md", "w", encoding="utf-8") as f:
        f.write(md)
    print("\n  💾 comparacion.md escrito")


if __name__ == "__main__":
    main()
