# ================================================
#  NBA PREDICTOR — MÓDULO 6: ODDS ENGINE
#  Responsabilidad:
#    - Obtener odds desde The Odds API
#    - Parsear player props (PTS, REB, AST)
#    - Parsear totales del partido
#    - Cache de 1 hora para no gastar requests
# ================================================

import requests
import json
import time
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

ODDS_API_KEY = ""  # El usuario debe completar con su API key
ODDS_CACHE_FILE = Path("cache/odds_cache.json")
CONFIG_FILE = Path("cache/config.json")

# ─────────────────────────────────────────────
# 1. CONFIGURACIÓN — Persistencia de API Key
# ─────────────────────────────────────────────

def cargar_config() -> dict:
    """Carga configuración desde cache/config.json."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def guardar_config(config: dict):
    """Guarda configuración en cache/config.json."""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_api_key() -> str:
    """Obtiene la API key desde config o desde la constante."""
    if ODDS_API_KEY:
        return ODDS_API_KEY
    config = cargar_config()
    return config.get('odds_api_key', '')


def set_api_key(api_key: str):
    """Guarda la API key en config.json."""
    config = cargar_config()
    config['odds_api_key'] = api_key
    config['ultima_actualizacion'] = datetime.now().isoformat()
    guardar_config(config)


# ─────────────────────────────────────────────
# 2. CACHE DE ODDS
# ─────────────────────────────────────────────

def cargar_odds_cache() -> dict | None:
    """Carga odds desde cache si tiene menos de 1 hora."""
    if not ODDS_CACHE_FILE.exists():
        return None

    try:
        with open(ODDS_CACHE_FILE, 'r') as f:
            data = json.load(f)

        edad_horas = (time.time() - data.get('timestamp', 0)) / 3600
        if edad_horas < 1:
            print(f"  📦 Odds desde cache ({edad_horas:.1f}h)")
            return data.get('data')
    except Exception:
        pass

    return None


def guardar_odds_cache(data: dict):
    """Guarda odds en cache con timestamp."""
    ODDS_CACHE_FILE.parent.mkdir(exist_ok=True)
    cache = {
        'timestamp': time.time(),
        'data': data
    }
    with open(ODDS_CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


# ─────────────────────────────────────────────
# 3. OBTENER PARTIDOS DE HOY
# ─────────────────────────────────────────────

def get_partidos_hoy() -> list[dict] | None:
    """
    Obtiene lista de partidos de hoy desde The Odds API.
    Retorna lista de eventos con id, equipos y horario.
    """
    api_key = get_api_key()

    if not api_key:
        print("  ⚠️  API key no configurada")
        return None

    try:
        url = "https://api.the-odds-api.com/v4/sports/basketball_nba/events"
        params = {
            'apiKey': api_key,
            'daysFrom': 0,
            'daysTo': 1
        }

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        eventos = resp.json()
        print(f"  ✅ {len(eventos)} partidos encontrados")
        return eventos

    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Error conectando a Odds API: {e}")
        return None


# ─────────────────────────────────────────────
# 4. OBTENER ODDS DE PARTIDO
# ─────────────────────────────────────────────

def get_odds_partido(event_id: str, debug: bool = False) -> dict | None:
    """
    Obtiene odds de un partido específico incluyendo player props.
    """
    api_key = get_api_key()

    if not api_key:
        return None

    try:
        url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{event_id}/odds"
        params = {
            'apiKey': api_key,
            'regions': 'eu,us',
            'markets': 'player_points,player_rebounds,player_assists,totals',
            'oddsFormat': 'decimal'
        }

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()

        # Debug: mostrar markets disponibles
        if debug:
            bookmakers = data.get('bookmakers', [])
            if bookmakers:
                markets_avail = [m.get('key') for m in bookmakers[0].get('markets', [])]
                if markets_avail:
                    print(f"    [DEBUG] Markets disponibles: {markets_avail}")

        return data

    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Error obteniendo odds: {e}")
        return None


# ─────────────────────────────────────────────
# 5. PARSEAR PLAYER PROPS
# ─────────────────────────────────────────────

def parsear_odds(respuesta: dict) -> dict[str, dict]:
    """
    Transforma la respuesta JSON de The Odds API en dict usable.

    Formato de salida:
    {
        "NombreJugador_PTS": {"linea": 25.5, "odds_over": 1.87, "odds_under": 1.95},
        "NombreJugador_REB": {"linea": 10.5, "odds_over": 1.90, "odds_under": 1.90},
        ...
    }
    """
    if not respuesta or 'bookmakers' not in respuesta:
        return {}

    resultado = {}

    # Buscar el primer bookmaker con markets
    bookmakers = respuesta.get('bookmakers', [])
    if not bookmakers:
        return {}

    # Usar el primer bookmaker (generalmente tiene más mercados)
    bookmaker = bookmakers[0]
    markets = bookmaker.get('markets', [])

    for market in markets:
        market_key = market.get('key', '')
        outcomes = market.get('outcomes', [])

        if len(outcomes) < 2:
            continue

        # Player props
        if market_key == 'player_points':
            for outcome in outcomes:
                name = outcome.get('name', '')
                if not name:
                    continue
                point = outcome.get('point', 0)
                price = outcome.get('price', 1.87)

                key = f"{name}_PTS"
                if key not in resultado:
                    resultado[key] = {'linea': point, 'odds_over': None, 'odds_under': None}

                # Determinar si es over o under por el nombre
                # La API devuelve "Over" y "Under" en el field 'description' o por orden
                if 'Over' in outcome.get('description', '') or outcome.get('description', '').strip() == 'O':
                    resultado[key]['odds_over'] = price if price is not None else 1.87
                else:
                    resultado[key]['odds_under'] = price if price is not None else 1.87

        elif market_key == 'player_rebounds':
            for outcome in outcomes:
                name = outcome.get('name', '')
                if not name:
                    continue
                point = outcome.get('point', 0)
                price = outcome.get('price', 1.87)

                key = f"{name}_REB"
                if key not in resultado:
                    resultado[key] = {'linea': point, 'odds_over': None, 'odds_under': None}

                if 'Over' in outcome.get('description', '') or outcome.get('description', '').strip() == 'O':
                    resultado[key]['odds_over'] = price if price is not None else 1.87
                else:
                    resultado[key]['odds_under'] = price if price is not None else 1.87

        elif market_key == 'player_assists':
            for outcome in outcomes:
                name = outcome.get('name', '')
                if not name:
                    continue
                point = outcome.get('point', 0)
                price = outcome.get('price', 1.87)

                key = f"{name}_AST"
                if key not in resultado:
                    resultado[key] = {'linea': point, 'odds_over': None, 'odds_under': None}

                if 'Over' in outcome.get('description', '') or outcome.get('description', '').strip() == 'O':
                    resultado[key]['odds_over'] = price if price is not None else 1.87
                else:
                    resultado[key]['odds_under'] = price if price is not None else 1.87

    # Limpiar entradas incompletas
    resultado = {k: v for k, v in resultado.items()
                 if v['odds_over'] is not None and v['odds_under'] is not None}

    return resultado


def parsear_odds_totales(respuesta: dict) -> dict | None:
    """
    Parsea el mercado de totales (over/under puntos del partido).

    Retorna:
    {"linea": 225.5, "odds_over": 1.87, "odds_under": 1.95} o None si no hay datos.
    """
    if not respuesta or 'bookmakers' not in respuesta:
        return None

    bookmakers = respuesta.get('bookmakers', [])
    if not bookmakers:
        return None

    bookmaker = bookmakers[0]
    markets = bookmaker.get('markets', [])

    for market in markets:
        if market.get('key') == 'totals':
            outcomes = market.get('outcomes', [])
            if len(outcomes) >= 2:
                over_data = next((o for o in outcomes if 'Over' in o.get('description', '')), None)
                under_data = next((o for o in outcomes if 'Under' in o.get('description', '')), None)

                if over_data and under_data:
                    return {
                        'linea': over_data.get('point', 0),
                        'odds_over': over_data.get('price', 0),
                        'odds_under': under_data.get('price', 0)
                    }

    return None


# ─────────────────────────────────────────────
# 6. FUNCIÓN PRINCIPAL — GET ODDS PROPS
# ─────────────────────────────────────────────

def get_odds_props(debug: bool = True) -> dict[str, dict]:
    """
    Obtiene odds de player props para todos los partidos de hoy.
    Retorna dict combinado con todas las odds disponibles.
    """
    # Verificar API key
    api_key = get_api_key()
    if not api_key:
        print("  ⚠️  API key no configurada. Obtén una gratis en the-odds-api.com")
        return {}

    # Verificar cache
    cached = cargar_odds_cache()
    if cached:
        return cached

    # Obtener partidos de hoy
    eventos = get_partidos_hoy()
    if not eventos:
        return {}

    todas_odds = {}
    markets_vistos = set()

    for i, evento in enumerate(eventos):
        event_id = evento.get('id')
        home = evento.get('home_team', '')
        away = evento.get('away_team', '')

        if not event_id:
            continue

        print(f"  → Obteniendo odds: {away} @ {home}...", end=' ')

        # Debug en el primer partido para ver markets disponibles
        datos = get_odds_partido(event_id, debug=(i == 0 and debug))
        if datos:
            # Capturar markets disponibles
            bookmakers = datos.get('bookmakers', [])
            if bookmakers and i == 0:
                for bm in bookmakers:
                    for m in bm.get('markets', []):
                        markets_vistos.add(m.get('key'))

            odds = parsear_odds(datos)
            todas_odds.update(odds)
            print(f"✅ {len(odds)} props")
        else:
            print("⚠️  sin datos")

    # Mostrar markets disponibles si no hay props
    if not todas_odds and markets_vistos:
        print(f"\n  ⚠️  No se encontraron player props")
        print(f"  📊 Markets disponibles en tu plan: {sorted(markets_vistos)}")
        print("  💡 Los player props requieren plan de pago en The Odds API")

    # Guardar en cache
    guardar_odds_cache(todas_odds)

    print(f"\n  ✅ {len(todas_odds)} player props obtenidos")
    return todas_odds


# ─────────────────────────────────────────────
# 7. OBTENER TOTALES DEL PARTIDO
# ─────────────────────────────────────────────

def get_odds_totales() -> dict | None:
    """
    Obtiene odds de totales para el primer partido de hoy.
    Para uso rápido en el dashboard.
    """
    api_key = get_api_key()
    if not api_key:
        return None

    eventos = get_partidos_hoy()
    if not eventos:
        return None

    # Obtener primer partido
    evento = eventos[0]
    event_id = evento.get('id')

    if not event_id:
        return None

    datos = get_odds_partido(event_id)
    if not datos:
        return None

    return parsear_odds_totales(datos)


# ─────────────────────────────────────────────
# 8. UTILIDADES
# ─────────────────────────────────────────────

def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza nombres de jugadores para matching.
    Ej: 'LeBron James' -> 'LeBron James'
    """
    # Eliminar caracteres especiales y normalizar
    return nombre.strip()


def buscar_jugador_en_props(jugador_nombre: str, props: dict) -> list[str]:
    """
    Busca las keys de props que coinciden con un jugador.
    Retorna lista de keys como ["NombreJugador_PTS", "NombreJugador_REB", ...]
    """
    coincidencias = []
    jugador_norm = jugador_nombre.lower()

    for key in props.keys():
        if jugador_norm in key.lower():
            coincidencias.append(key)

    return coincidencias


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  🎯 MÓDULO 6: ODDS ENGINE")
    print("=" * 55)

    api_key = get_api_key()
    if not api_key:
        print("\n  ⚠️  API key no configurada")
        print("  → Obtén una gratis en: https://the-odds-api.com")
        print("  → Tienes 500 requests/mes gratis")
    else:
        print(f"\n  ✅ API key configurada")
        print("\n  Probando conexión...")
        props = get_odds_props()
        if props:
            print(f"\n  📊 Ejemplos de props encontrados:")
            for i, (key, val) in enumerate(list(props.items())[:5]):
                print(f"     {key}: línea {val['linea']}, Over {val['odds_over']}, Under {val['odds_under']}")
