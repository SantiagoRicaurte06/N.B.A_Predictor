# ================================================
#  NBA PREDICTOR — DESCARGA HISTÓRICA
#  Baja a cache los gamelogs de jugadores elegibles
#  (≥15 min, ≥15 GP) para las temporadas del backtest.
#  Corre UNA vez; el backtest (module7) trabaja sobre
#  el cache en disco, sin volver a golpear la API.
#
#  Reanudable: si el gamelog ya está en cache, lo salta.
#  Uso:
#     python descargar_historico.py            # todas las temporadas
#     python descargar_historico.py --limit 5  # prueba rápida (5 jugadores/temporada)
#  Ref: TRD §7, PLAN Fase 1.1
# ================================================

import sys
import time
from pathlib import Path

import pandas as pd

from module1_data_engine import (
    get_stats_liga,
    filtrar_jugadores_elegibles,
    get_player_gamelog,
    CACHE_DIR,
)

# Temporadas del backtest (actual + anterior, PLAN §Decisiones)
SEASONS = ["2024-25", "2025-26"]


def _parse_limit(argv) -> int | None:
    """--limit N para pruebas rápidas; sin él, descarga todo."""
    if "--limit" in argv:
        try:
            return int(argv[argv.index("--limit") + 1])
        except (IndexError, ValueError):
            print("  ⚠️  --limit necesita un número; ignorando.")
    return None


def descargar_temporada(season: str, limit: int | None = None) -> dict:
    """Descarga (o reanuda) los gamelogs de los elegibles de una temporada."""
    print("\n" + "=" * 55)
    print(f"  📥 TEMPORADA {season}")
    print("=" * 55)

    stats = get_stats_liga(season)
    if stats is None:
        print(f"  ❌ No se pudieron obtener stats de liga para {season}")
        return {"season": season, "ok": False}

    elegibles = filtrar_jugadores_elegibles(stats)
    ids = elegibles["PLAYER_ID"].astype(int).tolist()
    nombres = elegibles["PLAYER_NAME"].tolist() if "PLAYER_NAME" in elegibles else [""] * len(ids)

    if limit is not None:
        ids, nombres = ids[:limit], nombres[:limit]

    total = len(ids)
    descargados = saltados = fallidos = 0
    print(f"  → {total} jugadores elegibles a procesar\n")

    for i, (pid, nombre) in enumerate(zip(ids, nombres), 1):
        cache_path = CACHE_DIR / f"gamelog_{pid}_{season}.csv"

        # Reanudable: si ya existe, saltar (no re-descargar histórico).
        if cache_path.exists():
            saltados += 1
            continue

        try:
            gl = get_player_gamelog(pid, season)  # descarga + cachea
            if gl is not None and not gl.empty:
                descargados += 1
                print(f"    [{i:>3}/{total}] ✅ {nombre[:26]:<26} ({len(gl)} juegos)")
            else:
                fallidos += 1
                print(f"    [{i:>3}/{total}] ⚠️  {nombre[:26]:<26} sin datos")
        except KeyboardInterrupt:
            print("\n  ⏸️  Interrumpido — el progreso queda en cache, reanudable.")
            raise
        except Exception as e:
            fallidos += 1
            print(f"    [{i:>3}/{total}] ❌ {nombre[:26]:<26} error: {e}")

    print(f"\n  📊 {season}: {descargados} nuevos · {saltados} en cache · {fallidos} sin datos")
    return {
        "season": season, "ok": True, "total": total,
        "descargados": descargados, "saltados": saltados, "fallidos": fallidos,
    }


def main():
    limit = _parse_limit(sys.argv)
    inicio = time.time()

    print("=" * 55)
    print("  DESCARGA HISTÓRICA PARA BACKTEST")
    print(f"  Temporadas: {', '.join(SEASONS)}")
    if limit:
        print(f"  Modo prueba: máx {limit} jugadores por temporada")
    print("=" * 55)

    resumen = []
    try:
        for season in SEASONS:
            resumen.append(descargar_temporada(season, limit))
    except KeyboardInterrupt:
        print("\n  Detenido por el usuario. Vuelve a correr para reanudar.")
        return

    mins = (time.time() - inicio) / 60
    print("\n" + "=" * 55)
    print("  ✅ DESCARGA COMPLETA")
    for r in resumen:
        if r.get("ok"):
            print(f"    {r['season']}: {r['descargados']} nuevos, "
                  f"{r['saltados']} en cache, {r['fallidos']} sin datos")
    print(f"  ⏱️  {mins:.1f} min")
    print("=" * 55)


if __name__ == "__main__":
    main()
