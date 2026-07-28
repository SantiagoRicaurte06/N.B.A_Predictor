# PLAN DE EJECUCIÓN — NBA Predictor Pro v1

**Autor:** Santiago Ricaurte · **Fecha:** 2026-07-24 · **Documentos base:** [PRD.md](PRD.md), [TRD.md](TRD.md), [ADR.md](ADR.md), [DATA_SPEC.md](DATA_SPEC.md)

---

## Contexto

Este documento convierte los 4 documentos autoritativos en trabajo ejecutable, en fases ordenadas.

> ⚠️ **README.md NO es fuente de verdad.** Describe el sistema viejo (Kelly 25%, todos los mercados) y contradice el PRD/ADR (solo PTS, Kelly definido por backtest). No debe usarse como referencia. Se reescribe **al final** (Fase R), cuando el sistema real coincida con lo que va a describir.

**Meta:** sistema de props PTS validable — contabilidad confiable, backtest honesto, modelo pooled — que demuestre edge en papel antes de arriesgar dinero (ADR-003).

**Reglas permanentes:** commits solo a nombre de Santiago (sin coautoría); `cache/` jamás se commitea (contiene la API key).

### Decisiones sobre las preguntas abiertas del TRD §11 (para no bloquear)

| Pregunta | Decisión |
|---|---|
| Líneas históricas de props | No hay fuente gratis fiable → el backtest v1 mide **precisión + calibración** con línea sintética documentada (proxy: media móvil L10). El ROI real se valida en paper trading (TRD §5.4). |
| Estimación de incertidumbre | **Sigma empírico de residuos** por bucket de minutos/volumen. Regresión cuantílica = mejora futura si la calibración sale pobre. |
| Encoding del jugador | Solo features agregadas (rolling L5/L10). Sin embeddings en v1. |
| Horizonte de entrenamiento | Temporada actual (2025-26) + anterior (2024-25), con feature de "temporada" para capturar drift. |

---

## Fase 0 — Higiene y cimientos

### 0.1 `module8_tracking.py` (NUEVO) — contabilidad derivada
- Ledger CSV **append-only** `cache/ledger.csv`, schema TRD §4.4: `id, fecha, jugador, target, lado, linea, odds, pred_media, pred_sigma, prob_modelo, edge_pct, stake, modo (PAPEL/REAL), resultado (W/L/VOID/null), pnl`.
- Funciones: `registrar_pick()`, `registrar_resultado()`, `bankroll_actual()` (suma de pnl — **derivado, nunca almacenado**, ADR-007), `metricas()` (win rate, ROI, por bucket de edge).
- Archivos corruptos (`bankroll.json`, `historial_apuestas.csv`) → renombrar a `*.legacy`. No borrar, no migrar (datos no fiables).

### 0.2 Degradar module5 a solo-diagnóstico (ADR-004)
- Eliminar `aplicar_mejoras_automaticas()` y `cargar_correcciones_activas()` y sus llamadas (dashboard.py las importa en 2 sitios).
- Conservar el análisis (`analizar_por_*`, `generar_reporte`) leyendo ahora del ledger.
- En module3: quitar `MERCADOS_SUSPENDIDOS` y el consumo de correcciones.

### 0.3 Limpiar module3 → PTS-only + modo PAPEL
- `generar_stakes()` procesa solo `target='PTS'`; escribe picks vía module8 con `modo='PAPEL'`.
- Parámetros (Kelly fraction, MIN_EDGE) a un dict `PARAMS` único que el dashboard lee (fin de strings hardcodeados desfasados).

### 0.4 Arreglos de datos (DATA_SPEC §7 / §9) en `module1_data_engine.py`
- **Filtro DNP:** excluir filas con `MIN_num == 0` (§7.1).
- **Normalización de abreviaciones:** función única `normalizar_team()` para todos los cruces (§7.2 — extraer el mapeo que ya existe en `jugador_juega_hoy`).
- **Matching de lesiones:** nombre completo primero, apellido como fallback con warning (§7.3).

### 0.5 Dashboard sincronizado
- Tab Bankroll lee `module8.bankroll_actual()`; textos de riesgo leen `PARAMS`.
- Ocultar tab "Totales & Spread" (fuera de alcance v1; código latente — ADR-001).
- Registro W/L/VOID escribe al ledger.

**Commits:** ~4 (tracking · module5 · module3+params · data fixes+dashboard).

---

## Fase 1 — Backtest Engine (pieza central)

### 1.1 Descarga masiva a cache
- `descargar_historico.py`: gamelogs de jugadores elegibles (≥15 min, ≥15 GP) para 2024-25 y 2025-26 vía `get_player_gamelog()` con su `sleep(0.6)`. Corre UNA vez; el backtest trabaja sobre disco (TRD §7). Reanudable desde lo cacheado.

### 1.2 `module7_backtest_engine.py` (NUEVO)
- **Walk-forward estricto:** para cada fecha F, entrenar solo con `GAME_DATE < F` (TRD §5.1). Reusar `build_player_features()` (ya usa `shift(1)`).
- **Línea sintética:** `linea_proxy = media móvil L10` redondeada a .5, documentada como proxy.
- **Split temporal:** iteración = 2024-25 + primera mitad 2025-26; **validación final = última porción de 2025-26, intocable** (TRD §5.2).
- Salidas (`cache/backtest_resultados.csv` + resumen): MAE, sesgo, win rate vs proxy, **calibración por bucket de edge** (métrica reina).
- Test anti-leakage: assert de que ninguna feature de F usa datos con fecha ≥ F.

### 1.3 Línea base del modelo actual
- Backtest con el modelo per-jugador actual → números de referencia commiteados (`baseline.md`). El "antes" contra el que se mide el rediseño.

**Commits:** ~3 (descarga · engine+tests · baseline).

---

## Fase 2 — Modelo pooled (ADR-002)

### 2.1 Dataset pooled
- Apilar todos los gamelogs (jugador-partido = fila) con features rolling + contexto (`is_home`, `rest_days`, `is_b2b`, pace propio, temporada).
- **Eliminar features fingidas** (DATA_SPEC §7.4): fuera `usage_rate` (TEAM_FGA=FGA×5 inventado), `off/def_reb_rate` (defaults), `opponent_pace` (proxy circular), ajuste por defensive rating (siempre None). Traer datos reales de equipo/rival = mejora post-v1; v1 no alimenta el modelo con ruido.

### 2.2 Entrenamiento y contrato
- `XGBRegressor` sobre miles de filas, `random_state` fijo, hiperparámetros conservadores; validación walk-forward vía module7.
- `pred_sigma` = STD de residuos del walk-forward por bucket (terciles de `avg_MIN_L10`). Salida conforme al contrato TRD §4.2.
- `analizar_pick_prop()` (module3) usa el `pred_sigma` del contrato, no el sigma improvisado del MAE.

### 2.3 Comparación contra baseline
- Mismo backtest, mismas fechas. **Aceptación (TRD §6.3):** pooled > baseline en calibración y MAE. Si no → iterar features ANTES de avanzar (solo sobre el set de iteración, nunca validación).
- Al aprobar: cablear el pooled al flujo diario.

**Commits:** ~3 (dataset · modelo+sigma · integración+comparación).

---

## Fase 3 — Validación en papel

- Flujo diario: cargar datos → ingresar líneas Betano a mano → picks PTS con edge → registrar en ledger (`modo=PAPEL`) → marcar W/L al día siguiente.
- Vista nueva: ROI papel acumulado, win rate vs break-even (~53.5%), calibración en vivo.
- **Gate papel→real:** se fija con los números del backtest (PRD §7); referencia ~100 picks con ROI+. La Fase 4 (dinero real) queda condicionada a aprobar esto — fuera de este plan.

---

## Fase R — Cierre documental (AL FINAL, no antes)

- **Reescribir README.md** para el sistema real resultante: solo PTS, flujo con backtest y paper trading, parámetros reales desde `PARAMS`, módulos 7/8, estructura actualizada. Hacerlo antes sería documentar algo que no existe.
- Actualizar PRD/TRD si alguna decisión cambió durante la ejecución (marcar en ADR como "Sustituida" si aplica).

---

## Verificación por fase

- **F0:** `python test_pipeline.py` verde + tests de module8 (resultados conocidos → pnl/bankroll exactos, caso VOID). Dashboard levanta sin imports rotos ni textos desfasados.
- **F1:** test anti-leakage verde; backtest reproducible (2 corridas → mismos números); baseline commiteado.
- **F2:** reporte pooled vs baseline; pooled ≥ baseline antes de integrar.
- **F3:** un ciclo diario completo end-to-end.
- **FR:** README coincide con el comportamiento observable.
- **Siempre:** `git status` sin archivos de `cache/` (la API key jamás sale).

**Orden estricto: 0 → 1 → 2 → 3 → R.** El backtest antes que el modelo nuevo (línea base honesta); README al final.
