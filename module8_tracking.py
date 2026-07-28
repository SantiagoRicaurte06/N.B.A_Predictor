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
]

RESULTADOS_VALIDOS = {"W", "L", "VOID"}
MODOS_VALIDOS = {"PAPEL", "REAL"}


# ─────────────────────────────────────────────
# 1. LECTURA / ESCRITURA DEL LEDGER
# ─────────────────────────────────────────────

def _cargar_ledger() -> pd.DataFrame:
    """Carga el ledger completo. Si no existe, devuelve uno vacío con el esquema."""
    if LEDGER_FILE.exists():
        df = pd.read_csv(LEDGER_FILE)
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


if __name__ == "__main__":
    print("Módulo 8 — Tracking (contabilidad derivada del ledger)")
    print(f"Ledger: {LEDGER_FILE}")
    print(f"Bankroll PAPEL: ${bankroll_actual():.2f}")
    print(f"Métricas: {metricas()}")
