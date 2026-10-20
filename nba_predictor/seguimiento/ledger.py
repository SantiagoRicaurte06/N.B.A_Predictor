# ================================================
#  NBA PREDICTOR — MÓDULO 8: TRACKING
#  Responsabilidad:
#    - Ledger append-only de picks (cache/ledger.csv)
#    - Contabilidad DERIVADA: el bankroll se calcula
#      sumando el PnL del ledger, nunca se almacena
#      como número mutable (ADR-007).
#    - Métricas: win rate, ROI, calibración por edge.
#  Ref: TRD §4.4, ADR-007
# ================================================

import pandas as pd
from pathlib import Path
from datetime import datetime

LEDGER_FILE = Path("cache/ledger.csv")

# Esquema del ledger (TRD §4.4). Orden estable de columnas.
COLUMNS = [
    "id", "fecha", "jugador", "target", "lado", "linea", "odds",
    "pred_media", "pred_sigma", "prob_modelo", "edge_pct", "stake",
    "modo", "resultado", "pnl",
    # Identificador de ESPN del jugador: permite resolver el pick solo con
    # el box score del día siguiente. Los ledgers anteriores no lo tienen.
    "athlete_id",
]

RESULTADOS_VALIDOS = {"W", "L", "VOID"}
MODOS_VALIDOS = {"PAPEL", "REAL"}

# Break-even de referencia a cuota típica de props (1.87). Un win rate por
# debajo de esto = sistema perdedor, sin importar cuántos aciertos.
BREAK_EVEN_PCT = round(1 / 1.87 * 100, 1)   # ≈ 53.5

# GATE papel → dinero real (PLAN Fase 3, ADR-003). Umbrales calibrados con el
# backtest: el pooled quedó ~break-even, así que para arriesgar dinero real hay
# que DEMOSTRAR ventaja real en papel — muestra suficiente, win rate por encima
# del break-even y ROI positivo.
GATE_PAPEL = {
    # Suelo de muestra. El criterio que manda es el intervalo de confianza de
    # abajo; este número solo evita que se evalúe con cuatro datos.
    "min_picks":    300,
    "min_win_rate": 54.0,    # por encima del break-even (~53.5)
    "min_roi":      0.0,     # ROI positivo
    # El criterio REAL: el límite inferior del IC al 95 % debe superar el
    # break-even. Es lo que distingue "voy ganando" de "voy ganando de verdad".
    "confianza":    0.95,
}

# POR QUÉ NO BASTA CON min_picks Y min_win_rate
# ---------------------------------------------
# La versión anterior pedía 100 picks con 54 % de acierto. Con esa muestra el
# intervalo de confianza al 95 % es [44.2 %, 63.8 %]: el break-even de 53.5 %
# cae justo en el medio. Se podía cruzar el gate —y empezar a apostar dinero
# real— estando en realidad en el 45 %.
#
# Cuánta muestra hace falta de verdad, para que el límite inferior supere el
# break-even:
#     acierto observado 58 %  ->  ~460 picks
#     acierto observado 56 %  -> ~1 500 picks
#     acierto observado 54 %  ->  no alcanza nunca de forma razonable
#
# Por eso el gate ya no compara contra un número fijo: calcula el intervalo y
# exige que su suelo esté por encima del break-even. Así se ajusta solo — con
# más ventaja, menos muestra necesaria.


def _limite_inferior_wilson(exitos: int, n: int, z: float = 1.96) -> float:
    """
    Límite inferior del intervalo de Wilson, en porcentaje.

    Se usa Wilson y no la aproximación normal porque con muestras pequeñas o
    proporciones lejos de 0.5 la normal da intervalos demasiado optimistas —
    justo el error que este gate existe para evitar.
    """
    if n <= 0:
        return 0.0
    p = exitos / n
    denom = 1 + z**2 / n
    centro = p + z**2 / (2 * n)
    margen = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    return max(0.0, (centro - margen) / denom) * 100


# ─────────────────────────────────────────────
# 1. LECTURA / ESCRITURA DEL LEDGER
# ─────────────────────────────────────────────

def _cargar_ledger() -> pd.DataFrame:
    """Carga el ledger completo. Si no existe, devuelve uno vacío con el esquema."""
    if LEDGER_FILE.exists():
        df = pd.read_csv(LEDGER_FILE, dtype={"athlete_id": str})
        # Garantizar todas las columnas del esquema (tolerante a versiones)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)


def _guardar_ledger(df: pd.DataFrame):
    """Persiste el ledger. Crea cache/ si no existe."""
    LEDGER_FILE.parent.mkdir(exist_ok=True)
    df[COLUMNS].to_csv(LEDGER_FILE, index=False)


def _siguiente_id(df: pd.DataFrame) -> int:
    """ID incremental. 1 si el ledger está vacío."""
    if df.empty or df["id"].isna().all():
        return 1
    return int(pd.to_numeric(df["id"], errors="coerce").max()) + 1


# ─────────────────────────────────────────────
# 2. REGISTRO DE PICKS
# ─────────────────────────────────────────────

def registrar_pick(pick: dict, modo: str = "PAPEL") -> int:
    """
    Registra un pick nuevo en el ledger con resultado pendiente (null).
    `pick` debe traer al menos: jugador, target, lado, linea, odds, stake.
    Campos opcionales del modelo: pred_media, pred_sigma, prob_modelo, edge_pct.
    Retorna el id asignado.
    """
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"modo inválido: {modo}. Usa uno de {MODOS_VALIDOS}")

    df = _cargar_ledger()
    nuevo_id = _siguiente_id(df)

    fila_dict = {
        "id":          nuevo_id,
        "fecha":       pick.get("fecha", datetime.now().isoformat()),
        "jugador":     pick.get("jugador", ""),
        "target":      pick.get("target", "PTS"),
        "lado":        pick.get("lado", ""),
        "linea":       pick.get("linea"),
        "odds":        pick.get("odds"),
        "pred_media":  pick.get("pred_media"),
        "pred_sigma":  pick.get("pred_sigma"),
        "prob_modelo": pick.get("prob_modelo"),
        "edge_pct":    pick.get("edge_pct"),
        "stake":       pick.get("stake"),
        "modo":        modo,
        "resultado":   pd.NA,   # pendiente
        "pnl":         pd.NA,   # se calcula al registrar el resultado
        "athlete_id":  pick.get("athlete_id"),
    }

    fila = pd.DataFrame([fila_dict], columns=COLUMNS)
    # Evita el FutureWarning de concat sobre un ledger vacío.
    df = fila if df.empty else pd.concat([df, fila], ignore_index=True)
    _guardar_ledger(df)
    return nuevo_id


# ─────────────────────────────────────────────
# 3. REGISTRO DE RESULTADOS Y CÁLCULO DE PnL
# ─────────────────────────────────────────────

def _calcular_pnl(resultado: str, stake: float, odds: float) -> float:
    """
    PnL de una apuesta ya resuelta.
      W    → ganancia neta = stake * (odds - 1)
      L    → -stake
      VOID → 0 (se devuelve el stake, no afecta el bankroll)
    """
    if resultado == "W":
        return round(stake * (odds - 1), 2)
    if resultado == "L":
        return round(-stake, 2)
    if resultado == "VOID":
        return 0.0
    raise ValueError(f"resultado inválido: {resultado}")


def registrar_resultado(pick_id: int, resultado: str) -> float:
    """
    Marca el resultado de un pick y calcula su PnL.
    resultado ∈ {W, L, VOID}. Retorna el PnL calculado.
    """
    if resultado not in RESULTADOS_VALIDOS:
        raise ValueError(f"resultado inválido: {resultado}. Usa {RESULTADOS_VALIDOS}")

    df = _cargar_ledger()
    mask = pd.to_numeric(df["id"], errors="coerce") == pick_id
    if not mask.any():
        raise KeyError(f"No existe pick con id {pick_id}")

    idx = df.index[mask][0]
    stake = float(df.at[idx, "stake"])
    odds  = float(df.at[idx, "odds"])
    pnl   = _calcular_pnl(resultado, stake, odds)

    # 'resultado' puede leerse como float64 (todo NaN) desde CSV; forzar object
    # antes de asignar un string evita el FutureWarning de dtype incompatible.
    df["resultado"] = df["resultado"].astype(object)
    df.at[idx, "resultado"] = resultado
    df.at[idx, "pnl"]       = pnl
    _guardar_ledger(df)
    return pnl


# ─────────────────────────────────────────────
# 4. BANKROLL DERIVADO (ADR-007)
# ─────────────────────────────────────────────

def bankroll_actual(bankroll_inicial: float = 300.0, modo: str = "PAPEL") -> float:
    """
    Bankroll = inicial + suma del PnL de todos los picks RESUELTOS del modo.
    Nunca se almacena; siempre se deriva del ledger. Reproducible por diseño.
    """
    df = _cargar_ledger()
    if df.empty:
        return round(bankroll_inicial, 2)

    resueltos = df[(df["modo"] == modo) & df["pnl"].notna()]
    total_pnl = pd.to_numeric(resueltos["pnl"], errors="coerce").fillna(0).sum()
    return round(bankroll_inicial + total_pnl, 2)


# ─────────────────────────────────────────────
# 5. MÉTRICAS
# ─────────────────────────────────────────────

def metricas(modo: str = "PAPEL") -> dict:
    """
    Métricas sobre los picks resueltos (excluye VOID del win rate y ROI).
    Incluye desglose de win rate por bucket de edge (calibración).
    """
    df = _cargar_ledger()
    df = df[df["modo"] == modo]

    # Resueltos y no anulados
    jugados = df[df["resultado"].isin(["W", "L"])].copy()
    anuladas = int((df["resultado"] == "VOID").sum())
    pendientes = int(df["resultado"].isna().sum())

    if jugados.empty:
        return {
            "modo": modo, "total_resueltos": 0, "pendientes": pendientes,
            "anuladas": anuladas, "mensaje": "Sin picks resueltos aún",
        }

    jugados["stake"] = pd.to_numeric(jugados["stake"], errors="coerce")
    jugados["pnl"]   = pd.to_numeric(jugados["pnl"], errors="coerce")
    jugados["edge_pct"] = pd.to_numeric(jugados["edge_pct"], errors="coerce")

    n        = len(jugados)
    ganadas  = int((jugados["resultado"] == "W").sum())
    apostado = jugados["stake"].sum()
    pnl_tot  = jugados["pnl"].sum()

    resultado = {
        "modo":            modo,
        "total_resueltos": n,
        "ganadas":         ganadas,
        "perdidas":        n - ganadas,
        "anuladas":        anuladas,
        "pendientes":      pendientes,
        "win_rate":        round(ganadas / n * 100, 1),
        "apostado_total":  round(float(apostado), 2),
        "pnl_total":       round(float(pnl_tot), 2),
        "roi_pct":         round(float(pnl_tot / apostado * 100), 2) if apostado > 0 else 0.0,
    }

    # Calibración: win rate por bucket de edge (¿el edge alto gana más?)
    calibracion = {}
    edges = jugados.dropna(subset=["edge_pct"])
    if len(edges) >= 6:
        try:
            edges = edges.copy()
            edges["bucket"] = pd.qcut(edges["edge_pct"], q=3,
                                      labels=["bajo", "medio", "alto"],
                                      duplicates="drop")
            for bucket, grupo in edges.groupby("bucket", observed=True):
                calibracion[str(bucket)] = {
                    "n":        len(grupo),
                    "win_rate": round((grupo["resultado"] == "W").mean() * 100, 1),
                    "edge_medio": round(grupo["edge_pct"].mean(), 1),
                }
        except Exception:
            pass
    resultado["calibracion_por_edge"] = calibracion

    return resultado


# ─────────────────────────────────────────────
# 6. GATE papel → real
# ─────────────────────────────────────────────

def estado_gate(modo: str = "PAPEL", gate: dict | None = None) -> dict:
    """
    Progreso hacia la graduación de papel a dinero real. Evalúa los tres
    criterios del GATE contra las métricas actuales del ledger.
    """
    gate = gate or GATE_PAPEL
    m = metricas(modo)
    n   = m.get("total_resueltos", 0)
    wr  = m.get("win_rate", 0.0)
    roi = m.get("roi_pct", 0.0)

    # Suelo del intervalo de confianza: la ventaja tiene que ser distinguible
    # del azar, no solo estar por encima en el promedio observado.
    exitos = int(round(n * wr / 100.0))
    ic_bajo = _limite_inferior_wilson(exitos, n)

    criterios = {
        "picks":    {"actual": n,  "meta": gate["min_picks"],    "ok": n  >= gate["min_picks"]},
        "win_rate": {"actual": wr, "meta": gate["min_win_rate"], "ok": wr >= gate["min_win_rate"]},
        "roi":      {"actual": roi,"meta": gate["min_roi"],      "ok": roi >= gate["min_roi"]},
        "ic_supera_break_even": {
            "actual": round(ic_bajo, 1),
            "meta":   BREAK_EVEN_PCT,
            "ok":     ic_bajo > BREAK_EVEN_PCT,
        },
    }
    return {
        "criterios": criterios,
        "aprobado": all(c["ok"] for c in criterios.values()),
        "break_even_pct": BREAK_EVEN_PCT,
        "ic_inferior_pct": round(ic_bajo, 1),
        "progreso_picks": round(min(n / gate["min_picks"], 1.0), 3) if gate["min_picks"] else 0.0,
    }


if __name__ == "__main__":
    print("Módulo 8 — Tracking (contabilidad derivada del ledger)")
    print(f"Ledger: {LEDGER_FILE}")
    print(f"Bankroll PAPEL: ${bankroll_actual():.2f}")
    print(f"Métricas: {metricas()}")
