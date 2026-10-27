# ADR — NBA Predictor Pro

**Architecture Decision Records**
**Autor:** Santiago Ricaurte · **Fecha:** 2026-07-24 · **Documentos relacionados:** [PRD.md](PRD.md), [TRD.md](TRD.md)

Cada registro documenta una decisión de arquitectura tomada, su contexto y sus consecuencias. Formato: Estado · Contexto · Decisión · Consecuencias · Alternativas consideradas.

| # | Decisión | Estado |
|---|----------|--------|
| ADR-001 | Enfoque en un solo mercado (PTS) en v1 | Aceptado |
| ADR-002 | Modelo pooled multi-jugador en vez de per-jugador | Aceptado |
| ADR-003 | Validación por backtest antes de dinero real | Aceptado |
| ADR-004 | Eliminar el lazo de auto-mejora automático | Aceptado |
| ADR-005 | Odds manuales, sin API de pago | Aceptado |
| ADR-006 | Archivos planos locales, sin base de datos | Aceptado |
| ADR-007 | Bankroll derivado del registro, no mutable | Aceptado |
| ADR-008 | El modelo emite incertidumbre, no solo el valor | Aceptado |
| ADR-009 | Despliegue en VPS con Docker y login OIDC | Aceptado |

---

## ADR-001 — Enfoque en un solo mercado (PTS) en v1

**Estado:** Aceptado

**Contexto:** El sistema apostaba props de PTS, REB y AST, más totales y spread semi-conectados. REB y AST terminaron suspendidos por win rate < 35%. Abrir cinco mercados a la vez dispersó el esfuerzo y ninguno alcanzó rentabilidad.

**Decisión:** v1 se concentra exclusivamente en **player props de puntos (PTS)**. Los demás mercados quedan fuera de alcance hasta que PTS demuestre edge validado.

**Consecuencias:**
- (+) Menos superficie que validar, más profundidad en el mercado con más volumen de datos.
- (+) Un backtest más simple y enfocado.
- (−) Se renuncia temporalmente a diversificación de mercados.

**Alternativas consideradas:** reactivar los 3 props a la vez (rechazada: no se entendía aún por qué fallaban); conectar todo incluido totales/spread (rechazada: reproduce la dispersión que causó el estancamiento).

---

## ADR-002 — Modelo pooled multi-jugador en vez de un modelo por jugador

**Estado:** Aceptado

**Contexto:** `entrenar_modelo_props()` entrena un `XGBRegressor` (200 árboles, depth 3) sobre 5-40 partidos de UN jugador. Esa relación datos/parámetros produce sobreajuste severo → sobreestimación → ROI negativo. Es la causa raíz identificada del -66%.

**Decisión:** Migrar a **un solo modelo entrenado con muchos jugadores a la vez** (miles de partidos-jugador). La identidad y forma del jugador entran como *features*, no como partición del dataset.

**Consecuencias:**
- (+) Órdenes de magnitud más datos por modelo → menos sobreajuste.
- (+) El modelo aprende patrones generales (efecto de descanso, pace, matchup) transferibles entre jugadores.
- (−) Pierde algo de personalización por jugador; se compensa con features de forma reciente.
- (−) Requiere reescribir el núcleo de module2.

**Alternativas consideradas:** mantener per-jugador con más regularización o un modelo más simple (rechazada: el problema de fondo son los pocos datos, no el tipo de modelo); no tocar el modelo hasta medir (parcialmente incorporada: se mide la línea base antes de reemplazar).

---

## ADR-003 — Validación por backtest y paper trading antes de dinero real

**Estado:** Aceptado

**Contexto:** No existe ninguna forma de saber si el sistema tiene ventaja. El bankroll tracking está corrupto y no es fiable. Apostar dinero real sin evidencia de edge es la fuente del riesgo.

**Decisión:** Regla innegociable — **no se arriesga dinero real hasta demostrar edge en papel.** Se construye un Backtest Engine (module7) como mecanismo central de validación, y una fase de paper trading en vivo. El umbral de graduación papel→real se calibra con lo que muestre el backtest.

**Consecuencias:**
- (+) El riesgo de perder dinero con un sistema no validado se elimina.
- (+) Si no hay edge, se descubre en papel (resultado válido y barato).
- (−) Retrasa cualquier apuesta real hasta tener el backtest y la muestra.

**Alternativas consideradas:** confiar en el tracking en vivo actual (rechazada: datos corruptos); win rate o ROI fijo como única métrica (incorporados como métricas de control, no como gate único).

---

## ADR-004 — Eliminar el lazo de auto-mejora automático (module5 solo diagnóstico)

**Estado:** Aceptado

**Contexto:** `module5.aplicar_mejoras_automaticas()` con `MIN_MUESTRA=10` ajustaba el sistema solo: suspendía mercados, excluía jugadores, metía correcciones de sesgo — todo sobre muestras diminutas. Con 10 apuestas no se distingue señal de suerte; el lazo reaccionaba al ruido como si fuera información y probablemente degradó el sistema (de ahí salieron REB/AST suspendidos y el Kelly recortado).

**Decisión:** Se **elimina la aplicación automática de cambios.** El Módulo 5 pasa a ser **solo diagnóstico**: muestra dónde falla el modelo, pero no modifica nada. Las decisiones se toman con evidencia de backtest y muestras grandes.

**Consecuencias:**
- (+) Elimina una fuente activa de sobreajuste a ruido.
- (+) Las decisiones quedan bajo control humano con evidencia sólida.
- (−) Se pierde la ilusión de "auto-mejora"; requiere disciplina manual.

**Alternativas consideradas:** mantener el lazo subiendo el umbral a 50-100 muestras (rechazada: sigue siendo automático y frágil); dejarlo como está (rechazada: es parte del problema).

---

## ADR-005 — Odds ingresadas manualmente, sin API de pago

**Estado:** Aceptado

**Contexto:** Los player props de The Odds API requieren plan de pago; el tier gratis (500 req/mes) solo da spreads, totals y moneylines. Pagar una API para un sistema aún no validado no se justifica.

**Decisión:** Las líneas y odds de Betano se **ingresan manualmente** en el dashboard. La integración con The Odds API queda como código latente, fuera del flujo crítico.

**Consecuencias:**
- (+) Cero costo mensual y cero dependencia de un servicio de pago.
- (+) El foco queda en el modelo, no en la automatización de odds.
- (−) Trabajo manual diario para ingresar líneas.

**Alternativas consideradas:** plan de pago para props automáticos (rechazada: no se justifica antes de validar edge); híbrido totales-auto/props-manual (rechazada: totales está fuera de alcance v1).

---

## ADR-006 — Persistencia en archivos planos locales, sin base de datos

**Estado:** Aceptado

**Contexto:** El sistema es personal y local, con volúmenes pequeños (decenas de jugadores/día, cientos de picks). Ya usa CSV/JSON en `cache/`.

**Decisión:** Mantener **archivos planos locales** (CSV/JSON) como capa de persistencia. Sin base de datos en v1.

**Consecuencias:**
- (+) Simplicidad; datos inspeccionables y versionables.
- (+) Cero infraestructura.
- (−) No escala a multiusuario ni a grandes volúmenes (no es un requisito de v1).

**Alternativas consideradas:** SQLite (aplazada: reevaluar solo si el paper trading supera ~10k registros).

---

## ADR-007 — Bankroll derivado del registro, no un número mutable

**Estado:** Aceptado

**Contexto:** `cache/bankroll.json` guardaba el bankroll como un número que se mutaba en cada resultado. El archivo terminó con datos imposibles (ROI −66% pero bankroll subido de $300 a $5886), señal de un bug de contabilidad o edición manual.

**Decisión:** El bankroll se **deriva** del registro histórico de picks (suma de PnL sobre un CSV append-only), nunca se almacena como número mutable independiente. Reset limpio del estado corrupto.

**Consecuencias:**
- (+) Elimina toda una clase de bugs de contabilidad; el bankroll siempre es reproducible desde el historial.
- (+) Auditable: cualquier cifra se puede reconstruir.
- (−) Requiere reconstruir el módulo de tracking (module8).

**Alternativas consideradas:** auditar y arreglar el número mutable existente (rechazada: los datos actuales no son fiables y el patrón mutable es el bug de fondo).

---

## ADR-008 — El modelo emite incertidumbre, no solo el valor esperado

**Estado:** Aceptado

**Contexto:** El cálculo de edge y de probabilidad Over/Under depende de la *distribución* de la predicción, no solo de su punto central. El código actual improvisa un sigma a partir del MAE o del STD histórico, de forma inconsistente.

**Decisión:** El Prediction Engine emite **media y una estimación de incertidumbre (`pred_sigma`)** como parte formal del contrato de predicción. La probabilidad de superar la línea se calcula a partir de esa distribución.

**Consecuencias:**
- (+) El edge se calcula sobre una base estadística coherente.
- (+) Permite calibración honesta (¿los picks de alto edge realmente ganan más?).
- (−) Exige elegir un método de estimación de incertidumbre (regresión cuantílica vs. sigma empírico) — queda como pregunta técnica abierta en el TRD.

**Alternativas consideradas:** seguir derivando sigma del MAE (rechazada: inconsistente y subestima la varianza real).

---

## ADR-009 — Despliegue en VPS con Docker y login OIDC

**Estado:** Aceptado

**Contexto:** El dashboard debe estar disponible en internet solo para su dueño. Es una app Streamlit (proceso largo con WebSockets) que persiste en archivos planos (ADR-006) y entrena el modelo del día en el servidor.

**Decisión:** Desplegar en un **VPS** con Docker Compose: Streamlit detrás de **Caddy** (HTTPS automático) y acceso con **`st.login` (OpenID Connect con Google)** más una lista de correos autorizados. Sin la configuración de login el dashboard no arranca.

**Consecuencias:**
- (+) `cache/` sigue siendo un directorio: sin migrar datos.
- (+) Contraseñas y 2FA los gestiona Google; la app no guarda credenciales.
- (+) Coste cero con Oracle Cloud Always Free, o 4–6 USD/mes en un VPS de pago.
- (−) El servidor (actualizaciones, respaldos, cortafuegos) se mantiene a mano.

**Alternativas consideradas:** Vercel y Firebase Hosting (rechazadas: serverless o estático, sin disco persistente ni procesos largos); Supabase (no ejecuta Python; solo útil si el ledger pasa a Postgres); Streamlit Community Cloud (disco efímero, se perdería el ledger); usuario y contraseña propios con hash (rechazada: más superficie de ataque que delegar en un proveedor OIDC).
