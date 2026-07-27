# PRD — NBA Predictor Pro

**Autor:** Santiago Ricaurte
**Versión:** 1.0
**Fecha:** 2026-07-24
**Estado:** Aprobado para ejecución

---

## 1. Contexto y problema

NBA Predictor Pro es un sistema personal de predicción de apuestas NBA (player props) con gestión de bankroll por Kelly Criterion. El pipeline existe y es funcional a nivel de código, pero **no es rentable**: el propio código está en modo daño (2 de 3 mercados suspendidos, Kelly recortado de 25% a 10%, edge mínimo subido), y no existe ninguna forma de medir si el sistema tiene ventaja real.

El problema no es de código, es de **falta de definición y de validación**. Nunca se escribió qué significa "funcionar", ni existe un backtest que pruebe si las predicciones tienen edge antes de arriesgar dinero. Este PRD fija el norte: convertir el sistema en algo que **demuestre rentabilidad en papel antes de tocar un peso**.

---

## 2. Objetivo

**Construir un sistema que genere ROI positivo sostenido apostando player props de puntos (PTS) en la NBA.**

La rentabilidad es la meta, pero con una regla innegociable: **no se arriesga dinero real hasta que el sistema demuestre edge en papel.** Apostar más capital a un sistema no validado no es la meta; construir uno que sí tenga ventaja, sí.

### Definición de éxito

| Fase | Criterio de éxito |
|------|-------------------|
| **Fase 1 — Validación** | Acumular una muestra de picks **en papel** (sin apostar) con ROI positivo demostrable. El umbral exacto (nº de picks, win rate, ROI) se calibra con el backtest — ver §7. |
| **Fase 2 — Dinero real** | Solo tras aprobar Fase 1. ROI acumulado positivo sobre dinero real, con gestión de riesgo estricta. |

El break-even a odds típicas de Betano (~1.87 decimal) es **~53.5% de win rate**. Cualquier win rate sostenido por debajo de eso = sistema perdedor, sin importar cuántos picks acierte.

---

## 3. Alcance

### Dentro de alcance (v1)
- **Un solo mercado: PTS (puntos) de player props.** Clavarlo bien antes de abrir otros.
- Uso **personal y local** (corre en la máquina de Santiago).
- **Odds ingresadas manualmente** desde Betano (sin dependencia de API de pago).
- **Backtest histórico honesto** como mecanismo central de validación.
- Registro de picks (paper trading) con contabilidad confiable.
- Dashboard como interfaz de uso diario.

### Fuera de alcance (v1 — posible futuro)
- Mercados REB, AST, Totales O/U, Spread. Se reactivan **solo** cuando PTS demuestre edge y con la misma barra de validación.
- Carga automática de odds (requiere plan de pago de The Odds API).
- Despliegue web / multiusuario / cuentas.
- Automatización del lazo de "auto-mejora" (ver §6.8 — se elimina).

---

## 4. Estado actual (auditoría honesta)

Lo que existe hoy, sin adornos:

| Componente | Estado real |
|------------|-------------|
| **Módulo 1 — Data Engine** | Funcional. Descarga stats de liga (nba_api), injury report (ESPN), equipos que juegan hoy, gamelogs, y calcula efectos de ausencias. Sólido. |
| **Módulo 2 — Prediction Engine** | **Raíz del problema.** Entrena un XGBoost **por jugador** con solo 5-40 partidos de ese jugador. Con tan pocos datos, XGBoost sobreajusta masivamente → sobreestima → pierde. También tiene modelos Poisson (totales) y Normal (spread) semi-conectados. |
| **Módulo 3 — Stakes Engine** | Kelly + bankroll. En modo defensivo: Kelly 10%, edge min 8%, REB/AST suspendidos. |
| **Módulo 5 — Error Analysis** | Lazo de "auto-mejora" que suspende mercados/excluye jugadores con solo 10 muestras. **Reacciona al ruido como si fuera señal — probablemente empeoró el sistema.** |
| **Módulo 6 — Odds Engine** | Integración con The Odds API. Los player props requieren plan de pago; el tier gratis no los da → en la práctica se ingresan a mano. |
| **Dashboard** | Streamlit, 6 tabs. Funcional. Contiene desfases (dice "Kelly 25%" pero el código usa 10%). |
| **Bankroll tracking** | **Datos corruptos.** El archivo muestra ROI −66% pero bankroll subido de $300 a $5886 — imposible con esos resultados. No confiable para medir nada. |
| **Backtesting** | **No existe.** Es el vacío más grande para una meta de rentabilidad. |
| **Tests** | Smoke tests con datos aleatorios (verifican que el código corre, no que las predicciones sean correctas). |

---

## 5. Principios de diseño

1. **Papel antes que plata.** Ninguna apuesta real sin validación previa.
2. **El backtest manda.** Las decisiones (qué mercados, qué jugadores, qué features) se toman con evidencia de backtest sobre muestras grandes, no con corazonadas ni con 10 apuestas.
3. **Nada de auto-tuning sobre ruido.** El sistema no se ajusta solo con muestras pequeñas. El diagnóstico informa; el humano decide.
4. **Honestidad estadística.** Sin data leakage: el modelo nunca ve información del futuro. El backtest simula exactamente lo que se sabría en el momento del pick.
5. **Simplicidad enfocada.** Un mercado bien hecho > cinco mercados a medias.

---

## 6. Requisitos funcionales

### 6.1 Data Engine (Módulo 1)
- Mantener la funcionalidad actual (stats de liga, injury report, gamelogs, ausencias).
- **Requisito nuevo:** exponer los datos de forma que el backtest pueda reconstruir el estado histórico de cualquier fecha (qué se sabía ese día).

### 6.2 Prediction Engine (Módulo 2) — *rediseño*
- **Decisión aprobada: replantear el enfoque de modelado a fondo.**
- Migrar de "un modelo diminuto por jugador" a **un modelo entrenado con muchos jugadores a la vez** (miles de partidos), donde la identidad del jugador y su forma reciente son features, no particiones. Más datos = menos sobreajuste.
- Objetivo del modelo: predecir la distribución de PTS de un jugador para su próximo partido (no solo el valor esperado — la incertidumbre importa para el edge).
- Mantener el rigor anti-leakage (rolling features con `shift`).

### 6.3 Odds (Módulo 6)
- **Entrada manual** de líneas y odds de Betano en el dashboard. Sin dependencia de API de pago.
- La integración con The Odds API queda como código latente, no en el flujo crítico.

### 6.4 Stakes Engine (Módulo 3)
- Kelly Criterion fraccionado para el sizing de apuestas.
- Los parámetros (fracción Kelly, edge mínimo, tope por apuesta) se fijan **con base en el backtest**, no a mano por miedo.
- Reglas de riesgo para Fase 2 (dinero real): tope de exposición diaria y stop-loss — a definir al graduar.

### 6.5 Backtest Engine (Módulo NUEVO) — *pieza central*
- Tomar partidos históricos, generar el pick que el modelo **habría** hecho sabiendo solo lo disponible en ese momento, y calcular si habría ganado contra la línea real.
- Salida: win rate, ROI, distribución de edge, calibración (¿los picks de alto edge realmente ganan más?).
- Es el mecanismo que decide si hay ventaja y con qué parámetros. **Sin esto, no se avanza a dinero real.**
- Reto a vigilar: conseguir líneas históricas de props. Si no hay líneas reales históricas, definir una aproximación honesta y documentar su limitación.

### 6.6 Tracking / Bankroll — *reconstruir*
- **Reset limpio.** Descartar el bankroll corrupto actual.
- Contabilidad correcta y probada con tests: cada pick registra predicción, línea, odds, stake, resultado; el bankroll se deriva de forma verificable.
- En Fase 1 (papel) el "bankroll" es virtual; sirve para medir ROI sin arriesgar nada.

### 6.7 Dashboard (Módulo 4)
- Flujo diario (una corrida en la tarde): cargar datos NBA → ingresar líneas de Betano → ver picks con su edge → registrar. Al día siguiente marcar ganó/perdió.
- **Requisito nuevo:** vista de resultados del backtest y vista de paper trading (ROI acumulado, win rate, calibración).
- Corregir desfases de texto (Kelly, mercados) para que la UI diga la verdad del código.

### 6.8 Diagnóstico (Módulo 5) — *degradar a solo-lectura*
- **Se elimina el lazo de auto-mejora automático.**
- El módulo pasa a ser **solo diagnóstico**: muestra dónde falla el modelo (por mercado, jugador, edge, calibración) pero **no cambia nada por su cuenta**.
- Las decisiones que antes tomaba solo (suspender mercado, excluir jugador) las toma Santiago con evidencia de backtest y muestras grandes.

---

## 7. Métricas de éxito

Las métricas exactas de graduación papel → dinero real **se calibran con el backtest** (decisión aprobada), para que sean realistas y no números inventados. Marco de referencia:

- **Métrica primaria:** ROI acumulado sobre los picks registrados.
- **Métrica de control:** win rate vs. break-even (~53.5% a odds 1.87).
- **Métrica de calidad:** calibración — los picks de mayor edge deben ganar más que los de menor edge. Si no, el modelo miente sobre su propia ventaja.
- **Muestra mínima:** a definir con el backtest (referencia inicial: ~100 picks para tener señal estadística, no ruido).

---

## 8. Roadmap por fases

**Fase 0 — Higiene y cimientos**
1. Reset del bankroll corrupto + contabilidad confiable con tests.
2. Eliminar el lazo de auto-mejora del Módulo 5 (degradar a diagnóstico).
3. Corregir desfases de texto en el dashboard.

**Fase 1 — Backtest (el corazón)**
4. Construir el Backtest Engine.
5. Medir el modelo ACTUAL en backtest para tener una línea base honesta.

**Fase 2 — Rediseño del modelo**
6. Migrar a modelo pooled multi-jugador para PTS.
7. Comparar contra la línea base en backtest. Iterar features con evidencia.

**Fase 3 — Validación en papel**
8. Fijar el umbral de graduación con lo que muestre el backtest.
9. Paper trading en vivo hasta alcanzar la muestra y el ROI objetivo.

**Fase 4 — Dinero real (condicional)**
10. Solo si Fase 3 aprueba. Definir reglas de riesgo (tope diario, stop-loss) y empezar con stakes mínimos.

**Futuro (fuera de v1):** reactivar REB/AST/Totales/Spread bajo la misma barra de validación.

---

## 9. Riesgos y supuestos

| Riesgo | Mitigación |
|--------|------------|
| No conseguir líneas históricas de props para el backtest | Definir aproximación honesta y documentar su limitación; considerar validar con paper trading en vivo si el backtest no es fiable. |
| El mercado de props es eficiente y no hay edge real | El backtest lo revelará temprano, **antes** de arriesgar dinero. Es un resultado válido: mejor saberlo en papel. |
| Sobreajuste al construir/iterar el modelo con el backtest | Separar datos de entrenamiento y de validación temporalmente; no tocar el set de validación hasta el final. |
| Volver a caer en ajustes por pánico ante rachas cortas | Principio §5.3: nada de decisiones sobre muestras pequeñas. |

---

## 10. Registro de decisiones

Decisiones tomadas en la sesión de definición (2026-07-24):

| Tema | Decisión |
|------|----------|
| Objetivo | Rentabilidad real (con validación en papel obligatoria antes de dinero) |
| Mercados v1 | Solo PTS. Clavar uno antes de abrir más. |
| Odds | Manual, gratis (sin API de pago) |
| Alcance | Personal y local |
| Definición de éxito | Papel primero, luego plata |
| Validación | Backtest histórico honesto |
| Modelo | Replantear a fondo (pooled multi-jugador) |
| Bankroll | Reset limpio + tracking confiable |
| Auto-mejora (Módulo 5) | Eliminar el lazo automático; degradar a diagnóstico |
| Flujo diario | Una corrida en la tarde vía dashboard |
| Gate papel→real | Calibrar el umbral con el backtest |
