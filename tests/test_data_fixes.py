# ================================================
#  TEST — Arreglos de datos en module1 (DATA_SPEC §7)
#  DNP filter, normalización de equipos, matching de lesiones.
# ================================================

import sys

# La consola de Windows es cp1252 y revienta con las flechas de los
# mensajes; el UnicodeEncodeError enmascaraba el resultado del test.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

import nba_predictor.datos.fuente_nba as m1

FALLOS = 0

def check(nombre, cond, detalle=""):
    global FALLOS
    if cond:
        print(f"  OK  {nombre}")
    else:
        FALLOS += 1
        print(f"  FALLO  {nombre}  {detalle}")


print("=" * 55)
print("  TEST — Arreglos de datos module1 (DATA_SPEC §7)")
print("=" * 55)

# ── §7.2  normalizar_team ──
check("NBA 'NOP' y ESPN 'NO' → misma canónica",
      m1.normalizar_team('NOP') == m1.normalizar_team('NO'),
      f"{m1.normalizar_team('NOP')} vs {m1.normalizar_team('NO')}")
check("'GS' → 'GSW' canónico",
      m1.normalizar_team('GS') == m1.normalizar_team('GSW'))
check("'phx' minúscula normaliza",
      m1.normalizar_team('phx') == m1.normalizar_team('PHO'))
check("equipo desconocido pasa igual (upper)",
      m1.normalizar_team('lal') == 'LAL')

# jugador_juega_hoy con variantes cruzadas
check("jugador_juega_hoy cruza NBA↔ESPN (NOP vs {NO})",
      m1.jugador_juega_hoy('NOP', {'NO', 'LAL'}) is True)
check("jugador_juega_hoy False si no está",
      m1.jugador_juega_hoy('BOS', {'NO', 'LAL'}) is False)
check("sin schedule → no filtra (True)",
      m1.jugador_juega_hoy('BOS', set()) is True)

# ── §7.1  filtro DNP ──
df = pd.DataFrame({'MIN': ['30:00', '0:00', '', '25:00'], 'PTS': [20, 0, 0, 15]})
df = m1._asegurar_min_num(df)
df_filtrado = m1._filtrar_dnp(df)
check("DNP: quedan 2 filas con minutos > 0",
      len(df_filtrado) == 2, f"got {len(df_filtrado)}")
check("DNP: no queda ningún MIN_num == 0",
      (df_filtrado['MIN_num'] > 0).all())

# ── §7.3  matching de lesiones ──
injury = pd.DataFrame({
    'player_name': ['LeBron James', 'Anthony Davis', 'Jaylen Brown'],
    'status':      ['Out', 'Available', 'GTD'],
    'reason':      ['ankle', '', 'knee'],
})
# Nombre completo exacto → detecta Out
disp, estado = m1.is_player_available('LeBron James', injury)
check("lesión: nombre completo detecta 'Out'", disp is False, f"got {disp}, {estado}")

# Jugador no lesionado → disponible
disp2, _ = m1.is_player_available('Stephen Curry', injury)
check("lesión: jugador ausente del reporte → disponible", disp2 is True)

# Ambigüedad por apellido (dos 'Brown')
injury_amb = pd.DataFrame({
    'player_name': ['Jaylen Brown', 'Kobe Brown'],
    'status':      ['Out', 'Available'],
    'reason':      ['knee', ''],
})
# Nombre completo exacto debe ganar sobre el fallback ambiguo
disp3, _ = m1.is_player_available('Kobe Brown', injury_amb)
check("lesión: nombre completo evita ambigüedad de apellido", disp3 is True, f"got {disp3}")

print("-" * 55)
if FALLOS == 0:
    print("  TODOS LOS TESTS APROBADOS")
    sys.exit(0)
else:
    print(f"  {FALLOS} TEST(S) FALLIDO(S)")
    sys.exit(1)
