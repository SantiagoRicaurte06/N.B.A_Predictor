"""
Factores que explican los puntos de un jugador en un partido.

REGLA DE ORO: todo factor se calcula con información disponible ANTES del
partido: la historia previa, quién está fuera (reporte de lesiones), el
calendario y las líneas de la casa. Si un factor usara el propio partido, el
backtest mentiría.

Los factores van en grupos para poder medir qué aporta cada uno (ablación):
un grupo que no mejora la validación no entra al modelo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nba_predictor.datos.arenas import EQUIPOS_NBA, altitud, desfase, distancia_km

POSICION = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}

MIN_PARTIDOS_PREVIOS = 10   # historia mínima del jugador para predecir
MIN_MINUTOS_L10 = 15.0      # jugadores de rotación: los que tienen línea de props
ROTACION_MIN_L10 = 12.0     # para contar a alguien como ausencia relevante
ROTACION_DIAS = 25          # sin jugar en más tiempo, ya no cuenta como "ausente hoy"

GRUPOS = {
    # Lo que ya usaba el modelo anterior (pooled v1): historia del jugador.
    "base": ["pts_l5", "pts_l10", "pts_std_l10", "pts_tendencia", "min_l10",
             "fga_l10", "fg3a_l10", "fta_l10", "local", "descanso_jugador",
             "b2b", "partido_n", "victorias_l10"],
    "jugador": ["pts_l20", "pts_temporada", "pts_temp_anterior", "ppm_l20", "min_l5",
                "min_tendencia", "titular_l10", "titular_ultimo", "partidos_perdidos",
                "partidos_en_equipo", "min_ultimo"],
    "ausencias": ["aus_n", "aus_min", "aus_pts", "aus_fga", "aus_frac_pts",
                  "estrella_fuera", "cuota_pts", "rango_pts_hoy"],
    "rival": ["rival_drtg_l15", "rival_ritmo_l15", "rival_def_pos",
              "rival_aus_min", "rival_aus_pts", "rival_estrella_fuera"],
    "equipo": ["ritmo_l15", "ortg_l15"],
    "calendario": ["equipo_3en4", "rival_descanso", "rival_b2b", "viaje_km",
                   "cambio_huso", "altitud_sede"],
    "lineas": ["spread_equipo", "total_linea", "total_implicito", "spread_abs"],
    "motivacion": ["victorias_temp", "rival_victorias_temp", "racha5",
                   "playoffs", "tramo_final", "contra_ex_equipo"],
}


def columnas(grupos: list[str]) -> list[str]:
    return [c for g in grupos for c in GRUPOS[g]]


# ─────────────────────────────────────────────
# Limpieza
# ─────────────────────────────────────────────

def _limpiar(jp: pd.DataFrame, ep: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Fuera el All-Star Game y cualquier exhibición: solo los 30 equipos NBA.
    ep = ep[ep["equipo"].isin(EQUIPOS_NBA) & ep["rival"].isin(EQUIPOS_NBA)].copy()
    jp = jp[jp["evento"].isin(set(ep["evento"]))].copy()
    jp["posicion"] = jp["posicion"].map(POSICION).fillna("F")
    # Las filas de hoy (es_hoy) aún no tienen minutos: "juega" quiere decir
    # que no figura como baja en el reporte de lesiones.
    es_hoy = jp["es_hoy"].fillna(False).astype(bool) if "es_hoy" in jp else False
    jp["jugo"] = ~jp["no_jugo"] & ((jp["MIN"].fillna(0) > 0) | es_hoy)
    return jp, ep


# ─────────────────────────────────────────────
# Equipo-partido: calendario, ritmo, eficiencia, motivación
# ─────────────────────────────────────────────

def _rolling_previo(s: pd.Series, grupos, n: int, minimo: int = 3) -> pd.Series:
    """Media de los n partidos ANTERIORES (shift 1) dentro de cada grupo."""
    return s.groupby(grupos).transform(lambda x: x.shift(1).rolling(n, min_periods=minimo).mean())


def _factores_equipo(ep: pd.DataFrame) -> pd.DataFrame:
    ep = ep.sort_values(["equipo", "fecha_utc"]).reset_index(drop=True)

    # Posesiones del partido: promedio de las dos estimaciones (más estable).
    rival_pos = ep[["evento", "equipo", "posesiones"]].rename(
        columns={"equipo": "rival", "posesiones": "posesiones_rival"})
    ep = ep.merge(rival_pos, on=["evento", "rival"], how="left")
    pos = ((ep["posesiones"] + ep["posesiones_rival"]) / 2).clip(80, 125)
    ep["ritmo"] = pos
    ep["ortg"] = ep["pts"] / pos * 100
    ep["drtg"] = ep["pts_rival"] / pos * 100
    ep["gano"] = (ep["pts"] > ep["pts_rival"]).astype(float)

    g_eq = ep["equipo"]
    g_temp = [ep["equipo"], ep["temporada"]]
    ep["ritmo_l15"] = _rolling_previo(ep["ritmo"], g_eq, 15)
    ep["ortg_l15"] = _rolling_previo(ep["ortg"], g_eq, 15)
    ep["drtg_l15"] = _rolling_previo(ep["drtg"], g_eq, 15)
    ep["victorias_l10"] = _rolling_previo(ep["gano"], g_eq, 10)
    ep["racha5"] = ep.groupby("equipo")["gano"].transform(
        lambda x: x.shift(1).rolling(5, min_periods=1).sum())

    ep["partido_n"] = ep.groupby(g_temp).cumcount() + 1
    jugados = ep.groupby(g_temp).cumcount()
    ganados = ep.groupby(g_temp)["gano"].transform(lambda x: x.shift(1).fillna(0).cumsum())
    ep["victorias_temp"] = np.where(jugados > 0, ganados / jugados.replace(0, np.nan), 0.5)

    # Calendario
    dias = ep.groupby("equipo")["fecha"].diff().dt.days
    ep["descanso"] = dias.fillna(7).clip(0, 7)
    ep["b2b_equipo"] = (ep["descanso"] == 1).astype(int)
    prev2 = ep.groupby("equipo")["fecha"].shift(2)
    ep["equipo_3en4"] = ((ep["fecha"] - prev2).dt.days <= 3).astype(int)

    # Viaje: la sede es la del local (los partidos neutrales son casi nulos).
    ep["sede"] = np.where(ep["local"], ep["equipo"], ep["rival"])
    sede_prev = ep.groupby("equipo")["sede"].shift(1)
    ep["viaje_km"] = [distancia_km(a, b) if isinstance(a, str) else 0.0
                      for a, b in zip(sede_prev, ep["sede"])]
    ep["cambio_huso"] = [desfase(b) - desfase(a) if isinstance(a, str) else 0
                         for a, b in zip(sede_prev, ep["sede"])]
    ep["altitud_sede"] = ep["sede"].map(altitud)

    # Líneas de la casa
    ep["total_implicito"] = ep["total_linea"] / 2 - ep["spread_equipo"] / 2
    ep["spread_abs"] = ep["spread_equipo"].abs()

    ep["playoffs"] = (ep["tipo"] == 3).astype(int)
    ep["tramo_final"] = (ep["partido_n"] >= 65).astype(int)
    return ep


# ─────────────────────────────────────────────
# Jugador-partido: historia del propio jugador
# ─────────────────────────────────────────────

def _factores_jugador(jug: pd.DataFrame) -> pd.DataFrame:
    """Sobre los partidos JUGADOS, ordenados por jugador y fecha."""
    jug = jug.sort_values(["athlete_id", "fecha_utc"]).reset_index(drop=True)
    g = jug.groupby("athlete_id")

    def prev(col, n, minimo=3, fn="mean"):
        return g[col].transform(lambda x: getattr(x.shift(1).rolling(n, min_periods=minimo), fn)())

    jug["pts_l5"] = prev("PTS", 5, 2)
    jug["pts_l10"] = prev("PTS", 10)
    jug["pts_l20"] = prev("PTS", 20)
    jug["pts_std_l10"] = prev("PTS", 10, 3, "std")
    jug["pts_tendencia"] = jug["pts_l5"] - jug["pts_l20"]
    jug["min_l5"] = prev("MIN", 5, 2)
    jug["min_l10"] = prev("MIN", 10)
    jug["min_tendencia"] = jug["min_l5"] - jug["min_l10"]
    jug["fga_l10"] = prev("FGA", 10)
    jug["fg3a_l10"] = prev("FG3A", 10)
    jug["fta_l10"] = prev("FTA", 10)
    jug["titular_l10"] = prev("titular_f", 10, 1)
    jug["titular_ultimo"] = g["titular_f"].shift(1)
    jug["min_ultimo"] = g["MIN"].shift(1)
    pts20 = g["PTS"].transform(lambda x: x.shift(1).rolling(20, min_periods=5).sum())
    min20 = g["MIN"].transform(lambda x: x.shift(1).rolling(20, min_periods=5).sum())
    jug["ppm_l20"] = pts20 / min20.replace(0, np.nan)
    jug["n_previos"] = g.cumcount()

    gt = jug.groupby(["athlete_id", "temporada"])
    jug["pts_temporada"] = gt["PTS"].transform(lambda x: x.shift(1).expanding().mean())
    media_temp = jug.groupby(["athlete_id", "temporada"])["PTS"].mean().rename("pts_temp_anterior").reset_index()
    orden = sorted(jug["temporada"].unique())
    siguiente = {t: orden[i + 1] for i, t in enumerate(orden[:-1])}
    media_temp["temporada"] = media_temp["temporada"].map(siguiente)
    jug = jug.merge(media_temp.dropna(subset=["temporada"]), on=["athlete_id", "temporada"], how="left")

    jug["fecha_prev"] = jug.groupby("athlete_id")["fecha"].shift(1)
    jug["descanso_jugador"] = (jug["fecha"] - jug["fecha_prev"]).dt.days.fillna(7).clip(0, 7)
    jug["b2b"] = (jug["descanso_jugador"] == 1).astype(int)

    # Partidos de su equipo que se perdió justo antes (vuelta de lesión).
    idx_prev = jug.groupby("athlete_id")["idx_equipo"].shift(1)
    eq_prev = jug.groupby("athlete_id")["equipo"].shift(1)
    perdidos = (jug["idx_equipo"] - idx_prev - 1).where(eq_prev == jug["equipo"], 0)
    jug["partidos_perdidos"] = perdidos.fillna(0).clip(0, 30)
    jug["partidos_en_equipo"] = jug.groupby(["athlete_id", "equipo"]).cumcount()
    return jug


# ─────────────────────────────────────────────
# Ausencias: quién de la rotación no juega hoy
# ─────────────────────────────────────────────

def _ausencias(jp: pd.DataFrame, ep: pd.DataFrame, jug: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Para cada equipo-partido, los jugadores de rotación que NO juegan.

    Un jugador es de la rotación si, antes del partido, su último equipo es
    este, jugó hace menos de ROTACION_DIAS días y promedia al menos
    ROTACION_MIN_L10 minutos. Su "peso" es lo que venía aportando (puntos,
    minutos y tiros de sus últimos 10 partidos), medido ANTES del partido.

    Las ausencias se conocen antes del partido por el reporte de lesiones;
    los que se caen a última hora son la excepción.
    """
    # Estado de cada jugador DESPUÉS de cada partido jugado.
    estado = jug[["athlete_id", "fecha_utc", "equipo", "temporada"]].copy()
    gj = jug.groupby("athlete_id")
    estado["min_post"] = gj["MIN"].transform(lambda x: x.rolling(10, min_periods=3).mean())
    estado["pts_post"] = gj["PTS"].transform(lambda x: x.rolling(10, min_periods=3).mean())
    estado["fga_post"] = gj["FGA"].transform(lambda x: x.rolling(10, min_periods=3).mean())
    estado = estado.rename(columns={"equipo": "equipo_estado", "fecha_utc": "fecha_estado"})

    tg = ep[["evento", "equipo", "fecha_utc", "temporada"]]
    plantel = jug[["temporada", "equipo", "athlete_id"]].drop_duplicates()
    pares = tg.merge(plantel, on=["temporada", "equipo"])
    pares = pd.merge_asof(
        pares.sort_values("fecha_utc"), estado.sort_values("fecha_estado"),
        left_on="fecha_utc", right_on="fecha_estado", by="athlete_id",
        allow_exact_matches=False, direction="backward",
    )
    dias = (pares["fecha_utc"] - pares["fecha_estado"]).dt.days
    rot = pares[(pares["equipo_estado"] == pares["equipo"]) & (dias <= ROTACION_DIAS)
                & (pares["min_post"] >= ROTACION_MIN_L10)].copy()

    jugaron = set(zip(jp.loc[jp["jugo"], "evento"], jp.loc[jp["jugo"], "athlete_id"]))
    rot["juega"] = [(e, a) in jugaron for e, a in zip(rot["evento"], rot["athlete_id"])]

    # La estrella es el máximo anotador de la rotación con 20+ puntos.
    rot["max_pts_equipo"] = rot.groupby(["evento", "equipo"])["pts_post"].transform("max")
    rot["es_estrella"] = (rot["pts_post"] == rot["max_pts_equipo"]) & (rot["pts_post"] >= 20)

    aus = rot[~rot["juega"]]
    disp = rot[rot["juega"]]
    clave = ["evento", "equipo"]
    por_equipo = pd.DataFrame({
        "aus_n": aus.groupby(clave).size(),
        "aus_min": aus.groupby(clave)["min_post"].sum(),
        "aus_pts": aus.groupby(clave)["pts_post"].sum(),
        "aus_fga": aus.groupby(clave)["fga_post"].sum(),
        "estrella_fuera": aus.groupby(clave)["es_estrella"].any().astype(int),
    })
    por_equipo = tg[clave].drop_duplicates().set_index(clave).join(por_equipo).fillna(0)
    total_pts = rot.groupby(clave)["pts_post"].sum()
    por_equipo["aus_frac_pts"] = (por_equipo["aus_pts"] / total_pts.reindex(por_equipo.index)).fillna(0)
    por_equipo["pts_disponibles"] = disp.groupby(clave)["pts_post"].sum().reindex(por_equipo.index)

    # Rango del jugador entre los disponibles hoy (1 = primera opción).
    disp = disp.assign(rango_pts_hoy=disp.groupby(clave)["pts_post"].rank(ascending=False, method="min"))
    rango = disp[["evento", "athlete_id", "rango_pts_hoy"]]
    return por_equipo.reset_index(), rango


# ─────────────────────────────────────────────
# Defensa del rival contra cada posición
# ─────────────────────────────────────────────

def _defensa_por_posicion(jug: pd.DataFrame, ep: pd.DataFrame) -> pd.DataFrame:
    """Puntos que el rival permite a cada posición, relativo a la liga."""
    permitidos = (jug.groupby(["evento", "rival", "posicion"])["PTS"].sum()
                  .rename("pts_pos").reset_index())
    base = ep[["evento", "equipo", "fecha_utc", "temporada"]].rename(columns={"equipo": "rival"})
    filas = base.merge(pd.DataFrame({"posicion": ["G", "F", "C"]}), how="cross")
    filas = filas.merge(permitidos, on=["evento", "rival", "posicion"], how="left").fillna({"pts_pos": 0})
    filas = filas.sort_values(["rival", "posicion", "fecha_utc"])
    filas["def_pos_l15"] = filas.groupby(["rival", "posicion"])["pts_pos"].transform(
        lambda x: x.shift(1).rolling(15, min_periods=5).mean())
    # Media de la liga con días ANTERIORES solamente. Fila a fila no sirve:
    # los dos equipos de un partido comparten hora y uno vería al otro.
    filas["dia"] = filas["fecha_utc"].dt.normalize()
    diario = (filas.groupby(["temporada", "posicion", "dia"])["pts_pos"]
              .agg(["sum", "count"]).sort_index())
    previo = diario.groupby(level=[0, 1]).cumsum().groupby(level=[0, 1]).shift(1)
    liga = (previo["sum"] / previo["count"]).where(previo["count"] >= 50).rename("liga")
    filas = filas.merge(liga.reset_index(), on=["temporada", "posicion", "dia"], how="left")
    filas["rival_def_pos"] = filas["def_pos_l15"] / filas["liga"]
    return filas[["evento", "rival", "posicion", "rival_def_pos"]]


# ─────────────────────────────────────────────
# Ensamblado
# ─────────────────────────────────────────────

def construir(jp: pd.DataFrame, ep: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla de entrenamiento/predicción: una fila por jugador de rotación y
    partido jugado, con todos los factores y los objetivos PTS y MIN.
    """
    jp, ep = _limpiar(jp, ep)
    ep = _factores_equipo(ep)
    ep["idx_equipo"] = ep.groupby("equipo").cumcount()

    jug = jp[jp["jugo"]].copy()
    jug["titular_f"] = jug["titular"].astype(float)
    jug = jug.merge(ep[["evento", "equipo", "idx_equipo"]], on=["evento", "equipo"], how="left")
    jug = _factores_jugador(jug)

    aus_eq, rango = _ausencias(jp, ep, jug)
    def_pos = _defensa_por_posicion(jug, ep)

    # Primera vez que el jugador vistió cada camiseta: para "contra su exequipo".
    primera = jug.groupby(["athlete_id", "equipo"])["fecha_utc"].min().rename("primera_vez").reset_index()

    cols_eq = ["evento", "equipo", "partido_n", "victorias_l10", "victorias_temp", "racha5",
               "ritmo_l15", "ortg_l15", "equipo_3en4", "viaje_km", "cambio_huso",
               "altitud_sede", "spread_equipo", "total_linea", "total_implicito",
               "spread_abs", "playoffs", "tramo_final", "local"]
    df = jug.drop(columns=["local"]).merge(ep[cols_eq], on=["evento", "equipo"], how="left")

    rival = ep[["evento", "equipo", "drtg_l15", "ritmo_l15", "descanso", "b2b_equipo",
                "victorias_temp"]].rename(columns={
        "equipo": "rival", "drtg_l15": "rival_drtg_l15", "ritmo_l15": "rival_ritmo_l15",
        "descanso": "rival_descanso", "b2b_equipo": "rival_b2b",
        "victorias_temp": "rival_victorias_temp"})
    df = df.merge(rival, on=["evento", "rival"], how="left")

    df = df.merge(aus_eq.drop(columns=["pts_disponibles"]), on=["evento", "equipo"], how="left")
    df = df.merge(aus_eq[["evento", "equipo", "pts_disponibles"]], on=["evento", "equipo"], how="left")
    aus_rival = aus_eq[["evento", "equipo", "aus_min", "aus_pts", "estrella_fuera"]].rename(columns={
        "equipo": "rival", "aus_min": "rival_aus_min", "aus_pts": "rival_aus_pts",
        "estrella_fuera": "rival_estrella_fuera"})
    df = df.merge(aus_rival, on=["evento", "rival"], how="left")
    df = df.merge(rango, on=["evento", "athlete_id"], how="left")
    df["cuota_pts"] = df["pts_l10"] / df["pts_disponibles"].replace(0, np.nan)
    df = df.merge(def_pos, on=["evento", "rival", "posicion"], how="left")

    df = df.merge(primera.rename(columns={"equipo": "rival"}), on=["athlete_id", "rival"], how="left")
    df["contra_ex_equipo"] = (df["primera_vez"] < df["fecha_utc"]).astype(int)

    df["local"] = df["local"].astype(int)
    elegible = (df["n_previos"] >= MIN_PARTIDOS_PREVIOS) & (df["min_l10"] >= MIN_MINUTOS_L10)
    df = df[elegible].sort_values(["fecha_utc", "evento", "athlete_id"]).reset_index(drop=True)
    df["semana"] = df["fecha"].dt.to_period("W").astype(str)
    return df
