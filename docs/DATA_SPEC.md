# DATA SPEC — NBA Predictor Pro

**Diccionario de datos y contratos de fuentes**
**Autor:** Santiago Ricaurte · **Fecha:** 2026-07-24 · **Documentos relacionados:** [PRD.md](PRD.md), [TRD.md](TRD.md), [ADR.md](ADR.md)

Este documento describe cada fuente de datos, sus campos reales, sus rarezas y las trampas conocidas. Es la referencia obligada para el rediseño del modelo (ADR-002): varias features actuales dependen de datos que **no existen de forma fiable** en las fuentes, y eso hay que saberlo antes de reconstruir.

---

## 1. Panorama de fuentes

| Fuente | Librería/Endpoint | Qué provee | Fiabilidad |
|--------|-------------------|-----------|------------|
| Stats de liga | `nba_api` · `LeagueDashPlayerStats` | Promedios de temporada por jugador | Alta |
| Gamelog jugador | `nba_api` · `PlayerGameLog` | Partido a partido de un jugador | Alta, pero **columnas limitadas** |
| Injury report | ESPN · `.../basketball/nba/injuries` | Lesionados/dudosos del día | Media (matching frágil) |
| Partidos de hoy | ESPN · `.../basketball/nba/scoreboard` | Equipos que juegan hoy | Alta |
| Odds | The Odds API · `basketball_nba` | Líneas y cuotas | **Props solo en plan de pago** |

---

## 2. `nba_api` — LeagueDashPlayerStats

**Llamada:** `LeagueDashPlayerStats(season, per_mode_detailed='PerGame', timeout=60)`
**Cache:** `cache/stats_liga_{season}.csv` · TTL 12h
**Granularidad:** una fila por jugador (promedios de temporada).

| Campo | Tipo | Descripción | Uso actual |
|-------|------|-------------|-----------|
| `PLAYER_ID` | int | ID único NBA del jugador | Clave para pedir gamelog |
| `PLAYER_NAME` | str | Nombre completo | Display, matching injury |
| `TEAM_ABBREVIATION` | str | Abreviación del equipo (ver §7 rareza) | Filtro "juega hoy" |
| `GP` | int | Partidos jugados en la temporada | Filtro elegibilidad (≥15) |
| `MIN` | float | Minutos promedio | Filtro elegibilidad (≥15) |
| `PTS` / `REB` / `AST` | float | Promedios por partido | Ranking edge, contexto |

*(El endpoint devuelve muchas más columnas — FG_PCT, STL, BLK, etc. — pero el código solo consume las de arriba.)*

---

## 3. `nba_api` — PlayerGameLog

**Llamada:** `PlayerGameLog(player_id, season, timeout=30)`
**Cache:** `cache/gamelog_{player_id}_{season}.csv` · TTL 6h · `time.sleep(0.6)` entre llamadas
**Granularidad:** una fila por partido jugado por ese jugador. **Es la fuente principal para el modelo.**

| Campo | Tipo | Descripción | Nota |
|-------|------|-------------|------|
| `GAME_DATE` | datetime | Fecha del partido | Se parsea y ordena ascendente |
| `MATCHUP` | str | Ej. `"LAL vs. GSW"` (local) o `"LAL @ GSW"` (visitante) | `vs.` = local; `@` = visitante |
| `WL` | str | `"W"` o `"L"` | |
| `MIN` | **str** | **Llega como texto `"35:00"`** | Ver §7 — trampa crítica |
| `PTS` | int | Puntos — **el target del modelo** | |
| `REB` / `AST` / `STL` / `BLK` / `TOV` | int | Stats de la caja | |
| `FGA` / `FGM` | int | Tiros de campo intentados/anotados | |
| `FG3A` / `FG3M` | int | Triples intentados/anotados | |
| `FTA` / `FTM` | int | Tiros libres intentados/anotados | |
| `PLUS_MINUS` | int | +/- del jugador en el partido | |

### Campo derivado que el código crea
| Campo | Cómo se calcula | Trampa |
|-------|-----------------|--------|
| `MIN_num` | `MIN.split(':')[0]` → int | **Descarta los segundos**; en DNP `MIN` puede venir vacío → `fillna(0)` |

---

## 4. ESPN — Injury Report

**Endpoint:** `GET site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries`
**Cache:** `cache/injury_report.csv` · TTL 2h

Estructura de respuesta relevante:
```
injuries[]
  └─ team.displayName
  └─ injuries[]
       ├─ athlete.displayName
       ├─ status          ("Out", "Day-To-Day", "GTD", ...)
       └─ shortComment    (razón)
```

DataFrame resultante (`injury_report.csv`):
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `player_name` | str | Nombre del jugador lesionado |
| `team` | str | Nombre largo del equipo |
| `status` | str | Estado de la lesión |
| `reason` | str | Comentario corto |

**Valores de `status` que el código interpreta:**
- Excluyen al jugador: `out`, `inactive`, `dnp`, `doubtful`
- Marca GTD (juega pero incierto): `gtd`, `game time`
- Cualquier otro → se asume disponible

---

## 5. ESPN — Scoreboard (partidos de hoy)

**Endpoint:** `GET .../basketball/nba/scoreboard?dates=YYYYMMDD`
**Cache:** `cache/equipos_hoy.json` · TTL 4h · guarda una lista de abreviaciones.

Estructura relevante:
```
events[]
  └─ competitions[0].competitors[]
       └─ team.abbreviation   → ej. "LAL", "GSW"
```
Salida: `set` de abreviaciones de equipos que juegan hoy.

---

## 6. The Odds API — Player Props

**Endpoint:** `.../v4/sports/basketball_nba/events/{event_id}/odds`
**Params:** `regions='eu,us'`, `markets='player_points,player_rebounds,player_assists,totals'`, `oddsFormat='decimal'`
**Cache:** `cache/odds_cache.json` · TTL 1h

> **Restricción crítica:** los mercados `player_*` **requieren plan de pago**. El tier gratis (500 req/mes) solo entrega `spreads`, `totals`, `h2h`. Por eso v1 usa entrada manual (ADR-005).

Estructura de un outcome de prop:
```
bookmakers[].markets[] (key = "player_points")
  └─ outcomes[]
       ├─ name         → nombre del jugador
       ├─ point        → la línea (ej. 25.5)
       ├─ price        → cuota decimal (ej. 1.87)
       └─ description  → "Over" / "Under"
```
Parseado a: `{"Jugador_PTS": {"linea": 25.5, "odds_over": 1.87, "odds_under": 1.95}}`

---

## 7. Rarezas y trampas de datos (sección crítica)

Estas son las que hay que tener presentes al reconstruir el modelo. Varias explican comportamiento errático actual.

### 7.1 `MIN` llega como texto `"MM:SS"`
`PlayerGameLog` devuelve minutos como string `"35:00"`, no como número. El código hace `split(':')[0]` → pierde los segundos y, en partidos DNP, el valor puede ser vacío/None → se rellena con 0. **Implicación:** un DNP con `MIN=""` se vuelve `MIN_num=0`, lo cual es correcto, pero hay que filtrar esos partidos antes de entrenar o contaminan las features.

### 7.2 Abreviaciones de equipo NO coinciden entre NBA API y ESPN
El mismo equipo tiene abreviación distinta según la fuente. El código mantiene un mapeo manual:
```
NOP↔NO · UTA↔UTAH · GS↔GSW · PHX↔PHO · SA↔SAS · NY↔NYK
```
**Implicación:** cualquier cruce por equipo (filtro "juega hoy", efectos de ausencia) debe normalizar con este mapeo o falla en silencio.

### 7.3 Matching de lesiones por apellido (frágil)
`is_player_available()` cruza jugadores contra el injury report buscando el **apellido como substring**. **Riesgo:** dos jugadores con el mismo apellido (ej. varios "Williams", "Jones") producen falsos positivos/negativos. Es una fuente de error silenciosa.

### 7.4 **Features de equipo/rival que NO existen en el gamelog** ← la más importante
`PlayerGameLog` **no** trae stats agregadas del equipo ni del rival. Sin embargo, module2 calcula features que las necesitan:

| Feature | Campo que necesita | Realidad |
|---------|-------------------|----------|
| `usage_rate` | `TEAM_FGA` | **No existe** → el código lo finge: `TEAM_FGA = FGA * 5` |
| `off_reb_rate` | `TEAM_OREB` | No existe → default 1 |
| `def_reb_rate` | `TEAM_DREB` | No existe → default 1 |
| `defensive_rating` del rival | stats del oponente | Se pasa `None` casi siempre |
| `opponent_pace` | pace del rival | Se usa el pace del propio jugador como proxy |

**Implicación grave:** varias de las "features críticas v2" (usage, rebound rate, ajuste por defensa del rival) están construidas sobre **datos inventados o ausentes**. En el rediseño (ADR-002) hay que decidir: o se traen estos datos de un endpoint real (`LeagueDashTeamStats`, `BoxScoreAdvanced`, etc.), o se eliminan esas features en vez de alimentarlas con ruido.

### 7.5 `es_gtd` depende del texto de ESPN
La marca GTD sale de buscar substrings en el `status` de ESPN. Si ESPN cambia el texto (`"GTD"` vs `"Game-Time Decision"` vs `"Questionable"`), la detección se rompe.

---

## 8. Inventario de archivos en `cache/`

| Archivo | Formato | Contenido | Nota |
|---------|---------|-----------|------|
| `stats_liga_{season}.csv` | CSV | Stats de liga | TTL 12h |
| `gamelog_{player_id}_{season}.csv` | CSV | Gamelog por jugador | TTL 6h |
| `injury_report.csv` | CSV | Lesionados | TTL 2h |
| `equipos_hoy.json` | JSON | Lista de abreviaciones | TTL 4h |
| `config.json` | JSON | `odds_api_key` | **SECRETO — nunca commitear** (ya en `.gitignore`) |
| `odds_cache.json` | JSON | Odds cacheadas | TTL 1h |
| `bankroll.json` | JSON | Estado del bankroll | **CORRUPTO — se reemplaza (ADR-007)** |
| `historial_apuestas.csv` | CSV | Registro de picks | Base del nuevo tracking |
| `patrones_error.json` | JSON | Salida de diagnóstico | Módulo 5 |
| `mejoras_aplicadas.json` | JSON | Correcciones auto | **Se elimina el lazo (ADR-004)** |
| `reportes/reporte_{fecha}.txt` | TXT | Reportes de análisis | |

---

## 9. Gaps de datos a resolver en el rediseño

Resumen accionable para el modelo pooled (ADR-002):

1. **Conseguir stats reales de equipo y rival** (usage, pace, defensive rating) desde endpoints apropiados de `nba_api`, o eliminar las features que hoy se alimentan con valores fingidos (§7.4).
2. **Robustecer el matching de lesiones** — usar `PLAYER_ID` en vez de apellido cuando sea posible (§7.3).
3. **Filtrar DNP correctamente** antes de entrenar (§7.1).
4. **Normalizar abreviaciones** en un solo punto para todos los cruces por equipo (§7.2).
5. **Líneas históricas de props** para el backtest — no vienen de ninguna fuente actual; es la pregunta abierta #1 del TRD.
