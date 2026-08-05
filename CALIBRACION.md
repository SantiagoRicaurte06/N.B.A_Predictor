# CALIBRACIÓN — La sigma era in-sample

**Generado:** 2026-08-05
**Reproducible:** `python diagnostico_edge.py`

---

## El fallo

`ModeloPooled.entrenar` estimaba `pred_sigma` con los residuos del modelo
sobre **sus propios datos de entrenamiento**. XGBoost ajusta muy fino ahí, así
que el error salía artificialmente pequeño.

Como la probabilidad se calcula con `prob = Φ((media − línea) / sigma)`, una
sigma corta infla **todas** las probabilidades. El síntoma medible: el modelo
declaraba un 72.6 % de acierto y conseguía un 59.1 %.

Eso no es un error cosmético. `module3` dimensiona con Kelly, y Kelly consume
la probabilidad directamente: alimentado con probabilidades infladas, apuesta
de más de forma sistemática.

## El arreglo

Residuos **fuera de muestra** por ventana temporal expansiva: los datos se
ordenan por fecha, se parten en 5 tramos, y cada tramo se predice con un
modelo entrenado solo con lo anterior. Es el error que se verá en producción,
que es lo que la sigma debe medir.

| | Antes | Después |
|---|---|---|
| Sigma declarada | 5.99 | **6.53** |
| Sigma real (medida out-of-sample) | 6.42 | 6.42 |
| Ratio declarada/real | 1.07× (subestima) | **1.01×** |
| Residuos usados | ~33 000 in-sample | **23 848 out-of-fold** |

### Efecto en la calibración

| Prob. declarada | Real (antes) | Real (después) |
|---|---|---|
| ≤ 55 % | 48.4 % | 49.0 % |
| 55–60 % | 51.2 % | 50.5 % |
| 60–65 % | 57.1 % | 57.6 % |
| 65–70 % | 60.2 % | **63.4 %** |
| > 70 % | 59.1 % | 59.6 % (n=52) |

---

## Lo que el arreglo NO hizo

**No creó ni destruyó ventaja.** El acierto con umbral 0.60 pasó de 55.8 % a
55.7 %: el modelo ordena igual, solo cambiaron las etiquetas de probabilidad.
La ventaja (o su ausencia) siempre estuvo en el ranking, no en la calibración.

Lo que cambia es que ahora los números significan algo y Kelly puede usarlos.

## Sigue habiendo sobreconfianza

Entre 3 y 7 puntos porcentuales en todos los tramos, con la sigma ya corregida.

---

## Hipótesis DESCARTADA: la cola derecha

La sospecha era que el culpable fuese la normal. Los puntos anotados tienen
cola derecha (medido: **asimetría 0.429** en los residuos), y una normal sobre
una distribución sesgada exagera las colas.

Se implementó la alternativa: en vez de suponer la forma, usar la medida.

    actual = media + residuo  →  P(actual > línea) = P(residuo > línea − media)

leyendo esa probabilidad de 201 cuantiles de los residuos out-of-fold. Para
una predicción de 20 puntos daba entre 2.6 y 5.2 puntos menos que la normal,
justo la magnitud de la sobreconfianza observada. Encajaba.

**No funcionó.** Medido sobre el dev set (2 335 puntos):

| | Normal | Empírica |
|---|---|---|
| \|brecha\| media ponderada | **5.0 %** | 5.6 % |
| Acierto con umbral 0.60 | **59.1 %** | 54.8 % |
| Acierto con umbral 0.65 | **62.4 %** | 61.6 % |

Empeora en todo. El tramo 0.60–0.65 pasa de acertar 57.6 % a 50.6 %: la
corrección mueve picks distintos a ese tramo, y son peores.

La explicación más probable es que la asimetría no es una constante de la liga
sino algo propio de cada jugador y situación, así que una distribución agregada
no la representa — y encima se estima en el periodo de entrenamiento y se
aplica a otro.

**Decisión:** la maquinaria (`ModeloPooled.prob_supera` y el parámetro
`prob_fn` de `evaluar`) se conserva para poder repetir el experimento, pero
**no está activa en ningún flujo**. Todo sigue usando la normal. Queda escrito
para que nadie —incluido el yo del futuro— vuelva a intentarlo creyendo que es
obviamente correcto.

## Qué queda entonces

La sobreconfianza de ~5 puntos sigue sin explicación. Pero hay una salida que
**no depende de arreglarla**: lo que aguantó fuera de muestra no fue el valor
de la probabilidad, fue el **orden**. El ranking es monotónico y se sostiene.

Por eso lo práctico no es seguir persiguiendo la calibración, sino mover el
umbral de operación a donde el acierto MEDIDO supera el break-even. Eso solo
exige que el ranking sea correcto, que es justo lo que está demostrado.

---

## Estado de la validación (2026-08-05)

Set de validación: 6 142 puntos posteriores al 2026-02-21.

| Umbral | n | Acierto | ROI | IC95 | ¿Supera 53.5 %? |
|---|---|---|---|---|---|
| 0.50 | 6 142 | 51.5 % | −3.6 % | [50.3, 52.8] | No |
| 0.55 | 3 598 | 53.2 % | −0.6 % | [51.5, 54.8] | No |
| **0.60** (prefijado) | 1 703 | 55.7 % | +4.2 % | **[53.4, 58.1]** | **Roza, no cruza** |
| 0.65 | 643 | 58.3 % | +9.1 % | [54.5, 62.1] | Sí |

**El umbral que se registró de antemano (0.60) no supera el break-even** al
95 %: el límite inferior queda en 53.4 % contra 53.5 %. Falla por una décima.

El 0.65 se lee **después** de mirar la validación y sobre un set ya usado. Es
una hipótesis para datos frescos, no evidencia.

### Lo que sí quedó demostrado

El ranking es monotónico y aguantó fuera de muestra:

```
51.5 %  →  53.2 %  →  55.7 %  →  58.3 %
 0.50      0.55       0.60       0.65
```

El modelo distingue de verdad sus predicciones buenas de las malas.

### Advertencia de método

**La validación ya se ha usado dos veces** (con la sigma vieja y con la nueva).
Ha dejado de ser un set virgen: cualquier número adicional extraído de estos
datos está contaminado.

---

## Cambios aplicados a partir de esto

### 1. El gate se podía pasar por suerte

Antes: 100 picks con 54 % de acierto. Con esa muestra el IC95 va de **44.2 % a
63.8 %** — el break-even de 53.5 % cae en el medio. Se podía cruzar el gate, y
empezar a apostar dinero real, estando en realidad en el 45 %.

Ahora el criterio es que el **límite inferior del intervalo de Wilson supere el
break-even**, más un suelo de 300 picks. Se ajusta solo: con más ventaja hace
falta menos muestra.

| Acierto observado | Picks necesarios |
|---|---|
| 62 % | 130 |
| 60 % | 230 |
| 58 % | 470 |
| 56 % | 1 510 |
| 55 % | 4 210 |
| 54 % | 38 090 (o sea: no) |

Se usa Wilson y no la aproximación normal porque con proporciones lejos de 0.5
la normal da intervalos demasiado optimistas — justo el error que este gate
existe para evitar.

### 2. Faltaba un piso de convicción

`min_edge = 0.08` equivale a prob ~57.8 % con cuota 1.87, dentro de la zona
donde el sistema mide **por debajo** del break-even.

Pero subir `min_edge` no era la solución correcta: `edge = prob × cuota − 1`,
así que un mismo edge se alcanza con probabilidad alta y cuota mala o al revés.
Lo que aguantó fuera de muestra fue el **ranking del modelo**, no el edge.

Por eso se añade un filtro aparte, `min_prob = 0.65`, tomado directamente de lo
medido. `min_edge` se mantiene como piso económico.

---

## Siguiente paso

Temporada 2026-27, desde octubre. Registrar con **umbral 0.65 prefijado**,
contra **líneas reales de Betano**, anotando **la cuota de cada pick**. Con
300-400 picks hay respuesta, sin arriesgar dinero.

Cuotas mínimas para no perder:

| Acierto | Cuota mínima |
|---|---|
| 55.7 % | 1.795 |
| 58.3 % | 1.715 |

Si la cuota media real está por debajo de 1.72, el asunto se cierra sin más
análisis.

**Todo lo anterior se mide contra una línea sintética (media móvil L10), no
contra Betano.** Ésa sigue siendo la asunción central sin probar.
