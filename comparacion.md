# COMPARACIÓN — Baseline vs Pooled (Fase 2)

**Generado:** 2026-07-27 20:45

Ambos modelos evaluados sobre los **mismos** puntos de test (ventana temporal
`2026-01-22 → 2026-02-21` de 2025-26, 1240 puntos). La validación final
`[>= 2026-02-21]` queda **intocable** (TRD §5.2). Línea sintética L10 (proxy).

## Resultados

| Métrica | Baseline (per-jugador) | Pooled (multi-jugador) | Mejor |
|---------|-----------------------|------------------------|-------|
| MAE | 5.94 pts | 4.98 pts | Pooled ✅ |
| Sesgo | -0.63 | +0.18 | — |
| Predicciones | 1179 | 1240 | — |
| Picks (edge≥5%) | 1019 | 646 | — |
| Win rate | 50.3% | 53.4% | (break-even 53.5%) |
| ROI proxy | -5.86% | -0.13% | — |

## Calibración por bucket de edge (la métrica reina)

**Baseline:**

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
| bajo | ~13.1% | 52.6% | 340 |
| medio | ~30.8% | 51.3% | 339 |
| alto | ~59.6% | 47.1% | 340 |

**Pooled:**

| Bucket | Edge medio | Win rate | N |
|--------|-----------|----------|---|
| bajo | ~7.3% | 44.9% | 216 |
| medio | ~13.3% | 58.4% | 214 |
| alto | ~24.6% | 56.9% | 216 |

## Veredicto

- **MAE más bajo:** ✅ sí (5.94 → 4.98, −16%)
- **Sesgo casi eliminado:** ✅ (−0.63 → +0.18)
- **Calibración con signo correcto (edge alto > edge bajo):** ✅ sí
  - Baseline: alto 47.1% vs bajo 52.6% = **−5.5 pp** (edge anti-predictivo, roto)
  - Pooled: alto 56.9% vs bajo 44.9% = **+12.0 pp** (edge predictivo)
- **ROI proxy:** de −5.86% a −0.13% (dejó de sangrar)

**✅ El pooled SUPERA al baseline en todas las métricas y arregla el defecto central (la calibración invertida). Se integra al flujo diario (Fase 2.3).**

> Nota metodológica: el criterio de calibración es **direccional** (bucket alto >
> bucket bajo), no monotonía estricta de 3 buckets — con ~215 muestras/bucket,
> una diferencia de 1-2 pp entre medio y alto es ruido; lo que importa es que el
> edge tenga el signo correcto.

## Lo que esto NO prueba (honestidad, ADR-003)

- El win rate del pooled (53.4%) está **en el break-even** (53.5%), no por encima.
  Sobre líneas sintéticas el modelo es ~break-even, **no rentable todavía**.
- El ROI usa línea **sintética** (proxy L10), no líneas reales de Betano. Mide
  consistencia interna del modelo, no rentabilidad. Vencer líneas reales es más
  difícil y se valida en **paper trading** (Fase 3), sin arriesgar dinero.

**Conclusión:** el pooled es la decisión correcta a integrar (arregla la raíz del
problema), pero la rentabilidad real sigue por demostrarse en papel.
