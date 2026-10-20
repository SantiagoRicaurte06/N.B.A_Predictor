# RECALIBRACIÓN — Modelo de puntos v2 con datos de ESPN

**Fecha:** 2026-10-20 · **Reproducible:** `python scripts/recalibrar.py --holdout`
**Números completos:** [`resultados_recalibracion.json`](resultados_recalibracion.json)

---

## Lo más importante primero

1. **El modelo predice mejor.** En validación, el error medio baja de 5.15 puntos
   (promedio de los últimos 10 partidos) a **4.86** (−5.5 %).
2. **Sus probabilidades son fiables.** La probabilidad declarada coincide con el
   acierto real con una diferencia de 1 a 2 puntos en todos los tramos.
3. **El ROI contra líneas sintéticas NO es evidencia de ganancia contra Betano.**
   Da cifras de 70 % o más de acierto, imposibles contra una casa real. Lo que
   miden es lo mal que una línea sintética imita a la de la casa. La medida que
   manda es la de las líneas reales de Betano, que el dashboard registra desde
   ahora.

---

## Protocolo (fijado antes de mirar resultados)

| Pieza | Decisión |
|---|---|
| Datos | ESPN, temporadas 2021-22 a 2025-26: 6 628 partidos, 103 160 filas jugador-partido de rotación |
| Ajuste y selección | Solo con **2023-24 y 2024-25**, cada una predicha con un modelo entrenado con todo lo anterior |
| Reentreno | Al inicio de cada mes, con todo lo ocurrido antes (como en producción) |
| Holdout | **2025-26**, predicho **una sola vez** con todo congelado |
| Regla para un factor | Entra si baja el error medio de validación en al menos 0.005 puntos |
| Umbral de apuesta | El de mejor ROI con al menos 10 picks por semana |
| Cuota | 1.87 a ambos lados (break-even 53.5 %) |

Las 4 partidas de playoffs de 2025-26 que ESPN no tiene (404) se omiten.

---

## Selección de factores

Error medio (MAE, puntos) en validación. Cada paso agrega el grupo que más baja
el error.

| Paso | MAE | Mejora |
|---|---:|---:|
| Promedio de los últimos 10 partidos | 5.147 | — |
| **base** (los factores del modelo anterior) | 5.032 | — |
| + **ausencias** del equipo | 4.938 | −0.094 |
| + historia del **jugador** | 4.887 | −0.051 |
| + **líneas** de la casa (spread y total) | 4.873 | −0.014 |
| + rival · calendario · ritmo · motivación | ≥ 4.871 | < 0.005 cada uno: **no entran** |

| Forma de predecir | MAE |
|---|---:|
| Directo (puntos) | 4.873 |
| Minutos × puntos por minuto | 4.871 (no supera la regla) |
| **Mezcla de ambos** | **4.865** ← elegida |

**Lo que más pesa son las ausencias.** Cuando falta un compañero de rotación, sus
puntos y minutos se reparten; el modelo lo ve a través de los puntos libres, la
ausencia de la estrella y el rango del jugador entre los disponibles.

**Lo que no aportó**, medido y descartado: defensa del rival (por posesión y
contra la posición), bajas del rival, viajes, cambio de huso, altitud, tres
partidos en cuatro noches, récord y racha, tramo final de temporada y partidos
contra un exequipo. El "estado de ánimo" no se puede medir directamente, y sus
aproximaciones (racha, motivación por clasificación) no mejoraron la predicción.

---

## Líneas sintéticas: por qué hay dos y por qué ninguna basta

ESPN no tiene histórico de líneas de props, así que el backtest compara contra
líneas construidas:

- **Ingenua:** mediana de los últimos 10 partidos.
- **Informada:** regresión de mediana con forma, minutos, ausencias del equipo y
  total implícito. Imita a una casa que ajusta por lesiones.

**Ambas se ponen en la mediana, no en la media.** Los puntos tienen cola
derecha, así que la mediana queda por debajo de la media; una línea en la media
hacía ganar al under el 54 % de las veces sin mérito del modelo. La primera
corrida tenía ese sesgo y se corrigió antes de medir el holdout.

Aun así, la línea informada es un modelo lineal y se equivoca en casos extremos
(por ejemplo, una línea de 30.5 para un jugador al que le faltan cinco
compañeros). Una casa no comete esos errores. Por eso el ROI contra estas líneas
**sobreestima** el edge real.

---

## Validación · 2023-24 y 2024-25

| | Modelo | Últimos 10 |
|---|---:|---:|
| Error medio (MAE) | **4.86** | 5.15 |
| Sesgo | −0.06 | −0.18 |

### Calibración contra la línea informada

| Probabilidad declarada | Picks | Declarada | Real |
|---|---:|---:|---:|
| 50–55 % | 22 645 | 52.4 % | 52.0 % |
| 55–60 % | 11 650 | 57.1 % | 55.8 % |
| 60–65 % | 5 284 | 61.9 % | 60.4 % |
| 65–70 % | 1 751 | 67.0 % | 65.2 % |
| 70–75 % | 539 | 72.2 % | 70.3 % |
| ≥ 75 % | 236 | 79.3 % | 80.9 % |

### Apuestas simuladas contra la línea informada

| Probabilidad ≥ | Picks/semana | Acierto | ROI |
|---|---:|---:|---:|
| 0.55 | 278 | 58.6 % | +9.6 % |
| 0.60 | 112 | 62.8 % | +17.4 % |
| 0.65 | 36 | 67.7 % | +26.7 % |
| **0.70** | **11** | **73.5 %** | **+37.5 %** |

Umbral elegido: **0.70**, el de mejor ROI con al menos 10 picks por semana.
Contra líneas reales habrá menos picks: la línea de la casa está más cerca del
modelo que la sintética.

---

## Holdout · 2025-26 (medido una sola vez)

Configuración congelada (grupos, modo mezcla, umbral 0.70) y reentreno mensual,
igual que en validación. Nada se tocó después de ver estos números.

| | Modelo | Últimos 10 |
|---|---:|---:|
| Error medio (MAE) | **4.81** | 5.08 |
| Sesgo | −0.13 | — |

| Probabilidad declarada | Picks | Declarada | Real |
|---|---:|---:|---:|
| 50–55 % | 12 173 | 52.3 % | 52.7 % |
| 55–60 % | 5 774 | 57.1 % | 56.7 % |
| 60–65 % | 2 481 | 62.1 % | 62.1 % |
| 65–70 % | 816 | 67.1 % | 64.3 % |
| 70–75 % | 245 | 72.3 % | 71.4 % |
| ≥ 75 % | 161 | 80.1 % | 82.6 % |

| Probabilidad ≥ | Picks/semana | Acierto | ROI |
|---|---:|---:|---:|
| 0.55 | 279 | 59.6 % | +11.4 % |
| 0.60 | 109 | 64.1 % | +19.8 % |
| 0.65 | 36 | 68.2 % | +27.5 % |
| **0.70** | **12** | **75.9 %** | **+41.9 %** |

**Lectura:** el modelo generaliza. La mejora de error (−5.3 %) y la calibración
se sostienen en una temporada que no participó en ninguna decisión. Lo que **no**
se puede leer es el ROI: sigue siendo contra una línea sintética, con las mismas
limitaciones de arriba.

---

## Qué sigue

1. **Registrar las líneas reales de Betano** de cada jugador que se mire,
   apostado o no. El dashboard las guarda con la predicción y la probabilidad del
   modelo y completa los puntos reales al día siguiente.
2. Con unas **300 líneas reales**, medir acierto y ROI contra Betano. Si el
   modelo no supera el break-even ahí, el edge sintético no se traslada a la casa
   y hay que decirlo así.
3. El gate papel → dinero real sigue igual: 300 picks y el límite inferior del
   IC 95 % por encima del break-even.

## Limitaciones conocidas

- **Comienzo de temporada.** La rotación de cada equipo se reconstruye con los
  partidos de los últimos 25 días, así que en las primeras dos semanas los
  factores de ausencias valen 0. El modelo se entrenó igual, por lo que es
  coherente, pero predice algo peor esos días. Mejora posible: usar la plantilla
  vigente y los números de la temporada anterior.
- **Bajas de última hora.** En la historia se sabe quién jugó; en vivo, el
  reporte de lesiones puede cambiar después de cargar el día. Conviene volver a
  cargar cerca del inicio de los partidos.
- **Jugadores nuevos.** Se predice a quien tiene al menos 10 partidos previos y
  15 minutos de media reciente; los novatos entran tras sus primeros partidos.
