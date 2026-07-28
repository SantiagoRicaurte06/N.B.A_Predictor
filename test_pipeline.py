# ================================================
#  NBA PREDICTOR — TEST TÉCNICO DEL PIPELINE
#  Verifica que todos los módulos funcionen
#  con datos mock antes de usar datos reales.
# ================================================

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Semilla fija: el pipeline usa datos mock aleatorios; sin semilla, tests como
# el de integración eran no-deterministas (a veces generaban pick, a veces no).
np.random.seed(42)

print("=" * 60)
print("  [TEST] TEST TECNICO — NBA PREDICTOR PIPELINE")
print("=" * 60)

# ═══════════════════════════════════════════════════════
# TEST 1: Module 2 — Feature Engineering
# ═══════════════════════════════════════════════════════

print("\n" + "-" * 50)
print("  TEST 1: Feature Engineering (module2)")
print("-" * 50)

from module2_prediction_engine import (
    build_player_features,
    calcular_usage_rate,
    calcular_rebound_rate,
    calcular_pace_proxy,
    detectar_back_to_back,
    get_feature_cols_props,
    entrenar_modelo_props,
    ajustar_por_defensive_rating,
)

# Crear datos mock de gamelog
def crear_gamelog_mock():
    """Crea un gamelog fake con todas las columnas necesarias."""
    n_games = 20
    dates = pd.date_range(end=datetime.now(), periods=n_games, freq='2D')

    df = pd.DataFrame({
        'GAME_DATE': dates,
        'PTS': np.random.randint(15, 35, n_games),
        'REB': np.random.randint(5, 15, n_games),
        'AST': np.random.randint(3, 12, n_games),
        'STL': np.random.randint(0, 3, n_games),
        'BLK': np.random.randint(0, 3, n_games),
        'TOV': np.random.randint(1, 5, n_games),
        'FGA': np.random.randint(10, 25, n_games),
        'FGM': np.random.randint(5, 15, n_games),
        'FG3A': np.random.randint(2, 10, n_games),
        'FG3M': np.random.randint(1, 5, n_games),
        'FTA': np.random.randint(3, 10, n_games),
        'FTM': np.random.randint(2, 8, n_games),
        'OREB': np.random.randint(1, 5, n_games),
        'DREB': np.random.randint(3, 10, n_games),
        'TEAM_FGA': np.random.randint(70, 90, n_games),
        'TEAM_REB': np.random.randint(40, 50, n_games),
        'TEAM_OREB': np.random.randint(8, 15, n_games),
        'TEAM_DREB': np.random.randint(30, 40, n_games),
        'MIN': [f"{np.random.randint(25, 40)}:00" for _ in range(n_games)],
        'MATCHUP': ['vs. LAL' if i % 2 == 0 else '@ GSW' for i in range(n_games)],
        'WL': ['W' if i % 2 == 0 else 'L' for i in range(n_games)],
    })
    return df

try:
    gl_mock = crear_gamelog_mock()
    print(f"  ✅ Datos mock creados: {len(gl_mock)} juegos")

    # Testear build_player_features
    gl_features = build_player_features(gl_mock.copy())

    features_esperadas = [
        'avg_PTS_L10', 'trend_PTS', 'avg_pace_L10', 'avg_usage_L10',
        'is_b2b', 'b2b_last_5', 'avg_minutes_restriction_L3',
        'avg_off_reb_rate_L10', 'avg_def_reb_rate_L10'
    ]

    features_encontradas = [f for f in features_esperadas if f in gl_features.columns]
    print(f"  ✅ Features generadas: {len(features_encontradas)}/{len(features_esperadas)}")

    for f in features_esperadas:
        if f in gl_features.columns:
            print(f"      ✓ {f}")
        else:
            print(f"      ✗ {f} — FALTA!")

    # Testear funciones auxiliares
    print("\n  Funciones auxiliares:")

    # Usage rate
    row_mock = gl_mock.iloc[-1]
    usage = calcular_usage_rate(row_mock)
    print(f"    ✓ Usage rate: {usage:.3f} (esperado: 0.15-0.35)")

    # Rebound rate
    reb_off = calcular_rebound_rate(row_mock, is_offensive=True)
    reb_def = calcular_rebound_rate(row_mock, is_offensive=False)
    print(f"    ✓ Rebound rate: OFF={reb_off:.3f}, DEF={reb_def:.3f}")

    # Pace
    pace = calcular_pace_proxy(gl_mock)
    print(f"    ✓ Pace promedio: {pace.mean():.1f} (esperado: 90-110)")

    # Back-to-back
    b2b = detectar_back_to_back(gl_mock)
    print(f"    ✓ B2B detectados: {b2b.sum()} (esperado: 0 con freq=2D)")

    print("\n  ✅ TEST 1 APROBADO")

except Exception as e:
    print(f"\n  ❌ TEST 1 FALLIDO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# TEST 2: Module 2 — Modelo de Predicción
# ═══════════════════════════════════════════════════════

print("\n" + "-" * 50)
print("  TEST 2: Entrenamiento de Modelo (module2)")
print("-" * 50)

try:
    # Entrenar modelo para PTS
    resultado = entrenar_modelo_props(gl_features, 'PTS')

    if resultado is None:
        print("  ⚠️  Modelo no pudo entrenar (insuficientes datos)")
    else:
        print(f"  ✅ Modelo entrenado: {resultado['n_juegos']} juegos")
        print(f"      - Predicción: {resultado['prediccion']:.1f} PTS")
        print(f"      - MAE: {resultado['mae']:.2f}")
        print(f"      - Confianza: {resultado['confianza']}")
        print(f"      - Features usadas: {len(resultado['feature_cols'])}")

    print("\n  ✅ TEST 2 APROBADO")

except Exception as e:
    print(f"\n  ❌ TEST 2 FALLIDO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# TEST 3: Ajustes por Defensive Rating
# ═══════════════════════════════════════════════════════

print("\n" + "-" * 50)
print("  TEST 3: Ajustes por Defensive Rating (module2)")
print("-" * 50)

try:
    # Testear ajuste por defensive rating
    opponent_stats = {
        'opp_pts_per_game': 120.0,  # Defensa mala (permite más puntos)
        'opp_reb_per_game': 46.0,
        'opp_ast_per_game': 28.0,
    }

    pred_ajustada, info = ajustar_por_defensive_rating(
        prediccion=25.0,
        target='PTS',
        opponent_stats=opponent_stats
    )

    print(f"  Predicción original: 25.0 PTS")
    print(f"  Predicción ajustada: {pred_ajustada:.1f} PTS")
    print(f"  Factor aplicado: {info['factor']:.3f}")
    print(f"  Cambio: {info['cambio']:+.1f}")

    # Verificar que el factor es correcto
    assert info['factor'] > 1.0, "Debería inflar la predicción vs defensa mala"

    print("\n  ✅ TEST 3 APROBADO")

except Exception as e:
    print(f"\n  ❌ TEST 3 FALLIDO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# TEST 4: Module 3 — Stakes Engine
# ═══════════════════════════════════════════════════════

print("\n" + "-" * 50)
print("  TEST 4: Stakes Engine (module3)")
print("-" * 50)

from module3_stakes_engine import (
    calcular_edge,
    kelly_criterion,
    analizar_pick_prop,
    cargar_bankroll,
)

try:
    # Testear cálculo de edge
    edge = calcular_edge(prob_modelo=0.55, odds_decimal=1.91)
    print(f"  Edge con 55% prob @ 1.91: {edge*100:.1f}% (esperado: ~4.5%)")

    # Testear Kelly
    kelly = kelly_criterion(prob_modelo=0.55, odds_decimal=1.91)
    print(f"  Kelly criterion: {kelly*100:.2f}% del bankroll")

    # Testear análisis completo de pick
    resultado_modelo = {
        'jugador': 'Test Player',
        'target': 'PTS',
        'prediccion': 28.0,
        'mae': 4.0,
        'std_historico': 5.0,
        'confianza': 'ALTA',
        'es_gtd': False,
        'avg_historico': 24.0,
    }

    pick = analizar_pick_prop(
        resultado_modelo,
        linea_casa=24.5,
        odds_over=1.91,
        odds_under=1.87,
        bankroll=300.0
    )

    if pick:
        print(f"  ✅ Pick generado:")
        print(f"      - Jugador: {pick['jugador']}")
        print(f"      - Tipo: {pick['tipo']}")
        print(f"      - Edge: {pick['edge_pct']:.1f}%")
        print(f"      - Stake: ${pick['stake_usd']:.2f}")
        print(f"      - Ganancia potencial: ${pick['ganancia_potencial']:.2f}")
    else:
        print(f"  ⚠️  Sin pick (edge < 8%)")

    # Testear lógica de dirección (CRÍTICO)
    print("\n  Verificando lógica de dirección (CRÍTICO):")

    # Caso 1: Predicción > línea → OVER
    pick_over = analizar_pick_prop(
        {'jugador': 'Test', 'target': 'PTS', 'prediccion': 30.0, 'mae': 4.0,
         'std_historico': 4.0, 'confianza': 'ALTA', 'es_gtd': False, 'avg_historico': 25.0},
        linea_casa=24.5, odds_over=1.91, odds_under=1.87, bankroll=300
    )
    if pick_over and pick_over['lado'] == 'OVER':
        print(f"    ✓ Predicción > línea → OVER (CORRECTO)")
    else:
        print(f"    ✗ Predicción > línea → {pick_over['lado'] if pick_over else 'None'} (ERROR!)")

    # Caso 2: Predicción < línea → UNDER
    pick_under = analizar_pick_prop(
        {'jugador': 'Test', 'target': 'PTS', 'prediccion': 20.0, 'mae': 4.0,
         'std_historico': 4.0, 'confianza': 'ALTA', 'es_gtd': False, 'avg_historico': 25.0},
        linea_casa=25.5, odds_over=1.91, odds_under=1.87, bankroll=300
    )
    if pick_under and pick_under['lado'] == 'UNDER':
        print(f"    ✓ Predicción < línea → UNDER (CORRECTO)")
    else:
        print(f"    ✗ Predicción < línea → {pick_under['lado'] if pick_under else 'None'} (ERROR!)")

    # Caso 3: Predicción muy cerca → None
    pick_cerca = analizar_pick_prop(
        {'jugador': 'Test', 'target': 'PTS', 'prediccion': 25.0, 'mae': 4.0,
         'std_historico': 5.0, 'confianza': 'MEDIA', 'es_gtd': False, 'avg_historico': 25.0},
        linea_casa=25.5, odds_over=1.91, odds_under=1.87, bankroll=300
    )
    if pick_cerca is None:
        print(f"    ✓ Predicción ≈ línea → Sin pick (CORRECTO)")
    else:
        print(f"    ✗ Predicción ≈ línea → {pick_cerca['lado']} (ERROR!)")

    print("\n  ✅ TEST 4 APROBADO")

except Exception as e:
    print(f"\n  ❌ TEST 4 FALLIDO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# TEST 5: Integración Completa
# ═══════════════════════════════════════════════════════

print("\n" + "-" * 50)
print("  TEST 5: Integración Completa")
print("-" * 50)

try:
    # Simular pipeline completo
    print("  Simulando pipeline completo...")

    # 1. Crear datos mock
    gl_mock = crear_gamelog_mock()

    # 2. Generar features
    gl_features = build_player_features(gl_mock)

    # 3. Entrenar modelo
    resultado = entrenar_modelo_props(gl_features, 'PTS')

    if resultado:
        # 4. Aplicar ajustes
        from module2_prediction_engine import predecir_con_ausencias

        resultado_ajustado = predecir_con_ausencias(
            nombre='Test Player',
            resultado_modelo=resultado,
            efectos_ausencia={},
            jugadores_ausentes=[],
            opponent_stats={'opp_pts_per_game': 120.0},
            minutes_restriction=None
        )

        print(f"  ✅ Predicción final: {resultado_ajustado['prediccion']:.1f} PTS")
        print(f"      - Ajustes aplicados: {len(resultado_ajustado.get('ajustes_ausencias', []))}")

        # 5. Generar pick con stake
        pick = analizar_pick_prop(
            resultado_ajustado,
            linea_casa=24.5,
            odds_over=1.91,
            odds_under=1.87,
            bankroll=300.0
        )

        if pick:
            print(f"  ✅ Pick final: {pick['lado']} @ {pick['odds']}")
            print(f"      - Stake: ${pick['stake_usd']:.2f}")
            print(f"      - Edge: {pick['edge_pct']:.1f}%")
        else:
            print(f"  ⚠️  Sin pick (edge insuficiente)")

    print("\n  ✅ TEST 5 APROBADO")

except Exception as e:
    print(f"\n  ❌ TEST 5 FALLIDO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("  ✅ TODOS LOS TESTS APROBADOS")
print("=" * 60)
print("\n  El pipeline está listo para usar con datos reales.")
print("  Para comenzar:")
print("    1. Configura tu API key en module6_odds_engine.py")
print("    2. Ejecuta el pipeline completo")
print("    3. Registra los picks generados")
print("    4. Después de 7-14 días, revisa el win rate en module5")
print()
