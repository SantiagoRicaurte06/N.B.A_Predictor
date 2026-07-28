# LÍNEA BASE — Modelo actual (per-jugador)

**Generado:** 2026-07-27 20:11 · **Documento:** referencia para comparar el modelo pooled (Fase 2).

Medido con `module7_backtest_engine` sobre el modelo actual
(`module2.entrenar_modelo_props`, un XGBoost por jugador).

## Configuración del backtest
- Temporadas: 2024-25, 2025-26
- Split: **iteración** (excluye validación final, TRD §5.2)
- Juegos de test por jugador: **4** (`--max-test`)
- Línea: **sintética** = media móvil L10 redondeada a .5 (proxy, no línea real)
- Cuota proxy: 1.87 · Edge mínimo para "apostar": 5%

## Resultados

| Métrica | Valor |
|---------|-------|
| Jugadores | 356 |
| Predicciones | 1356 |
| **MAE** | **6.36 pts** |
| Sesgo (pred − real) | -0.80 pts |
| Picks (edge ≥ 5%) | 1193 |
| **Win rate** | **50.8%** (break-even 53.5%) |
| **ROI proxy** | **-5.01%** |

## Calibración por bucket de edge (la métrica reina)

¿Los picks de mayor edge ganan más? Si no, el modelo sobreestima su ventaja.

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
| bajo | ~14.7% | 52.0% | 398 |
| medio | ~34.5% | 50.4% | 397 |
| alto | ~59.9% | 50.0% | 398 |

## Criterio de aceptación del pooled (Fase 2)

El modelo pooled debe **superar esta línea base** en:
1. **MAE** más bajo (mejor predicción puntual).
2. **Calibración**: que el win rate suba de bucket bajo → alto (hoy probablemente plano).
3. Idealmente, win rate de picks por encima del break-even (53.5%).

> ⚠️ El ROI usa línea sintética, no real: mide *consistencia interna* del modelo,
> no rentabilidad real. La rentabilidad se valida en paper trading (ADR-003).
