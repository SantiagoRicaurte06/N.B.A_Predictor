# ================================================
#  TEST — MÓDULO 8: TRACKING
#  Verifica que la contabilidad derivada sea exacta:
#  resultados conocidos → PnL y bankroll exactos.
#  Usa un ledger temporal aislado (no toca cache real).
# ================================================

import sys
import pandas as pd
from pathlib import Path

import module8_tracking as trk

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
