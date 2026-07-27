# TRD — NBA Predictor Pro

**Technical Requirements Document**
**Autor:** Santiago Ricaurte
**Versión:** 1.0
**Fecha:** 2026-07-24
**Documento padre:** [PRD.md](PRD.md)

---

## 1. Propósito

Este documento traduce las decisiones del PRD a requisitos técnicos concretos: stack, arquitectura, contratos de datos, diseño de los componentes nuevos (Backtest Engine y modelo pooled) y las restricciones reales de las fuentes de datos. Es la base técnica sobre la que se construirá el plan de ejecución.

Alcance técnico de v1: **un solo mercado (PTS), local, odds manuales, validación por backtest.**

---

## 2. Stack tecnológico

Basado en `requirements.txt` actual, sin cambios de fondo:

| Capa | Tecnología | Uso |
|------|-----------|-----|
| Lenguaje | Python 3.11+ | Todo el sistema |
| Datos NBA | `nba_api` | Stats de liga, gamelogs, scoreboard |
| Datos externos | `requests` → ESPN API | Injury report, equipos que juegan hoy |
| ML | `xgboost`, `scikit-learn` | Modelos de predicción |
| Estadística | `scipy`, `numpy` | Poisson, Normal, cálculo de probabilidades |
| Datos tabulares | `pandas` | Manejo de gamelogs, features, historial |
| UI | `streamlit` | Dashboard local |
| Persistencia | Archivos locales (CSV/JSON) en `cache/` | Sin base de datos en v1 |

**Decisión técnica:** sin base de datos. Los volúmenes son pequeños (decenas de jugadores/día, cientos de picks) y el uso es personal-local. Archivos planos versionables son suficientes. Reevaluar solo si el paper trading supera ~10k registros.

---

## 3. Arquitectura del sistema

### 3.1 Módulos actuales (se conservan, con cambios)

```
module1_data_engine.py    → Adquisición de datos (NBA + ESPN)
module2_prediction_engine.py → Modelos ML  [REDISEÑO: pooled]
module3_stakes_engine.py  → Kelly + sizing [params desde backtest]
module5_error_analysis.py → Diagnóstico   [DEGRADAR: solo lectura]
module6_odds_engine.py    → Odds          [latente, no crítico]
dashboard.py              → UI Streamlit  [+ vistas backtest/paper]
```

### 3.2 Módulos nuevos

```
module7_backtest_engine.py → Simulación histórica honesta  [NUEVO, crítico]
module8_tracking.py        → Contabilidad de bankroll/paper [NUEVO, reemplaza tracking corrupto]
```

*(Nota: la numeración salta el 4 por historia del proyecto; se respeta para no romper imports existentes.)*

### 3.3 Flujo de datos (uso diario)

```
[nba_api] ──┐
            ├─→ module1 ──→ features ──→ module2 (predicción PTS + incertidumbre)
[ESPN api] ─┘                                        │
                                                     ↓
[líneas Betano, manual] ──────────────→ module3 (edge + Kelly stake)
                                                     │
                                                     ↓
                                          module8 (registro paper/real)
                                                     │
                                                     ↓
                                          module5 (diagnóstico solo-lectura)
```

### 3.4 Flujo de datos (backtest — offline)

```
[gamelogs históricos] ──→ module7:
    para cada partido histórico F de cada jugador:
        1. reconstruir estado conocido ANTES de F (sin leakage)
        2. module2 predice PTS con ese estado
        3. comparar contra línea histórica (o proxy) y resultado real
        4. registrar: predicción, línea, resultado, ¿ganó el pick?
    agregar → win rate, ROI, calibración por bucket de edge
```

---

## 4. Contratos de datos (schemas)

Definir estos contratos explícitamente evita el acoplamiento frágil actual (dicts con claves implícitas).

### 4.1 Gamelog de jugador (salida de module1)
Columnas mínimas garantizadas por fila (un partido):
```
GAME_DATE (datetime), PTS, REB, AST, MIN_num (int),
FGA, FGM, FG3A, FG3M, FTA, FTM, TOV, OREB, DREB,
MATCHUP (str), WL (str), PLAYER_ID (int), TEAM_ABBREVIATION (str)
```

### 4.2 Predicción (salida de module2) — *contrato revisado*
```json
{
  "jugador": "str",
  "player_id": "int",
  "target": "PTS",
  "pred_media": "float",       // valor esperado
  "pred_sigma": "float",       // incertidumbre (NUEVO, crítico para edge)
  "n_juegos_train": "int",
  "fecha_partido": "date",
  "features_version": "str"    // para trazabilidad
}
```
**Cambio clave vs. hoy:** el modelo debe emitir `pred_sigma` (incertidumbre), no solo el valor. El edge depende de la distribución, no del punto.

### 4.3 Pick (salida de module3)
```json
{
  "jugador": "str", "target": "PTS", "lado": "OVER|UNDER",
  "linea": "float", "odds": "float",
  "pred_media": "float", "prob_modelo": "float",
  "edge_pct": "float", "kelly_pct": "float", "stake": "float",
  "modo": "PAPEL|REAL",        // NUEVO: distingue validación de dinero real
  "timestamp": "iso8601"
}
```

### 4.4 Registro histórico (module8)
Un CSV append-only. Cada fila = un pick con su resultado eventual:
```
id, fecha, jugador, target, lado, linea, odds,
pred_media, pred_sigma, prob_modelo, edge_pct, stake,
modo (PAPEL/REAL), resultado (W/L/VOID/null), pnl
```
El bankroll **se deriva** de este registro (suma de pnl), nunca se guarda como número mutable independiente — así se elimina la clase de bug del bankroll corrupto actual.

---

## 5. Backtest Engine (module7) — diseño técnico

Es la pieza central del proyecto. Requisitos:

### 5.1 Anti-leakage (no negociable)
- Para predecir el partido en fecha `F`, el modelo solo puede usar datos con `GAME_DATE < F`.
- Todas las features rolling ya usan `.shift(1)` en module2 — verificar que el backtest respete esto extremo a extremo.
- El modelo pooled (§6) debe entrenarse solo con partidos anteriores a `F` (walk-forward), nunca con el dataset completo.

### 5.2 Split temporal
- Entrenamiento vs. validación separados **por tiempo**, no aleatorio (los datos son series temporales).
- Usar `TimeSeriesSplit` o un corte de fecha explícito.
- **El set de validación final no se toca** hasta terminar de iterar features — para no sobreajustar al backtest.

### 5.3 Métricas de salida
```
- win_rate global y por bucket de edge
- ROI simulado (asumiendo stakes de la política de module3)
- calibración: ¿los picks de edge alto ganan más que los de edge bajo?
- distribución del error (sesgo: ¿sobreestima?)
```

### 5.4 El problema de las líneas históricas de props
**Riesgo técnico principal.** El backtest necesita la línea que Betano ofrecía en cada partido histórico. Opciones, en orden de preferencia:
1. **Líneas históricas reales** si se consiguen (fuente de datos de props históricas — investigar disponibilidad/costo).
2. **Proxy honesto:** derivar una línea sintética desde el promedio de mercado (ej. promedio móvil del jugador) y documentar explícitamente que es una aproximación, no la línea real.
3. Si ninguna es fiable, el backtest mide *calidad predictiva* (MAE, calibración) pero **no** ROI directo; el ROI se valida entonces con paper trading en vivo (§PRD Fase 3).

Este punto debe resolverse temprano: define si el backtest puede medir ROI o solo precisión.

---

## 6. Rediseño del modelo (module2) — pooled multi-jugador

### 6.1 Problema actual
`entrenar_modelo_props()` entrena un `XGBRegressor` (200 árboles, depth 3) sobre 5-40 filas de UN jugador. Con esa relación datos/parámetros, sobreajusta y sobreestima — es la causa raíz del ROI negativo.

### 6.2 Enfoque objetivo
- **Un modelo entrenado con todos los jugadores elegibles a la vez** (miles de partidos-jugador).
- La identidad y forma del jugador entran como **features**, no como partición:
  - promedios rolling (L5, L10) de PTS y drivers (MIN, FGA, usage)
  - contexto: local/visitante, descanso, back-to-back, pace
  - opcional: embedding o encoding del jugador si aporta en backtest
- El modelo predice **media y una estimación de incertidumbre** (`pred_sigma`). Opciones técnicas: modelo de regresión + residual sigma empírico por bucket, o regresión cuantílica (`objective='reg:quantileerror'` en XGBoost, o `GradientBoostingRegressor` con quantile loss).

### 6.3 Criterio de aceptación
El modelo nuevo debe **superar la línea base** (modelo actual medido en backtest, §PRD Fase 1) en calibración y, si hay líneas, en ROI simulado. Si no supera, se itera antes de avanzar.

---

## 7. Fuentes de datos y restricciones

| Fuente | Endpoint | Límite / TTL cache actual |
|--------|----------|---------------------------|
| Stats de liga | `nba_api` `LeagueDashPlayerStats` | rate-limited; cache 12h |
| Gamelog jugador | `nba_api` `PlayerGameLog` | `time.sleep(0.6)` entre llamadas; cache 6h |
| Injury report | ESPN `site.api.espn.com/.../injuries` | cache 2h |
| Equipos hoy | ESPN `.../scoreboard` | cache 4h |
| Odds props | The Odds API | **tier gratis NO da player props** (requiere pago); 500 req/mo |

**Implicaciones técnicas:**
- `nba_api` es frágil y con rate limits → el backtest, que hace muchas llamadas, debe correr **sobre gamelogs ya cacheados en disco**, no golpeando la API en cada iteración. Diseñar un paso de "descarga masiva una vez → backtest sobre cache".
- Odds de props: se asume **entrada manual** en v1. No construir sobre la API de pago.

---

## 8. Deuda técnica a resolver (Fase 0)

Items concretos detectados en la auditoría del código:

1. **Bankroll corrupto:** `cache/bankroll.json` tiene ROI −66% con bankroll subido de $300→$5886 (imposible). Causa probable: `actualizar_bankroll_con_resultado` o edición manual. **Acción:** reemplazar por bankroll derivado del registro (§4.4).
2. **Lazo de auto-mejora (module5):** `aplicar_mejoras_automaticas()` con `MIN_MUESTRA=10` ajusta el sistema sobre ruido. **Acción:** eliminar la aplicación automática; conservar solo el análisis/reporte.
3. **Desfases de texto en UI:** dashboard dice "Kelly 25%" (línea ~646) mientras el código usa 10%. **Acción:** que la UI lea los parámetros reales, no strings hardcodeados.
4. **Features de Totales/Spread semi-conectadas:** `predecir_total_poisson` y `predecir_spread` existen y están en un tab manual, pero fuera del pipeline y sin tracking. **Acción:** dejar fuera de alcance v1 explícitamente (no borrar, marcar como latente).
5. **Contratos implícitos:** los dicts de predicción/pick tienen claves implícitas que rompen fácil. **Acción:** formalizar los schemas de §4.

---

## 9. Testing

- **Smoke tests** (existe `test_pipeline.py`): mantener; verifican que el pipeline corre con datos mock.
- **Tests nuevos requeridos:**
  - Contabilidad de bankroll (module8): dado un set de resultados conocidos, el pnl y bankroll derivados deben ser exactos.
  - Anti-leakage del backtest: assert de que ninguna feature usa datos con `GAME_DATE >= F`.
  - Lógica de dirección de pick (ya cubierta parcialmente en test_pipeline): predicción > línea → OVER, etc.

---

## 10. Requisitos no funcionales

| Requisito | Objetivo |
|-----------|----------|
| Tiempo de corrida diaria | Aceptable hasta ~2-3 min (limitado por nba_api), como hoy |
| Backtest | Debe correr sobre cache local, no en vivo; reproducible (semilla fija) |
| Reproducibilidad | Mismo input → mismo output; `random_state` fijo en modelos |
| Portabilidad | Corre en la máquina local de Santiago (Windows); sin dependencias de nube |
| Seguridad | API key en `cache/config.json`, **nunca** commiteada (ya cubierto por `.gitignore`) |

---

## 11. Preguntas técnicas abiertas

Para resolver al armar el plan de ejecución (candidatas para decidir con Fable 5 o en la siguiente sesión):

1. **Líneas históricas de props:** ¿existen a un costo/esfuerzo razonable, o el backtest v1 mide solo precisión y el ROI se valida en vivo? (§5.4) — *es la decisión técnica de mayor impacto.*
2. **Estimación de incertidumbre:** ¿regresión cuantílica, o media + sigma empírico por bucket? (§6.2)
3. **Encoding del jugador en el modelo pooled:** ¿features agregadas bastan, o vale la pena un embedding/target-encoding? Decidir con backtest.
4. **Horizonte de datos de entrenamiento:** ¿una temporada, varias? Más datos vs. cambios de reglas/estilo de juego entre temporadas.
