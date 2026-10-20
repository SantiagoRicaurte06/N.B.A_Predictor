# ================================================
#  TEST — MÓDULO 8: TRACKING
#  Verifica que la contabilidad derivada sea exacta:
#  resultados conocidos → PnL y bankroll exactos.
#  Usa un ledger temporal aislado (no toca cache real).
# ================================================

import sys
import pandas as pd
from pathlib import Path

import nba_predictor.seguimiento.ledger as trk

FALLOS = 0

def check(nombre, condicion, detalle=""):
    global FALLOS
    if condicion:
        print(f"  OK  {nombre}")
    else:
        FALLOS += 1
        print(f"  FALLO  {nombre}  {detalle}")


# ── Aislar el ledger en un archivo temporal ──
LEDGER_TEST = Path("cache/_ledger_test.csv")
trk.LEDGER_FILE = LEDGER_TEST
if LEDGER_TEST.exists():
    LEDGER_TEST.unlink()

print("=" * 55)
print("  TEST MÓDULO 8 — Tracking / contabilidad derivada")
print("=" * 55)

# ── 1. Ledger vacío → bankroll = inicial ──
check("bankroll vacío = inicial",
      trk.bankroll_actual(300.0) == 300.0,
      f"got {trk.bankroll_actual(300.0)}")

# ── 2. Registrar picks ──
id1 = trk.registrar_pick({"jugador": "A", "target": "PTS", "lado": "OVER",
                          "linea": 25.5, "odds": 2.0, "stake": 10.0,
                          "edge_pct": 6.0}, modo="PAPEL")
id2 = trk.registrar_pick({"jugador": "B", "target": "PTS", "lado": "UNDER",
                          "linea": 20.5, "odds": 1.90, "stake": 20.0,
                          "edge_pct": 9.0}, modo="PAPEL")
id3 = trk.registrar_pick({"jugador": "C", "target": "PTS", "lado": "OVER",
                          "linea": 30.5, "odds": 1.80, "stake": 15.0,
                          "edge_pct": 12.0}, modo="PAPEL")
check("ids incrementales 1,2,3", (id1, id2, id3) == (1, 2, 3),
      f"got {(id1, id2, id3)}")

# ── 3. Picks pendientes no mueven el bankroll ──
check("pendientes no afectan bankroll",
      trk.bankroll_actual(300.0) == 300.0,
      f"got {trk.bankroll_actual(300.0)}")

# ── 4. PnL exacto por resultado ──
pnl1 = trk.registrar_resultado(id1, "W")   # 10 * (2.0-1) = +10.0
pnl2 = trk.registrar_resultado(id2, "L")   # -20.0
pnl3 = trk.registrar_resultado(id3, "VOID")# 0.0
check("PnL W = +10.0", pnl1 == 10.0, f"got {pnl1}")
check("PnL L = -20.0", pnl2 == -20.0, f"got {pnl2}")
check("PnL VOID = 0.0", pnl3 == 0.0, f"got {pnl3}")

# ── 5. Bankroll derivado exacto ──
# 300 + 10 - 20 + 0 = 290
check("bankroll derivado = 290.0",
      trk.bankroll_actual(300.0) == 290.0,
      f"got {trk.bankroll_actual(300.0)}")

# ── 6. Reproducibilidad: recargar desde disco da lo mismo ──
check("bankroll reproducible tras recarga",
      trk.bankroll_actual(300.0) == 290.0,
      f"got {trk.bankroll_actual(300.0)}")

# ── 7. Métricas: VOID excluido del win rate ──
m = trk.metricas("PAPEL")
check("total_resueltos = 2 (VOID excluido)",
      m["total_resueltos"] == 2, f"got {m.get('total_resueltos')}")
check("win_rate = 50.0", m["win_rate"] == 50.0, f"got {m.get('win_rate')}")
check("anuladas = 1", m["anuladas"] == 1, f"got {m.get('anuladas')}")
# ROI = pnl(-10) / apostado(30) * 100 = -33.33
check("roi_pct = -33.33", m["roi_pct"] == -33.33, f"got {m.get('roi_pct')}")

# ── 8. Errores controlados ──
try:
    trk.registrar_resultado(999, "W")
    check("id inexistente lanza KeyError", False)
except KeyError:
    check("id inexistente lanza KeyError", True)

try:
    trk.registrar_resultado(id1, "XYZ")
    check("resultado inválido lanza ValueError", False)
except ValueError:
    check("resultado inválido lanza ValueError", True)

# ── 9. Gate papel → real ──
g = trk.estado_gate("PAPEL")
# Con solo 2 picks resueltos (50% WR, ROI -33%), el gate NO debe aprobar.
check("gate no aprueba con muestra chica", g["aprobado"] is False)
check("gate criterio picks no cumplido (2 < min_picks)",
      g["criterios"]["picks"]["ok"] is False, f"got {g['criterios']['picks']}")
check("gate reporta break-even ~53.5",
      abs(g["break_even_pct"] - 53.5) < 0.2, f"got {g['break_even_pct']}")


# ── El agujero que tenía el gate: pasarse por suerte ──
# Con 100 picks al 54 % el IC95 va de 44 % a 64 %: el break-even queda dentro,
# así que ese resultado NO distingue un sistema con ventaja de uno sin ella.
check("IC95: 100 picks al 54% no supera break-even",
      trk._limite_inferior_wilson(54, 100) <= trk.BREAK_EVEN_PCT)
# 600 y no 470: a 470 el intervalo cae justo en el borde (53.36 vs 53.5) y el
# test dependería del redondeo, no de la lógica.
check("IC95: 600 picks al 58% sí lo supera",
      trk._limite_inferior_wilson(348, 600) > trk.BREAK_EVEN_PCT)
check("IC95: más muestra estrecha el intervalo",
      trk._limite_inferior_wilson(580, 1000) > trk._limite_inferior_wilson(58, 100))
check("IC de Wilson nunca es negativo",
      trk._limite_inferior_wilson(0, 10) >= 0.0)
check("gate incluye el criterio de intervalo",
      "ic_supera_break_even" in trk.estado_gate("PAPEL")["criterios"])
# ── Limpieza ──
if LEDGER_TEST.exists():
    LEDGER_TEST.unlink()

print("-" * 55)
if FALLOS == 0:
    print("  TODOS LOS TESTS APROBADOS")
    sys.exit(0)
else:
    print(f"  {FALLOS} TEST(S) FALLIDO(S)")
    sys.exit(1)
