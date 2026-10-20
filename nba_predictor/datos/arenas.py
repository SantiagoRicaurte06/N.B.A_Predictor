"""
Ubicación de la arena de cada equipo, con las abreviaturas de ESPN.

Sirve para medir el viaje entre partidos (distancia y cambio de huso
horario) y la altitud de Denver y Utah. Las coordenadas son de la ciudad;
para distancias entre ciudades la precisión sobra.
"""

from math import asin, cos, radians, sin, sqrt

# equipo: (latitud, longitud, desfase UTC en horario estándar, altitud en m)
ARENAS = {
    "ATL": (33.757, -84.396, -5, 320), "BOS": (42.366, -71.062, -5, 5),
    "BKN": (40.683, -73.976, -5, 10), "CHA": (35.225, -80.839, -5, 230),
    "CHI": (41.881, -87.674, -6, 180), "CLE": (41.496, -81.688, -5, 200),
    "DAL": (32.790, -96.810, -6, 140), "DEN": (39.749, -105.008, -7, 1609),
    "DET": (42.341, -83.055, -5, 190), "GS": (37.768, -122.388, -8, 5),
    "HOU": (29.751, -95.362, -6, 15), "IND": (39.764, -86.156, -5, 220),
    "LAC": (33.945, -118.343, -8, 30), "LAL": (34.043, -118.267, -8, 90),
    "MEM": (35.138, -90.051, -6, 80), "MIA": (25.781, -80.188, -5, 2),
    "MIL": (43.045, -87.917, -6, 190), "MIN": (44.979, -93.276, -6, 260),
    "NO": (29.949, -90.082, -6, 2), "NY": (40.751, -73.993, -5, 10),
    "OKC": (35.463, -97.515, -6, 370), "ORL": (28.539, -81.384, -5, 30),
    "PHI": (39.901, -75.172, -5, 10), "PHX": (33.446, -112.071, -7, 340),
    "POR": (45.532, -122.667, -8, 15), "SAC": (38.580, -121.500, -8, 10),
    "SA": (29.427, -98.438, -6, 200), "TOR": (43.643, -79.379, -5, 80),
    "UTAH": (40.768, -111.901, -7, 1288), "WSH": (38.898, -77.021, -5, 20),
}

EQUIPOS_NBA = frozenset(ARENAS)


def distancia_km(a: str, b: str) -> float:
    """Distancia en línea recta entre las arenas de dos equipos."""
    if a == b or a not in ARENAS or b not in ARENAS:
        return 0.0
    la1, lo1, _, _ = ARENAS[a]
    la2, lo2, _, _ = ARENAS[b]
    la1, lo1, la2, lo2 = map(radians, (la1, lo1, la2, lo2))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def desfase(equipo: str) -> int:
    return ARENAS.get(equipo, (0, 0, 0, 0))[2]


def altitud(equipo: str) -> int:
    return ARENAS.get(equipo, (0, 0, 0, 0))[3]
