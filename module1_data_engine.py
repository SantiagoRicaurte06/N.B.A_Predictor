# ================================================
#  NBA PREDICTOR — MÓDULO 1: DATA ENGINE v2
#  Responsabilidad:
#    - Descargar TODOS los jugadores activos NBA
#    - Filtrar por minutos promedio (15+ min/juego)
#    - Rankear por edge potencial → Top 10 del día
#    - Rastrear injury report diario automático
#    - Calcular efecto de ausencias en compañeros
# ================================================

import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime
from pathlib import Path

from nba_api.stats.endpoints import (
    PlayerGameLog,
    LeagueDashPlayerStats,
    ScoreboardV2,
)
from nba_api.stats.static import players as nba_players_static

# ─────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────

TEMPORADA        = "2025-26"
CACHE_DIR        = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

MIN_MINUTOS      = 15.0   # promedio mínimo de minutos por partido
MIN_JUEGOS       = 15     # mínimo de partidos jugados en la temporada
TOP_JUGADORES    = 10     # cuántos jugadores mostrar por edge
CACHE_LIGA_HORAS = 12     # horas antes de refrescar stats de liga

# ── Filtro temporal ───────────────────────────
MESES_FILTRO     = 2      # solo usar datos de los últimos 2 meses (reducido por bajo rendimiento reciente)
MIN_JUEGOS_TRAS_LESION = 5  # mínimo de juegos desde regreso para usar solo esos datos

# ─────────────────────────────────────────────
# 1. STATS DE TODA LA LIGA
# ─────────────────────────────────────────────

def get_stats_liga(temporada: str = TEMPORADA) -> pd.DataFrame | None:
    """
    Descarga stats agregadas de toda la liga.
    Incluye todos los jugadores con sus promedios de temporada.
    Cache de 12 horas.
    """
    cache_path = CACHE_DIR / f"stats_liga_{temporada}.csv"

    if cache_path.exists():
        edad_horas = (time.time() - cache_path.stat().st_mtime) / 3600
        if edad_horas < CACHE_LIGA_HORAS:
            print(f"  📦 Stats de liga desde cache ({edad_horas:.0f}h)")
            return pd.read_csv(cache_path)

    try:
        print("  → Descargando stats de toda la liga NBA...")
        time.sleep(1)
        stats = LeagueDashPlayerStats(
            season=temporada,
            per_mode_detailed='PerGame',
            timeout=60
        ).get_data_frames()[0]

        stats.to_csv(cache_path, index=False)
        print(f"  ✅ {len(stats)} jugadores con stats de liga")
        return stats

    except Exception as e:
        print(f"  ⚠️  Error descargando stats de liga: {e}")
        return None


def filtrar_jugadores_elegibles(stats_liga: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra jugadores con suficientes minutos y partidos jugados.
    Criterios: 15+ min/juego y 15+ partidos en la temporada.
    """
    cols_num = ['MIN', 'PTS', 'REB', 'AST', 'GP']
    for col in cols_num:
        if col in stats_liga.columns:
            stats_liga[col] = pd.to_numeric(stats_liga[col], errors='coerce')

    elegibles = stats_liga[
        (stats_liga['MIN'] >= MIN_MINUTOS) &
        (stats_liga['GP']  >= MIN_JUEGOS)
    ].copy()

    print(f"  ✅ {len(elegibles)} jugadores elegibles (≥{MIN_MINUTOS} min, ≥{MIN_JUEGOS} juegos)")
    return elegibles


def rankear_por_edge_potencial(elegibles: pd.DataFrame) -> pd.DataFrame:
    """
    Rankea jugadores por potencial de encontrar edge en sus props.
    Mayor producción total = más mercados disponibles = más oportunidades.
    """
    for col in ['PTS', 'REB', 'AST']:
        if col not in elegibles.columns:
            elegibles[col] = 0

    elegibles['produccion_total'] = (
        elegibles['PTS'] +
        elegibles['REB'] * 1.2 +
        elegibles['AST'] * 1.1
    )

    max_prod = elegibles['produccion_total'].max()
    elegibles['edge_score'] = (
        elegibles['produccion_total'] / max_prod if max_prod > 0 else 0
    )

    return elegibles.sort_values('edge_score', ascending=False)

# ─────────────────────────────────────────────
# 2. HISTORIAL DE PARTIDOS
# ─────────────────────────────────────────────

def get_player_gamelog(player_id: int,
                        temporada: str = TEMPORADA,
                        usar_cache: bool = True) -> pd.DataFrame | None:
    """Descarga historial de partidos de un jugador con cache de 6 horas."""
    cache_path = CACHE_DIR / f"gamelog_{player_id}_{temporada}.csv"

    if usar_cache and cache_path.exists():
        edad_horas = (time.time() - cache_path.stat().st_mtime) / 3600
        if edad_horas < 6:
            df = pd.read_csv(cache_path)
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            return df

    try:
        time.sleep(0.6)
        log = PlayerGameLog(
            player_id=player_id,
            season=temporada,
            timeout=30
        ).get_data_frames()[0]

        if log.empty:
            return None

        log['GAME_DATE'] = pd.to_datetime(log['GAME_DATE'])
        log = log.sort_values('GAME_DATE').reset_index(drop=True)

        cols_num = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV',
                    'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM', 'PLUS_MINUS']
        for col in cols_num:
            if col in log.columns:
                log[col] = pd.to_numeric(log[col], errors='coerce')

        log['MIN_num'] = (
            log['MIN'].astype(str).str.split(':').str[0]
        )
        log['MIN_num'] = pd.to_numeric(log['MIN_num'], errors='coerce').fillna(0)

        log.to_csv(cache_path, index=False)
        return log

    except Exception:
        return None


def detectar_regreso_lesion(gamelog: pd.DataFrame) -> datetime | None:
    """
    Detecta si el jugador tuvo una ausencia larga reciente (7+ días entre partidos)
    que sugiere que estuvo lesionado y acaba de regresar.
    Retorna la fecha de regreso si detecta uno, None si no.
    """
    if gamelog is None or len(gamelog) < 3:
        return None

    gl = gamelog.sort_values('GAME_DATE').copy()
    gl['dias_gap'] = gl['GAME_DATE'].diff().dt.days

    # Referencia = ultimo partido (no datetime.now())
    fecha_referencia = gl['GAME_DATE'].max()
    fecha_limite = fecha_referencia - pd.Timedelta(days=60)
    recientes = gl[gl['GAME_DATE'] >= fecha_limite]

    if recientes.empty:
        return None

    # Gap de 10+ días = probable lesión
    lesion = recientes[recientes['dias_gap'] >= 10]

    if lesion.empty:
        return None

    # Tomar el regreso mas reciente
    fecha_regreso = lesion['GAME_DATE'].max()
    # Usar fecha del ultimo partido como referencia
    dias_desde_regreso = (gl['GAME_DATE'].max() - fecha_regreso).days

    # Solo aplica si regreso hace menos de 30 partidos-dias
    if dias_desde_regreso <= 30:
        return fecha_regreso

    return None


def filtrar_gamelog_por_fecha(gamelog: pd.DataFrame,
                               nombre: str = "") -> pd.DataFrame:
    """
    Filtra el gamelog para usar solo los ultimos MESES_FILTRO meses.
    Usa la fecha del ultimo partido como referencia (no datetime.now())
    para evitar filtrar todo cuando la temporada termino hace meses.
    """
    if gamelog is None or gamelog.empty:
        return gamelog

    # Referencia = ultimo partido del jugador, no hoy
    fecha_referencia = gamelog["GAME_DATE"].max()
    fecha_corte_normal = fecha_referencia - pd.DateOffset(months=MESES_FILTRO)

    # Verificar si hay regreso reciente de lesión
    fecha_regreso = detectar_regreso_lesion(gamelog)

    if fecha_regreso is not None:
        # Usar datos desde el regreso
        gl_desde_regreso = gamelog[gamelog['GAME_DATE'] >= fecha_regreso]

        if len(gl_desde_regreso) >= MIN_JUEGOS_TRAS_LESION:
            juegos_pre = len(gamelog[gamelog['GAME_DATE'] < fecha_regreso])
            print(f"    🔄 {nombre}: regreso de lesión detectado "
                  f"({fecha_regreso.strftime('%d %b')}) — "
                  f"usando {len(gl_desde_regreso)} juegos post-regreso "
                  f"(ignorando {juegos_pre} pre-lesión)")
            return gl_desde_regreso.reset_index(drop=True)
        else:
            # Pocos juegos post-regreso — ampliar al filtro normal
            print(f"    ⚠️  {nombre}: regreso reciente pero solo "
                  f"{len(gl_desde_regreso)} juegos — usando filtro estándar")

    # Filtro estándar: últimos 4 meses
    gl_filtrado = gamelog[gamelog['GAME_DATE'] >= fecha_corte_normal]

    juegos_totales  = len(gamelog)
    juegos_filtrados = len(gl_filtrado)
    juegos_excluidos = juegos_totales - juegos_filtrados

    if juegos_excluidos > 0:
        print(f"    📅 {nombre}: {juegos_filtrados} juegos últimos {MESES_FILTRO} meses "
              f"(excluidos {juegos_excluidos} antiguos)")

    return gl_filtrado.reset_index(drop=True)

# ─────────────────────────────────────────────
# 3. INJURY REPORT
# ─────────────────────────────────────────────

def get_injury_report() -> pd.DataFrame:
    """Obtiene injury report actual desde ESPN. Cache de 2 horas."""
    cache_path = CACHE_DIR / "injury_report.csv"

    if cache_path.exists():
        edad_horas = (time.time() - cache_path.stat().st_mtime) / 3600
        if edad_horas < 2:
            return pd.read_csv(cache_path)

    injured = []
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for team_data in data.get('injuries', []):
                team_name = team_data.get('team', {}).get('displayName', '')
                for injury in team_data.get('injuries', []):
                    athlete = injury.get('athlete', {})
                    injured.append({
                        'player_name': athlete.get('displayName', ''),
                        'team': team_name,
                        'status': injury.get('status', 'Unknown'),
                        'reason': injury.get('shortComment', ''),
                    })
    except Exception as e:
        print(f"  ⚠️  Injury report no disponible: {e}")

    df = pd.DataFrame(injured) if injured else pd.DataFrame(
        columns=['player_name', 'team', 'status', 'reason']
    )

    if not df.empty:
        df.to_csv(cache_path, index=False)
        print(f"  ✅ Injury report: {len(df)} jugadores reportados")
    else:
        print("  ⚠️  Injury report vacío — todos asumidos disponibles")

    return df


def detectar_inactividad_reciente(gamelog: pd.DataFrame, dias_umbral: int = 8) -> bool:
    """
    Detecta si un jugador lleva más de N días sin jugar.
    Compara su último GAME_DATE contra la fecha actual.
    """
    if gamelog is None or gamelog.empty or 'GAME_DATE' not in gamelog.columns:
        return False

    ultimo_game_date = pd.to_datetime(gamelog['GAME_DATE']).max()
    dias_sin_jugar = (datetime.now() - ultimo_game_date).days
    return dias_sin_jugar > dias_umbral


def is_player_available(nombre: str, injury_df: pd.DataFrame, gamelogs: dict = None) -> tuple[bool, str]:
    """Verifica disponibilidad de un jugador según injury report y gamelogs."""
    if injury_df.empty:
        disponible_injury = True
    else:
        apellido = nombre.lower().split()[-1]
        match = injury_df[
            injury_df['player_name'].str.lower().str.contains(apellido, na=False)
        ]

        if match.empty:
            disponible_injury = True
        else:
            status = match.iloc[0]['status']
            reason = match.iloc[0].get('reason', '')

            if any(s.lower() in status.lower() for s in ['out', 'inactive', 'dnp', 'doubtful']):
                return False, f"{status}: {reason}"
            elif 'gtd' in status.lower() or 'game time' in status.lower():
                return True, f"GTD: {reason}"
            disponible_injury = True

    # Verificar inactividad por gamelog si está disponible
    if gamelogs and nombre in gamelogs:
        gamelog = gamelogs[nombre]
        if detectar_inactividad_reciente(gamelog):
            return False, "Inactivo +8 días"

    return disponible_injury, "Disponible"

# ─────────────────────────────────────────────
# 4. EQUIPOS QUE JUEGAN HOY
# ─────────────────────────────────────────────

def get_equipos_hoy() -> set[str]:
    """
    Obtiene los equipos que juegan hoy via ESPN API.
    Retorna set de abreviaciones de equipos (ej: {'LAL', 'GSW', 'BOS'}).
    Más confiable que ScoreboardV2 para filtrar por fecha.
    """
    cache_path = CACHE_DIR / "equipos_hoy.json"

    # Cache de 4 horas — el schedule no cambia en el día
    if cache_path.exists():
        edad_horas = (time.time() - cache_path.stat().st_mtime) / 3600
        if edad_horas < 4:
            with open(cache_path) as f:
                equipos = set(json.load(f))
            print(f"  ✅ {len(equipos)} equipos juegan hoy (cache)")
            return equipos

    equipos = set()
    try:
        hoy = datetime.now().strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={hoy}"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            for evento in data.get('events', []):
                for competidor in evento.get('competitions', [{}])[0].get('competitors', []):
                    abrev = competidor.get('team', {}).get('abbreviation', '')
                    if abrev:
                        equipos.add(abrev)

        if equipos:
            with open(cache_path, 'w') as f:
                json.dump(list(equipos), f)
            print(f"  ✅ {len(equipos)} equipos juegan hoy: {', '.join(sorted(equipos))}")
        else:
            print("  ⚠️  No se encontraron partidos hoy — mostrando todos los jugadores")

    except Exception as e:
        print(f"  ⚠️  No se pudo obtener schedule: {e}")

    return equipos


def jugador_juega_hoy(team_abbrev: str, equipos_hoy: set[str]) -> bool:
    """
    Verifica si el equipo de un jugador juega hoy.
    Si no hay equipos detectados, retorna True (no filtrar).
    """
    if not equipos_hoy:
        return True  # si falla el schedule, no filtrar

    # Algunas abreviaciones difieren entre NBA API y ESPN
    mapeo = {
        'NOP': 'NO',  'UTA': 'UTAH', 'GS': 'GSW',
        'PHX': 'PHO', 'SA':  'SAS',  'NY': 'NYK',
    }
    abrev_espn   = mapeo.get(team_abbrev, team_abbrev)
    abrev_nba    = {v: k for k, v in mapeo.items()}.get(team_abbrev, team_abbrev)

    return team_abbrev in equipos_hoy or abrev_espn in equipos_hoy or abrev_nba in equipos_hoy


# ─────────────────────────────────────────────
# 5. SELECCIÓN TOP 10 POR EDGE
# ─────────────────────────────────────────────

def seleccionar_top_jugadores(elegibles: pd.DataFrame,
                               injury_df: pd.DataFrame,
                               equipos_hoy: set,
                               gamelogs: dict = None,
                               top_n: int = TOP_JUGADORES) -> list[dict]:
    """
    Selecciona los top N jugadores por edge potencial.
    Filtra por:
      1. Equipo que juega HOY según ESPN schedule
      2. Disponibles según injury report
      3. No inactivos (+8 días sin jugar)
    """
    seleccionados = []
    excluidos_schedule = 0
    excluidos_inactivos = 0

    for _, row in elegibles.iterrows():
        nombre    = row.get('PLAYER_NAME', '')
        player_id = row.get('PLAYER_ID', None)
        team      = row.get('TEAM_ABBREVIATION', '')

        if not nombre or not player_id:
            continue

        # Filtro 1: ¿juega hoy?
        if not jugador_juega_hoy(team, equipos_hoy):
            excluidos_schedule += 1
            continue

        # Filtro 2: ¿está disponible? (incluye check de inactividad)
        disponible, estado = is_player_available(nombre, injury_df, gamelogs)

        # Filtro 3: Excluir inactivos +8 días
        if gamelogs and nombre in gamelogs:
            if detectar_inactividad_reciente(gamelogs[nombre]):
                excluidos_inactivos += 1
                print(f"    🚫 {nombre} — excluido — inactivo +8 días")
                continue

        seleccionados.append({
            'nombre':     nombre,
            'player_id':  int(player_id),
            'team':       team,
            'disponible': disponible,
            'estado':     estado,
            'es_gtd':     'gtd' in estado.lower(),
            'avg_pts':    round(float(row.get('PTS', 0)), 1),
            'avg_reb':    round(float(row.get('REB', 0)), 1),
            'avg_ast':    round(float(row.get('AST', 0)), 1),
            'avg_min':    round(float(row.get('MIN', 0)), 1),
            'gp':         int(row.get('GP', 0)),
            'edge_score': round(float(row.get('edge_score', 0)), 3),
        })

    disponibles    = [j for j in seleccionados if j['disponible']]
    no_disponibles = [j for j in seleccionados if not j['disponible']]
    top            = disponibles[:top_n]

    print(f"\n  🏆 TOP {top_n} jugadores que juegan HOY (por edge):")
    for i, j in enumerate(top, 1):
        gtd = " ⚠️GTD" if j['es_gtd'] else ""
        print(f"     {i:2}. {j['nombre']:<26} [{j['team']}] "
              f"{j['avg_pts']}pts {j['avg_reb']}reb {j['avg_ast']}ast{gtd}")

    if excluidos_schedule:
        print(f"\n  📅 Excluidos por no jugar hoy: {excluidos_schedule} jugadores")
    if excluidos_inactivos:
        print(f"  🚫 Excluidos por inactividad +8 días: {excluidos_inactivos} jugadores")
    if no_disponibles:
        print(f"  ❌ Excluidos por injury report: {len(no_disponibles)} jugadores")

    return top

# ─────────────────────────────────────────────
# 5. EFECTOS DE AUSENCIAS
# ─────────────────────────────────────────────

def calcular_efecto_ausencia(jugador_nombre: str,
                              ausente_nombre: str,
                              gamelog_jugador: pd.DataFrame,
                              gamelog_ausente: pd.DataFrame) -> dict:
    """
    Calcula cómo cambian las stats de un jugador cuando falta un compañero.
    """
    if gamelog_jugador is None or gamelog_ausente is None:
        return {}

    fechas_ausente = set(
        gamelog_ausente['GAME_DATE'].dt.strftime('%Y-%m-%d').tolist()
    )

    gl = gamelog_jugador.copy()
    gl['fecha_str'] = gl['GAME_DATE'].dt.strftime('%Y-%m-%d')

    con_comp = gl[gl['fecha_str'].isin(fechas_ausente)]
    sin_comp = gl[~gl['fecha_str'].isin(fechas_ausente)]

    ajustes = {}
    for stat in ['PTS', 'REB', 'AST', 'MIN_num']:
        if stat not in gl.columns:
            continue
        if len(con_comp) < 3 or len(sin_comp) < 3:
            ajustes[stat] = 1.0
            continue

        avg_con = con_comp[stat].mean()
        avg_sin = sin_comp[stat].mean()
        mult = np.clip(avg_sin / avg_con, 0.70, 1.50) if avg_con > 0 else 1.0
        ajustes[stat] = round(mult, 3)

    return ajustes

# ─────────────────────────────────────────────
# 6. PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def cargar_todos_los_datos() -> dict:
    """
    Orquesta toda la carga de datos.
    Retorna dict con todo lo necesario para módulos 2 y 3.
    """
    print("\n" + "="*55)
    print("  📦 MÓDULO 1: DATA ENGINE v2")
    print("  Cobertura: Toda la NBA (15+ min/juego)")
    print("="*55)

    # Paso 1 — Stats de liga
    print("\n  → Paso 1/5: Stats de la liga...")
    stats_liga = get_stats_liga()
    if stats_liga is None:
        return {}

    # Paso 2 — Filtrar elegibles
    print("\n  → Paso 2/5: Filtrando jugadores elegibles...")
    elegibles = filtrar_jugadores_elegibles(stats_liga)

    # Paso 3 — Rankear
    print("\n  → Paso 3/5: Rankeando por edge potencial...")
    elegibles = rankear_por_edge_potencial(elegibles)

    # Paso 4 — Injury report
    print("\n  → Paso 4/6: Cargando injury report...")
    injury_df = get_injury_report()

    # Paso 5 — Equipos que juegan hoy
    print("\n  → Paso 5/6: Obteniendo partidos de hoy...")
    equipos_hoy = get_equipos_hoy()

    # Paso 6 — Top 10 (sin filtro de inactividad aún, no tenemos gamelogs)
    print("\n  → Paso 6/8: Seleccionando Top 10 que juegan hoy...")
    jugadores_hoy = seleccionar_top_jugadores(elegibles, injury_df, equipos_hoy, gamelogs={}, top_n=TOP_JUGADORES)

    if not jugadores_hoy:
        print("  ❌ Sin jugadores seleccionados")
        return {}

    # Paso 7 — Gamelogs del top 10
    print(f"\n  → Paso 7/8: Descargando historial de los Top {TOP_JUGADORES}...")
    gamelogs = {}
    for j in jugadores_hoy:
        nombre = j['nombre']
        print(f"    📥 {nombre}...", end=' ', flush=True)
        gl = get_player_gamelog(j['player_id'])
        if gl is not None and not gl.empty:
            # Aplicar filtro de 2 meses con excepción por lesión
            gl = filtrar_gamelog_por_fecha(gl, nombre)
            if len(gl) >= 5:  # Reducido de 10 a 5 para permitir más jugadores
                gamelogs[nombre] = gl
                print(f"✅ ({len(gl)} juegos filtrados)")
            else:
                print(f"⚠️  solo {len(gl)} juegos tras filtro — insuficiente")
        else:
            print("⚠️  sin datos")

    # Paso 8 — Filtrar inactivos (+8 días sin jugar)
    print("\n  → Paso 8/8: Filtrando jugadores inactivos...")
    jugadores_hoy = [
        j for j in jugadores_hoy
        if not (j['nombre'] in gamelogs and detectar_inactividad_reciente(gamelogs[j['nombre']]))
    ]

    # Paso 9 — Efectos de ausencias
    print("\n  → Calculando efectos de ausencias entre compañeros...")
    efectos_ausencia = {}
    equipos = {}

    for nombre, gl in gamelogs.items():
        if 'Team_Abbreviation' in gl.columns:
            team = gl['Team_Abbreviation'].iloc[-1]
            equipos.setdefault(team, []).append(nombre)

    for team, compañeros in equipos.items():
        if len(compañeros) < 2:
            continue
        for jugador in compañeros:
            efectos_ausencia[jugador] = {}
            for ausente in compañeros:
                if ausente == jugador:
                    continue
                if jugador in gamelogs and ausente in gamelogs:
                    ajustes = calcular_efecto_ausencia(
                        jugador, ausente,
                        gamelogs[jugador], gamelogs[ausente]
                    )
                    if ajustes:
                        efectos_ausencia[jugador][ausente] = ajustes

    ausentes_hoy = [j['nombre'] for j in jugadores_hoy if not j['disponible']]

    print("\n  ✅ Data Engine completo\n")

    return {
        'stats_liga':       elegibles,
        'gamelogs':         gamelogs,
        'injury_df':        injury_df,
        'jugadores_hoy':    jugadores_hoy,
        'efectos_ausencia': efectos_ausencia,
        'ausentes_hoy':     ausentes_hoy,
        'temporada':        TEMPORADA,
        'timestamp':        datetime.now().isoformat()
    }


if __name__ == "__main__":
    datos = cargar_todos_los_datos()
    if datos:
        print("\n📊 RESUMEN FINAL:")
        print(f"  Top jugadores seleccionados : {len(datos['jugadores_hoy'])}")
        print(f"  Gamelogs descargados        : {len(datos['gamelogs'])}")
        print(f"  Ausentes hoy                : {len(datos['ausentes_hoy'])}")
