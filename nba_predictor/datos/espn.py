"""
Cliente de la API pública de ESPN para la NBA.

Es la única fuente de datos del sistema: calendario, box scores por jugador,
titularidad, ausencias con su motivo, reporte de lesiones y las líneas de
partido de la casa (spread y total).

Todo lo que se descarga queda en `cache/espn/` comprimido. Un partido ya
terminado no cambia, así que se descarga una sola vez.

La API no es oficial: si ESPN cambia el formato, el arreglo vive solo en
este archivo y en `boxscore.py`.
"""

from __future__ import annotations

import gzip
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
CACHE_ESPN = Path("cache") / "espn"

# Tipos de temporada de ESPN: 1 pretemporada, 2 regular, 3 playoffs, 5 play-in.
TIPOS_VALIDOS = {2, 3, 5}

# Del resumen solo se guardan las partes que usa el sistema. El play-by-play
# multiplica por diez el tamaño y no se usa.
CLAVES_RESUMEN = ("boxscore", "header", "injuries", "pickcenter", "gameInfo")

_sesion = requests.Session()
_sesion.headers["User-Agent"] = "Mozilla/5.0 (nba-predictor-pro)"


def _get(url: str, params: dict | None = None, intentos: int = 4) -> dict:
    espera = 2.0
    for intento in range(intentos):
        try:
            r = _sesion.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                raise FileNotFoundError(url)
        except (requests.RequestException, ValueError):
            if intento == intentos - 1:
                raise
        time.sleep(espera)
        espera *= 2
    raise RuntimeError(f"ESPN no respondió tras {intentos} intentos: {url}")


def _leer_gz(ruta: Path):
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        return json.load(f)


def _escribir_gz(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(datos, f, separators=(",", ":"))
    tmp.replace(ruta)


def rango_temporada(temporada: str) -> tuple[date, date]:
    """'2024-25' -> del 1-oct-2024 al 30-jun-2025."""
    anio = int(temporada[:4])
    return date(anio, 10, 1), date(anio + 1, 6, 30)


# ─────────────────────────────────────────────
# Calendario
# ─────────────────────────────────────────────

def partidos_del_dia(dia: date) -> list[dict]:
    """Partidos NBA de un día (regular, play-in y playoffs) con su estado."""
    datos = _get(f"{BASE}/scoreboard", {"dates": dia.strftime("%Y%m%d"), "limit": 100})
    salida = []
    for ev in datos.get("events", []):
        tipo = ev.get("season", {}).get("type")
        if tipo not in TIPOS_VALIDOS:
            continue
        comp = ev["competitions"][0]
        equipos = {c["homeAway"]: c["team"]["abbreviation"] for c in comp["competitors"]}
        salida.append({
            "id": ev["id"],
            "fecha": ev["date"],
            "tipo": tipo,
            "local": equipos.get("home"),
            "visitante": equipos.get("away"),
            "terminado": ev["status"]["type"].get("completed", False),
        })
    return salida


def calendario_temporada(temporada: str, refrescar: bool = False) -> list[dict]:
    """Todos los partidos de una temporada. Se cachea al estar completa."""
    ruta = CACHE_ESPN / temporada / "calendario.json.gz"
    if ruta.exists() and not refrescar:
        return _leer_gz(ruta)

    inicio, fin = rango_temporada(temporada)
    dias = [inicio + timedelta(d) for d in range((fin - inicio).days + 1)]
    partidos = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for lista in ex.map(partidos_del_dia, dias):
            for p in lista:
                partidos[p["id"]] = p
    calendario = sorted(partidos.values(), key=lambda p: p["fecha"])
    if calendario and all(p["terminado"] for p in calendario):
        _escribir_gz(ruta, calendario)
    return calendario


# ─────────────────────────────────────────────
# Resumen de partido (box score + lesiones + líneas)
# ─────────────────────────────────────────────

def ruta_resumen(temporada: str, evento: str) -> Path:
    return CACHE_ESPN / temporada / "partidos" / f"{evento}.json.gz"


def resumen_partido(evento: str, temporada: str | None = None, usar_cache: bool = True) -> dict:
    """Resumen de un partido. Si se da la temporada, se cachea en disco."""
    ruta = ruta_resumen(temporada, evento) if temporada else None
    if ruta and usar_cache and ruta.exists():
        return _leer_gz(ruta)
    datos = _get(f"{BASE}/summary", {"event": evento})
    recorte = {k: datos.get(k) for k in CLAVES_RESUMEN}
    if ruta:
        _escribir_gz(ruta, recorte)
    return recorte


def descargar_temporada(temporada: str, hilos: int = 6, progreso: bool = True) -> int:
    """Descarga los resúmenes de todos los partidos terminados de la temporada.
    Es reanudable: lo que ya está en disco se salta. Devuelve cuántos faltan."""
    calendario = calendario_temporada(temporada)
    pendientes = [p["id"] for p in calendario
                  if p["terminado"] and not ruta_resumen(temporada, p["id"]).exists()]
    if progreso:
        print(f"{temporada}: {len(calendario)} partidos, {len(pendientes)} por descargar")

    fallidos = []
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        futuros = {ex.submit(resumen_partido, ev, temporada): ev for ev in pendientes}
        for n, fut in enumerate(as_completed(futuros), 1):
            try:
                fut.result()
            except Exception:
                fallidos.append(futuros[fut])
            if progreso and n % 250 == 0:
                print(f"  {temporada}: {n}/{len(pendientes)}")
    if progreso:
        print(f"{temporada}: listo ({len(fallidos)} fallidos)")
    return len(fallidos)


# ─────────────────────────────────────────────
# Líneas de partido (spread y total) de las casas
# ─────────────────────────────────────────────

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


def ruta_lineas(temporada: str, evento: str) -> Path:
    return CACHE_ESPN / temporada / "lineas" / f"{evento}.json.gz"


def lineas_partido(evento: str, temporada: str | None = None, usar_cache: bool = True) -> dict:
    """
    Spread y total de cierre del partido, como mediana entre las casas.

    El `pickcenter` del resumen viene vacío en 2023-24 y 2024-25; la API core
    sí guarda el histórico. Se descartan las cuotas en vivo (cambian durante
    el partido) y los modelos que no son casas. El spread va desde el punto de
    vista del local: negativo = el local es favorito.
    """
    ruta = ruta_lineas(temporada, evento) if temporada else None
    if ruta and usar_cache and ruta.exists():
        return _leer_gz(ruta)
    try:
        datos = _get(f"{CORE}/events/{evento}/competitions/{evento}/odds", {"limit": 50})
    except FileNotFoundError:
        datos = {}
    spreads, totales = [], []
    for item in datos.get("items", []):
        casa = (item.get("provider") or {}).get("name", "")
        if "live" in casa.lower() or "accuscore" in casa.lower():
            continue
        if isinstance(item.get("spread"), (int, float)):
            spreads.append(float(item["spread"]))
        if isinstance(item.get("overUnder"), (int, float)):
            totales.append(float(item["overUnder"]))

    def mediana(v):
        v = sorted(v)
        return None if not v else (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)

    lineas = {"spread_local": mediana(spreads), "total": mediana(totales), "n_casas": len(spreads)}
    if ruta:
        _escribir_gz(ruta, lineas)
    return lineas


def descargar_lineas_temporada(temporada: str, hilos: int = 6, progreso: bool = True) -> None:
    calendario = calendario_temporada(temporada)
    pendientes = [p["id"] for p in calendario
                  if p["terminado"] and not ruta_lineas(temporada, p["id"]).exists()]
    if progreso:
        print(f"{temporada}: líneas de {len(pendientes)} partidos por descargar")
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        list(ex.map(lambda ev: _intentar(lineas_partido, ev, temporada), pendientes))
    if progreso:
        print(f"{temporada}: líneas listas")


def _intentar(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def plantilla(equipo: str) -> list[dict]:
    """Plantilla vigente de un equipo (abreviatura de ESPN): refleja traspasos
    y fichajes, cosa que la historia de partidos no sabe al empezar la temporada."""
    datos = _get(f"{BASE}/teams/{equipo.lower()}/roster")
    return [{"athlete_id": str(a["id"]), "jugador": a.get("displayName"),
             "posicion": (a.get("position") or {}).get("abbreviation"),
             "estado": next((i.get("status") for i in a.get("injuries", []) if i.get("status")), "")}
            for a in datos.get("athletes", [])]


def reporte_lesiones() -> list[dict]:
    """Reporte de lesiones vigente de toda la liga."""
    datos = _get(f"{BASE}/injuries")
    salida = []
    for equipo in datos.get("injuries", []):
        nombre_equipo = equipo.get("displayName")
        for les in equipo.get("injuries", []):
            atleta = les.get("athlete", {})
            # El endpoint no trae el id del jugador: va dentro del enlace a su ficha.
            enlaces = " ".join(l.get("href", "") for l in atleta.get("links", []))
            encontrado = re.search(r"/id/(\d+)", enlaces)
            salida.append({
                "equipo": nombre_equipo,
                "jugador": atleta.get("displayName"),
                "athlete_id": encontrado.group(1) if encontrado else "",
                "estado": les.get("status"),
                "detalle": les.get("shortComment") or les.get("longComment", ""),
            })
    return salida


if __name__ == "__main__":
    import sys

    temporadas = sys.argv[1:] or ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    for t in temporadas:
        descargar_temporada(t)
        descargar_lineas_temporada(t)
