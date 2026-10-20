# ================================================
#  NBA PREDICTOR — LÍNEA BASE (Fase 1.3)
#  Corre el backtest con el MODELO ACTUAL (per-jugador,
#  module2.entrenar_modelo_props) y escribe baseline.md.
#  Es el "antes" contra el que se mide el modelo pooled.
#
#  El modelo actual reentrena XGBoost por cada predicción,
#  así que se acota con --max-test (juegos de test por
#  jugador). El MISMO valor se usará para el pooled, para
#  que la comparación sea sobre los mismos puntos de test.
#  Uso:
#     python correr_baseline.py               # max-test = 4
#     python correr_baseline.py --max-test 6
#  Ref: PLAN Fase 1.3, TRD §6.3
# ================================================

import sys
from datetime import datetime

import nba_predictor.backtest.walk_forward as bt

MAX_TEST_DEFAULT = 4
SEASONS = ["2024-25", "2025-26"]


def _parse_max_test(argv) -> int:
    if "--max-test" in argv:
        try:
            return int(argv[argv.index("--max-test") + 1])
        except (IndexError, ValueError):
            pass
    return MAX_TEST_DEFAULT


def escribir_baseline_md(r: dict, max_test: int):
    """Persiste los números de referencia en baseline.md (se commitea)."""
    cal = r.get("calibracion_por_edge", {})
    cal_lines = []
    for b in ["bajo", "medio", "alto"]:
        if b in cal:
            c = cal[b]
            cal_lines.append(f"| {b} | ~{c['edge_medio']}% | {c['win_rate']}% | {c['n']} |")
    cal_tabla = "\n".join(cal_lines) if cal_lines else "| — | — | — | — |"

    contenido = f"""# LÍNEA BASE — Modelo actual (per-jugador)

**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')} · **Documento:** referencia para comparar el modelo pooled (Fase 2).

Medido con `module7_backtest_engine` sobre el modelo actual
(`module2.entrenar_modelo_props`, un XGBoost por jugador).

## Configuración del backtest
- Temporadas: {', '.join(SEASONS)}
- Split: **iteración** (excluye validación final, TRD §5.2)
- Juegos de test por jugador: **{max_test}** (`--max-test`)
- Línea: **sintética** = media móvil L10 redondeada a .5 (proxy, no línea real)
- Cuota proxy: {bt.ODDS_PROXY} · Edge mínimo para "apostar": {bt.MIN_EDGE*100:.0f}%

## Resultados

| Métrica | Valor |
|---------|-------|
| Jugadores | {r['n_jugadores']} |
| Predicciones | {r['n_predicciones']} |
| **MAE** | **{r['mae']} pts** |
| Sesgo (pred − real) | {r['sesgo']:+.2f} pts |
| Picks (edge ≥ {bt.MIN_EDGE*100:.0f}%) | {r['n_picks']} |
| **Win rate** | **{r['win_rate_pct']}%** (break-even {r['break_even_pct']}%) |
| **ROI proxy** | **{r['roi_pct']:+.2f}%** |

## Calibración por bucket de edge (la métrica reina)

¿Los picks de mayor edge ganan más? Si no, el modelo sobreestima su ventaja.

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
{cal_tabla}

## Criterio de aceptación del pooled (Fase 2)

El modelo pooled debe **superar esta línea base** en:
1. **MAE** más bajo (mejor predicción puntual).
2. **Calibración**: que el win rate suba de bucket bajo → alto (hoy probablemente plano).
3. Idealmente, win rate de picks por encima del break-even ({r['break_even_pct']}%).

> ⚠️ El ROI usa línea sintética, no real: mide *consistencia interna* del modelo,
> no rentabilidad real. La rentabilidad se valida en paper trading (ADR-003).
"""
    with open("baseline.md", "w", encoding="utf-8") as f:
        f.write(contenido)
    print("\n  💾 baseline.md escrito")


def main():
    max_test = _parse_max_test(sys.argv)
    print("=" * 55)
    print("  LÍNEA BASE — modelo actual (per-jugador)")
    print(f"  Reentrenamiento por predicción · max-test={max_test}/jugador")
    print("  (esto tarda: el modelo actual reentrena XGBoost por juego)")
    print("=" * 55)

    res = bt.backtest(
        bt.predictor_baseline_perjugador,
        seasons=SEASONS,
        split="iteracion",
        max_test_por_jugador=max_test,
        verbose=True,
    )
    if "error" in res:
        print(f"  ❌ {res['error']}")
        sys.exit(1)

    escribir_baseline_md(res["resumen"], max_test)


if __name__ == "__main__":
    main()
