# ================================================
#  NBA PREDICTOR — MÓDULO 5: ERROR ANALYSIS ENGINE
#  Responsabilidad:
#    - Leer historial de apuestas con resultados
#    - Identificar patrones de error sistemáticos
#    - Sugerir y aplicar mejoras de features
#    - Generar reporte semanal de rendimiento
# ================================================

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime, timedelta

HISTORIAL_FILE   = Path("cache/historial_apuestas.csv")
PATRONES_FILE    = Path("cache/patrones_error.json")
MEJORAS_FILE     = Path("cache/mejoras_aplicadas.json")
REPORTE_DIR      = Path("cache/reportes")
REPORTE_DIR.mkdir(parents=True, exist_ok=True)

# Mínimo de picks para analizar un patrón con confianza
MIN_MUESTRA = 10

# Mercados suspendidos temporalmente (se actualiza dinámicamente)
MERCADOS_SUSPENDIDOS = ['AST', 'REB']  # Win rate < 35%

# ─────────────────────────────────────────────
# 1. CARGAR Y VALIDAR HISTORIAL
# ─────────────────────────────────────────────

def cargar_historial() -> pd.DataFrame | None:
    """
    Carga el historial de apuestas con resultados registrados.
    Solo analiza picks que ya tienen resultado (W o L).
    """
    if not HISTORIAL_FILE.exists():
        print("  ⚠️  Sin historial de apuestas todavía.")
        return None

    df = pd.read_csv(HISTORIAL_FILE)

    # Solo picks con resultado
    df_resultado = df.dropna(subset=['resultado'])
    df_resultado = df_resultado[
        df_resultado['resultado'].isin(['W', 'L'])
    ].copy()

    if len(df_resultado) < MIN_MUESTRA:
        print(f"  ⚠️  Solo {len(df_resultado)} picks con resultado. "
              f"Necesitas al menos {MIN_MUESTRA} para analizar patrones.")
        return None

    # Columnas útiles
    df_resultado['ganado'] = (df_resultado['resultado'] == 'W').astype(int)
    df_resultado['error_abs'] = abs(
        df_resultado['prediccion_modelo'] - df_resultado['linea']
    )
    df_resultado['timestamp'] = pd.to_datetime(
        df_resultado['timestamp'], errors='coerce'
    )

    print(f"  ✅ {len(df_resultado)} picks con resultado cargados")
    return df_resultado


# ─────────────────────────────────────────────
# 2. ANÁLISIS DE PATRONES DE ERROR
# ─────────────────────────────────────────────

def analizar_por_mercado(df: pd.DataFrame) -> dict:
    """
    ¿En qué mercados falla más el modelo?
    Props PTS vs REB vs AST vs Totales vs Spread.
    """
    resultados = {}
    for mercado, grupo in df.groupby('mercado'):
        if len(grupo) < 3:
            continue
        wr   = grupo['ganado'].mean()
        n    = len(grupo)
        edge = grupo['edge_pct'].mean() if 'edge_pct' in grupo else 0
        resultados[mercado] = {
            'win_rate': round(wr * 100, 1),
            'n_picks':  n,
            'edge_promedio': round(edge, 1),
            'rentable': wr > 0.524  # umbral mínimo con vig estándar
        }
    return resultados


def analizar_por_lado(df: pd.DataFrame) -> dict:
    """
    ¿Falla más en OVER o en UNDER?
    """
    resultados = {}
    if 'lado' not in df.columns:
        return resultados
    for lado, grupo in df.groupby('lado'):
        if len(grupo) < 3:
            continue
        resultados[lado] = {
            'win_rate': round(grupo['ganado'].mean() * 100, 1),
            'n_picks':  len(grupo)
        }
    return resultados


def analizar_por_confianza(df: pd.DataFrame) -> dict:
    """
    ¿Los picks de alta confianza realmente ganan más?
    Valida que la calibración del modelo es correcta.
    """
    resultados = {}
    if 'confianza' not in df.columns:
        return resultados
    for nivel, grupo in df.groupby('confianza'):
        if len(grupo) < 3:
            continue
        resultados[nivel] = {
            'win_rate': round(grupo['ganado'].mean() * 100, 1),
            'n_picks':  len(grupo),
            'calibrado': True  # se llenará abajo
        }

    # Alta confianza debería ganar más que media, que más que baja
    if all(k in resultados for k in ['ALTA', 'MEDIA', 'BAJA']):
        bien_calibrado = (
            resultados['ALTA']['win_rate'] >=
            resultados['MEDIA']['win_rate'] >=
            resultados['BAJA']['win_rate']
        )
        for k in resultados:
            resultados[k]['calibrado'] = bien_calibrado

    return resultados


def analizar_por_edge(df: pd.DataFrame) -> dict:
    """
    ¿Picks con mayor edge realmente ganan más?
    Si no, el modelo está sobreestimando el edge.
    """
    if 'edge_pct' not in df.columns:
        return {}

    # Dividir en terciles de edge
    try:
        df['edge_tercil'] = pd.qcut(
            df['edge_pct'], q=3,
            labels=['bajo', 'medio', 'alto'],
            duplicates='drop'
        )
    except Exception:
        return {}

    resultados = {}
    for tercil, grupo in df.groupby('edge_tercil'):
        if len(grupo) < 3:
            continue
        resultados[str(tercil)] = {
            'win_rate':    round(grupo['ganado'].mean() * 100, 1),
            'edge_medio':  round(grupo['edge_pct'].mean(), 1),
            'n_picks':     len(grupo)
        }

    return resultados


def analizar_por_jugador(df: pd.DataFrame) -> dict:
    """
    ¿Hay jugadores donde el modelo falla sistemáticamente?
    """
    resultados = {}
    for jugador, grupo in df.groupby('jugador'):
        if len(grupo) < 5:
            continue
        wr = grupo['ganado'].mean()
        resultados[jugador] = {
            'win_rate': round(wr * 100, 1),
            'n_picks':  len(grupo),
            'problema': wr < 0.40  # menos del 40% = problema serio
        }
    # Ordenar por win rate ascendente (peores primero)
    return dict(sorted(resultados.items(),
                        key=lambda x: x[1]['win_rate']))


def analizar_error_prediccion(df: pd.DataFrame) -> dict:
    """
    ¿Cuánto se equivoca el modelo en magnitud?
    ¿Tiende a predecir de más o de menos?
    """
    if 'prediccion_modelo' not in df.columns or 'linea' not in df.columns:
        return {}

    diferencias = df['prediccion_modelo'] - df['linea']

    return {
        'sesgo_promedio':    round(diferencias.mean(), 2),
        'error_abs_promedio': round(diferencias.abs().mean(), 2),
        'sobreestima':       diferencias.mean() > 0.5,
        'subestima':         diferencias.mean() < -0.5,
        'descripcion': (
            f"El modelo sobreestima en promedio {diferencias.mean():.1f} puntos"
            if diferencias.mean() > 0 else
            f"El modelo subestima en promedio {abs(diferencias.mean()):.1f} puntos"
        )
    }


def analizar_por_gtd(df: pd.DataFrame) -> dict:
    """
    ¿Los picks GTD (game time decision) son menos confiables?
    """
    if 'es_gtd' not in df.columns:
        return {}

    gtd     = df[df['es_gtd'] == True]
    no_gtd  = df[df['es_gtd'] == False]

    return {
        'gtd': {
            'win_rate': round(gtd['ganado'].mean() * 100, 1) if len(gtd) > 0 else None,
            'n_picks':  len(gtd)
        },
        'no_gtd': {
            'win_rate': round(no_gtd['ganado'].mean() * 100, 1) if len(no_gtd) > 0 else None,
            'n_picks':  len(no_gtd)
        },
        'gtd_es_problema': (
            len(gtd) >= 5 and len(no_gtd) >= 5 and
            gtd['ganado'].mean() < no_gtd['ganado'].mean() - 0.10
        )
    }


def analizar_tendencia_temporal(df: pd.DataFrame) -> dict:
    """
    ¿El modelo mejora con el tiempo o se deteriora?
    Compara win rate de la primera mitad vs segunda mitad del historial.
    """
    if len(df) < MIN_MUESTRA * 2:
        return {}

    df_sorted = df.sort_values('timestamp').copy()
    mitad = len(df_sorted) // 2

    primera = df_sorted.iloc[:mitad]
    segunda = df_sorted.iloc[mitad:]

    wr_primera = primera['ganado'].mean()
    wr_segunda = segunda['ganado'].mean()

    return {
        'win_rate_primera_mitad': round(wr_primera * 100, 1),
        'win_rate_segunda_mitad': round(wr_segunda * 100, 1),
        'mejorando': wr_segunda > wr_primera,
        'delta': round((wr_segunda - wr_primera) * 100, 1)
    }


# ─────────────────────────────────────────────
# 3. IDENTIFICAR PROBLEMAS Y SUGERIR MEJORAS
# ─────────────────────────────────────────────

def identificar_problemas(patrones: dict) -> list[dict]:
    """
    A partir de los patrones detectados, identifica problemas
    concretos y genera recomendaciones de mejora de features.
    """
    problemas = []

    # ── Problema 1: Mercado con bajo win rate
    mercados = patrones.get('por_mercado', {})
    for mercado, stats in mercados.items():
        if not stats['rentable'] and stats['n_picks'] >= MIN_MUESTRA:
            problemas.append({
                'tipo': 'mercado_bajo_rendimiento',
                'descripcion': f"{mercado} tiene win rate de {stats['win_rate']}% con {stats['n_picks']} picks",
                'severidad': 'ALTA' if stats['win_rate'] < 45 else 'MEDIA',
                'accion': f"Desactivar mercado {mercado} o aumentar edge mínimo a 8% para ese mercado",
                'feature_sugerida': None
            })

    # ── Problema 2: Edge no predice resultados
    por_edge = patrones.get('por_edge', {})
    if por_edge:
        wrs = [v['win_rate'] for v in por_edge.values()]
        if max(wrs) - min(wrs) < 3:  # diferencia menor al 3%
            problemas.append({
                'tipo': 'edge_no_calibrado',
                'descripcion': 'Los picks de alto edge no ganan más que los de bajo edge',
                'severidad': 'ALTA',
                'accion': 'Reducir Kelly al 10% hasta recalibrar el modelo',
                'feature_sugerida': 'calibracion_isotonica'
            })

    # ── Problema 3: Modelo sobreestima o subestima
    error = patrones.get('error_prediccion', {})
    if error:
        sesgo = error.get('sesgo_promedio', 0)
        if abs(sesgo) > 2.0:
            direction = "sobreestima" if sesgo > 0 else "subestima"
            problemas.append({
                'tipo': f'sesgo_{direction}',
                'descripcion': error.get('descripcion', ''),
                'severidad': 'MEDIA',
                'accion': f"Agregar corrección de sesgo de {-sesgo:.1f} pts a todas las predicciones",
                'feature_sugerida': 'bias_correction',
                'valor': round(-sesgo, 2)  # corrección a aplicar
            })

    # ── Problema 4: GTD picks son malos
    gtd = patrones.get('por_gtd', {})
    if gtd.get('gtd_es_problema'):
        wr_gtd    = gtd['gtd']['win_rate']
        wr_no_gtd = gtd['no_gtd']['win_rate']
        problemas.append({
            'tipo': 'gtd_poco_confiable',
            'descripcion': f"Picks GTD: {wr_gtd}% vs no-GTD: {wr_no_gtd}%",
            'severidad': 'MEDIA',
            'accion': 'Reducir Kelly al 10% para picks GTD',
            'feature_sugerida': 'gtd_kelly_reduction'
        })

    # ── Problema 5: Jugadores problemáticos
    jugadores = patrones.get('por_jugador', {})
    malos = [j for j, s in jugadores.items() if s.get('problema')]
    if malos:
        for jugador in malos:
            stats = jugadores[jugador]
            problemas.append({
                'tipo': 'jugador_problematico',
                'descripcion': f"{jugador}: {stats['win_rate']}% en {stats['n_picks']} picks",
                'severidad': 'ALTA' if stats['win_rate'] < 35 else 'MEDIA',
                'accion': f"Excluir a {jugador} de predicciones o solo apostar con edge ≥ 10%",
                'feature_sugerida': None,
                'jugador': jugador
            })

    # ── Problema 6: Modelo se deteriora con el tiempo
    tendencia = patrones.get('tendencia_temporal', {})
    if tendencia and not tendencia.get('mejorando', True):
        delta = abs(tendencia.get('delta', 0))
        if delta > 5:
            problemas.append({
                'tipo': 'deterioro_temporal',
                'descripcion': f"Win rate bajó {delta}% en la segunda mitad del historial",
                'severidad': 'ALTA',
                'accion': 'Reducir ventana de datos a 2 meses — el modelo puede estar usando datos demasiado antiguos',
                'feature_sugerida': 'ventana_datos_reducida'
            })

    # ── Problema 7: Confianza mal calibrada
    confianza = patrones.get('por_confianza', {})
    if confianza and not all(v.get('calibrado', True) for v in confianza.values()):
        problemas.append({
            'tipo': 'confianza_mal_calibrada',
            'descripcion': 'Los niveles de confianza no predicen correctamente el resultado',
            'severidad': 'MEDIA',
            'accion': 'Recalcular umbrales de confianza basados en MAE real del historial',
            'feature_sugerida': 'recalibrar_confianza'
        })

    return problemas


# ─────────────────────────────────────────────
# 4. APLICAR MEJORAS AUTOMÁTICAS
# ─────────────────────────────────────────────

def aplicar_mejoras_automaticas(problemas: list[dict]) -> dict:
    """
    Aplica las mejoras que no requieren reentrenar el modelo.
    Las que requieren reentrenamiento se guardan como pendientes.
    """
    mejoras_aplicadas  = []
    mejoras_pendientes = []

    # Cargar mejoras previas
    if MEJORAS_FILE.exists():
        with open(MEJORAS_FILE, 'r') as f:
            historial_mejoras = json.load(f)
    else:
        historial_mejoras = []

    # Mejoras que se pueden aplicar directamente
    mejoras_directas = {
        'bias_correction',
        'gtd_kelly_reduction',
        'gtd_kelly_reduction',
    }

    correcciones = {}

    for problema in problemas:
        feature = problema.get('feature_sugerida')
        tipo    = problema.get('tipo')

        # ── Corrección de sesgo — se aplica directo
        if tipo == 'sesgo_sobreestima' or tipo == 'sesgo_subestima':
            valor = problema.get('valor', 0)
            correcciones['bias_correction'] = valor
            mejoras_aplicadas.append({
                'tipo':        'bias_correction',
                'descripcion': f"Corrección de sesgo: {valor:+.2f} pts a todas las predicciones",
                'fecha':       datetime.now().isoformat()
            })

        # ── GTD Kelly reduction — se aplica directo
        elif tipo == 'gtd_poco_confiable':
            correcciones['gtd_kelly_fraction'] = 0.10
            mejoras_aplicadas.append({
                'tipo':        'gtd_kelly_reduction',
                'descripcion': 'Kelly reducido al 10% para picks GTD',
                'fecha':       datetime.now().isoformat()
            })

        # ── Jugador problemático — excluir de picks
        elif tipo == 'jugador_problematico':
            jugador = problema.get('jugador', '')
            if 'jugadores_excluidos' not in correcciones:
                correcciones['jugadores_excluidos'] = []
            correcciones['jugadores_excluidos'].append(jugador)
            mejoras_aplicadas.append({
                'tipo':        'jugador_excluido',
                'descripcion': f"{jugador} excluido por bajo rendimiento",
                'fecha':       datetime.now().isoformat()
            })

        # ── Mercado con bajo rendimiento
        elif tipo == 'mercado_bajo_rendimiento':
            mercado = problema.get('descripcion', '').split()[0]
            if 'mercados_edge_minimo' not in correcciones:
                correcciones['mercados_edge_minimo'] = {}
            correcciones['mercados_edge_minimo'][mercado] = 8.0
            mejoras_aplicadas.append({
                'tipo':        'edge_minimo_aumentado',
                'descripcion': f"Edge mínimo aumentado a 8% para {mercado}",
                'fecha':       datetime.now().isoformat()
            })

        # ── Mejoras que requieren reentrenamiento
        elif feature in ['calibracion_isotonica', 'recalibrar_confianza',
                          'ventana_datos_reducida']:
            mejoras_pendientes.append({
                'tipo':        feature,
                'descripcion': problema['accion'],
                'severidad':   problema['severidad'],
                'fecha':       datetime.now().isoformat()
            })

    # Guardar correcciones activas
    correcciones['ultima_actualizacion'] = datetime.now().isoformat()

    with open(MEJORAS_FILE, 'w') as f:
        json.dump({
            'correcciones_activas': correcciones,
            'historial': historial_mejoras + mejoras_aplicadas,
            'pendientes': mejoras_pendientes
        }, f, indent=2)

    return {
        'correcciones': correcciones,
        'aplicadas':    mejoras_aplicadas,
        'pendientes':   mejoras_pendientes
    }


def cargar_correcciones_activas() -> dict:
    """
    Carga las correcciones activas para que el módulo 3 las aplique.
    """
    if not MEJORAS_FILE.exists():
        return {}

    try:
        with open(MEJORAS_FILE, 'r') as f:
            contenido = f.read().strip()
            if not contenido:  # archivo vacío
                return {}
            data = json.loads(contenido)
            return data.get('correcciones_activas', {})
    except json.JSONDecodeError:
        # Archivo corrupto — resetear
        MEJORAS_FILE.unlink()
        return {}


# ─────────────────────────────────────────────
# 5. REPORTE SEMANAL
# ─────────────────────────────────────────────

def generar_reporte(patrones: dict, problemas: list[dict],
                     mejoras: dict) -> str:
    """
    Genera un reporte legible con el análisis completo.
    Se guarda en cache/reportes/ con fecha.
    """
    fecha = datetime.now().strftime('%Y-%m-%d')
    lineas = []

    lineas.append("=" * 60)
    lineas.append(f"  📊 REPORTE DE ANÁLISIS DE ERRORES — {fecha}")
    lineas.append("=" * 60)

    # Resumen general
    resumen = patrones.get('resumen', {})
    lineas.append(f"\n  Win Rate global : {resumen.get('win_rate_global', 0)}%")
    lineas.append(f"  ROI global      : {resumen.get('roi_global', 0)}%")
    lineas.append(f"  Total picks     : {resumen.get('total_picks', 0)}")

    # Tendencia
    tendencia = patrones.get('tendencia_temporal', {})
    if tendencia:
        flecha = "📈" if tendencia.get('mejorando') else "📉"
        lineas.append(f"  Tendencia       : {flecha} {tendencia.get('delta', 0):+.1f}% reciente")

    # Por mercado
    lineas.append("\n  ── POR MERCADO ──────────────────────────────")
    for mercado, stats in patrones.get('por_mercado', {}).items():
        emoji = "✅" if stats['rentable'] else "❌"
        lineas.append(f"  {emoji} {mercado:<15} {stats['win_rate']}% ({stats['n_picks']} picks)")

    # Por jugador (top problemáticos)
    lineas.append("\n  ── JUGADORES PROBLEMÁTICOS ──────────────────")
    jugadores = patrones.get('por_jugador', {})
    malos = [(j, s) for j, s in jugadores.items() if s.get('problema')]
    if malos:
        for jugador, stats in malos:
            lineas.append(f"  ⚠️  {jugador:<25} {stats['win_rate']}% ({stats['n_picks']} picks)")
    else:
        lineas.append("  ✅ Sin jugadores problemáticos detectados")

    # Problemas detectados
    lineas.append(f"\n  ── {len(problemas)} PROBLEMAS DETECTADOS ──────────────────")
    for i, p in enumerate(problemas, 1):
        emoji = "🔴" if p['severidad'] == 'ALTA' else "🟡"
        lineas.append(f"  {emoji} {i}. {p['descripcion']}")
        lineas.append(f"      → {p['accion']}")

    # Mejoras aplicadas
    aplicadas = mejoras.get('aplicadas', [])
    lineas.append(f"\n  ── {len(aplicadas)} MEJORAS APLICADAS AUTOMÁTICAMENTE ────")
    if aplicadas:
        for m in aplicadas:
            lineas.append(f"  ✅ {m['descripcion']}")
    else:
        lineas.append("  Sin mejoras automáticas aplicadas")

    # Mejoras pendientes
    pendientes = mejoras.get('pendientes', [])
    if pendientes:
        lineas.append(f"\n  ── {len(pendientes)} MEJORAS PENDIENTES (requieren reentrenamiento) ──")
        for p in pendientes:
            emoji = "🔴" if p['severidad'] == 'ALTA' else "🟡"
            lineas.append(f"  {emoji} {p['descripcion']}")

    lineas.append("\n" + "=" * 60)

    reporte_txt = "\n".join(lineas)

    # Guardar reporte
    ruta = REPORTE_DIR / f"reporte_{fecha}.txt"
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(reporte_txt)

    print(reporte_txt)
    print(f"\n  💾 Reporte guardado en: {ruta}")

    return reporte_txt


# ─────────────────────────────────────────────
# 6. PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def ejecutar_analisis_completo() -> dict:
    """
    Pipeline completo del módulo de análisis de errores.
    1. Carga historial
    2. Detecta patrones
    3. Identifica problemas
    4. Aplica mejoras automáticas
    5. Genera reporte
    """
    print("\n" + "=" * 55)
    print("  🔍 MÓDULO 5: ERROR ANALYSIS ENGINE")
    print("=" * 55)

    # Cargar historial
    print("\n  → Cargando historial de apuestas...")
    df = cargar_historial()
    if df is None:
        return {}

    # Calcular resumen global
    total    = len(df)
    ganadas  = df['ganado'].sum()
    wr_global = round(ganadas / total * 100, 1)
    apostado = df['stake_usd'].sum() if 'stake_usd' in df else 0
    ganado   = df[df['ganado'] == 1]['ganancia_potencial'].sum() if 'ganancia_potencial' in df else 0
    perdido  = df[df['ganado'] == 0]['stake_usd'].sum() if 'stake_usd' in df else 0
    roi      = round((ganado - perdido) / apostado * 100, 1) if apostado > 0 else 0

    print(f"\n  📊 Resumen: {total} picks | {wr_global}% WR | {roi}% ROI")

    # Analizar patrones
    print("\n  → Analizando patrones de error...")
    patrones = {
        'resumen': {
            'total_picks':    total,
            'win_rate_global': wr_global,
            'roi_global':     roi
        },
        'por_mercado':         analizar_por_mercado(df),
        'por_lado':            analizar_por_lado(df),
        'por_confianza':       analizar_por_confianza(df),
        'por_edge':            analizar_por_edge(df),
        'por_jugador':         analizar_por_jugador(df),
        'error_prediccion':    analizar_error_prediccion(df),
        'por_gtd':             analizar_por_gtd(df),
        'tendencia_temporal':  analizar_tendencia_temporal(df),
        'fecha_analisis':      datetime.now().isoformat()
    }

    # Guardar patrones
    with open(PATRONES_FILE, 'w') as f:
        json.dump(patrones, f, indent=2, default=str)

    # Identificar problemas
    print("  → Identificando problemas sistemáticos...")
    problemas = identificar_problemas(patrones)
    print(f"  ⚠️  {len(problemas)} problemas detectados")

    # Aplicar mejoras automáticas
    print("  → Aplicando mejoras automáticas...")
    mejoras = aplicar_mejoras_automaticas(problemas)
    print(f"  ✅ {len(mejoras['aplicadas'])} mejoras aplicadas")
    if mejoras['pendientes']:
        print(f"  🕐 {len(mejoras['pendientes'])} mejoras pendientes de reentrenamiento")

    # Generar reporte
    print("\n  → Generando reporte...")
    reporte = generar_reporte(patrones, problemas, mejoras)

    return {
        'patrones':  patrones,
        'problemas': problemas,
        'mejoras':   mejoras,
        'reporte':   reporte
    }


if __name__ == "__main__":
    resultado = ejecutar_analisis_completo()
