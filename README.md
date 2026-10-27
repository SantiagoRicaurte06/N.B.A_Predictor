# NBA Predictor

**Versión 0.2.0** · [Registro de cambios](CHANGELOG.md)

Predicción de los **puntos** de jugadores NBA y gestión de apuestas en papel contra
las líneas de Betano, con una regla central: **no se arriesga dinero real hasta
demostrar ventaja en papel**.

> **Estado:** el modelo de puntos v2 predice mejor que el promedio reciente (error
> medio 4.86 frente a 5.15 puntos) y sus probabilidades están bien calibradas. La
> ventaja contra Betano todavía **no está demostrada**: el backtest solo puede usar
> líneas sintéticas, y la prueba real son las líneas de Betano que el sistema
> registra desde ahora. Detalle en [docs/RECALIBRACION.md](docs/RECALIBRACION.md).

---

## Cómo funciona

```mermaid
flowchart LR
    ESPN[API de ESPN<br/>box scores · lesiones · plantillas · líneas] --> D[datos]
    D --> F[modelo/factores<br/>forma · ausencias · líneas]
    F --> M[modelo de puntos v2<br/>media + probabilidad calibrada]
    BET[Líneas de Betano<br/>ingreso manual] --> A[apuestas<br/>Kelly fraccionado]
    M --> A
    A --> L[(seguimiento<br/>ledger + líneas reales)]
    ESPN -.resultados del día siguiente.-> L
    L --> UI[Dashboard]
    F --> BT[backtest por temporadas]
```

**Uso diario**

1. **Hoy:** el dashboard descarga los partidos, el reporte de lesiones, las
   plantillas y las líneas de partido, y predice los puntos de cada jugador de
   rotación.
2. Escribes las líneas de Betano de los jugadores que te interesan. El modelo da
   la probabilidad calibrada de over o under y, si supera el piso (70 %), el
   stake Kelly. Al registrar, se guardan **todas** las líneas que escribiste,
   apostadas o no: son la base para medir el edge real contra Betano.
3. **Resultados:** al día siguiente, un botón resuelve los picks con los box
   scores de ESPN. Si el jugador no jugó, el pick queda anulado.
4. **Rendimiento:** bankroll, ROI, calibración en vivo y el gate papel → dinero real.
5. **Modelo:** factores en uso, validación, holdout y, cuando haya 30 o más, el
   rendimiento contra tus líneas reales.

![Pestaña Hoy: partidos, bajas y predicciones con las líneas de Betano](docs/img/hoy.png)

![Pestaña Modelo: factores en uso y resultados de validación](docs/img/modelo.png)

El tema claro u oscuro se elige en ⋮ → Settings.

---

## Qué tiene en cuenta el modelo

Cada factor se calcula solo con información previa al partido, y una prueba
automática lo verifica.

| Grupo | Ejemplos | En el modelo |
|---|---|:---:|
| Forma del jugador | puntos, minutos y tiros de sus últimos 5, 10 y 20 partidos; promedio de temporada | ✓ |
| Ausencias del equipo | puntos y minutos que dejan libres los compañeros que no juegan, si falta la estrella, rango del jugador entre los disponibles | ✓ |
| Líneas de la casa | spread (riesgo de paliza) y total del partido | ✓ |
| Rival, calendario, motivación | defensa por posición, viajes, huso horario, altitud, racha, playoffs, exequipo | medido; no mejoró |

La selección y sus números están en [docs/RECALIBRACION.md](docs/RECALIBRACION.md).

---

## Resultados

| | Validación 2023-24 y 2024-25 | Holdout 2025-26 |
|---|---:|---:|
| Error medio del modelo | 4.86 pts | 4.81 pts |
| Error del promedio de 10 partidos | 5.15 pts | 5.08 pts |
| Acierto con prob. ≥ 0.70 contra la línea informada | 73.5 % | 75.9 % |

El acierto contra líneas sintéticas **sobreestima** el edge real: esas líneas se
equivocan en casos que Betano no fallaría. Sirve para elegir el umbral, no para
prometer ganancias.

**Limitaciones conocidas**

- En las primeras dos semanas de cada temporada el modelo no ve las ausencias:
  reconstruye la rotación de cada equipo con los partidos recientes.
- Las bajas de última hora no llegan si el día se cargó temprano: conviene volver
  a cargarlo cerca del inicio de los partidos.
- Solo se predice a jugadores con 10 partidos previos y 15 minutos de media.

---

## Gate papel → dinero real

| Criterio | Meta |
|---|:---:|
| Muestra | ≥ 300 picks resueltos |
| Acierto | ≥ 54 % (break-even ≈ 53.5 % a cuota 1.87) |
| ROI | ≥ 0 % |
| **Intervalo de confianza** | el límite inferior del IC 95 % (Wilson) supera el break-even |

El último es el que manda: con 100 picks al 54 % el intervalo va de 44 % a 64 % y no
distingue ventaja de suerte.

---

## Instalación

Requiere Python 3.10 o superior. Streamlit 1.60 o superior se instala con el paquete.

```bash
pip install -e ".[dev]"

# Una vez: descarga el histórico de ESPN (unos minutos, ~60 MB en cache/)
python -m nba_predictor.datos.espn

# Dashboard
streamlit run app/dashboard.py

# Recalibración reproducible (validación; --holdout mide 2025-26)
python scripts/recalibrar.py

# Pruebas
pytest
```

El dashboard exige login. En local, configura `.streamlit/secrets.toml` a partir
de `.streamlit/secrets.toml.example` o arráncalo con `NBA_SIN_LOGIN=1`.

## Despliegue

En un VPS con Docker Compose, Caddy para HTTPS y login con Google. Por qué no
Vercel, Firebase ni Supabase, y los pasos: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

---

## Estructura

```
nba_predictor/
  datos/         ESPN: descarga, tablas jugador-partido y equipo-partido, datos del día
  modelo/        factores, modelo de puntos, configuración congelada, predicción diaria
  apuestas/      Kelly, edge y tamaño de cada apuesta
  seguimiento/   ledger de picks, métricas, gate y diagnóstico
  backtest/      evaluación por temporadas contra líneas sintéticas
app/             dashboard Streamlit (una vista por pestaña) y control de acceso
deploy/          Caddyfile y script de actualización del VPS
scripts/         recalibración
tests/           pytest
docs/            PRD, TRD, ADR, DATA_SPEC, PLAN, recalibración e históricos
.streamlit/      tema claro y oscuro del dashboard
.claude/skills/  skills del equipo para trabajar con agentes
```

Los datos descargados, el modelo del día, el ledger y las líneas reales viven en
`cache/`, que no se sube al repositorio.

---

## Contribuir

El repositorio sigue [GIT_WORKFLOW.md](GIT_WORKFLOW.md): ramas `feature/`, `fix/`,
`refactor/`… que salen de `develop`, commits en Conventional Commits y PR con las
pruebas en verde. Al clonar, activa los hooks una vez:

```bash
git config core.hooksPath .githooks
```

---

## Principios

- **Papel antes que dinero.** Nada real sin ventaja demostrada.
- **El backtest manda, pero no promete.** Las decisiones salen de validación; el
  holdout se mide una sola vez.
- **Sin factores de relleno.** Un factor entra solo si mejora la medición.
- **Contabilidad auditable.** El bankroll se deriva del registro de picks.
- **Un mercado bien hecho** (puntos) antes que cinco a medias.

## Documentación

| Documento | Contenido |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Cambios de cada versión |
| [DESPLIEGUE.md](docs/DESPLIEGUE.md) | Hosting, login y seguridad en producción |
| [RECALIBRACION.md](docs/RECALIBRACION.md) | Datos de ESPN, factores, validación y holdout del modelo v2 |
| [PRD.md](docs/PRD.md) · [TRD.md](docs/TRD.md) | Producto y arquitectura técnica |
| [ADR.md](docs/ADR.md) | Decisiones de arquitectura |
| [DATA_SPEC.md](docs/DATA_SPEC.md) | Fuentes de datos y sus trampas |
| [PLAN.md](docs/PLAN.md) | Plan por fases |
| [GIT_WORKFLOW.md](GIT_WORKFLOW.md) | Ramas, commits, PRs y releases |
| [CALIBRACION.md](docs/CALIBRACION.md) · [baseline.md](docs/baseline.md) · [comparacion.md](docs/comparacion.md) | Mediciones del modelo anterior (histórico) |

---

<sub>Proyecto personal de aprendizaje. Apostar implica riesgo; nada aquí garantiza rentabilidad.</sub>
