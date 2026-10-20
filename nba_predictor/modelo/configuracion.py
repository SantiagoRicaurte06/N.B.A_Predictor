"""
Configuración CONGELADA del modelo de puntos.

Cada valor sale de la validación en 2023-24 y 2024-25 (scripts/recalibrar.py,
detalle en docs/RECALIBRACION.md). Cambiarlo a mano invalida la medición del
holdout: si hay que tocar algo, se vuelve a validar y se documenta.
"""

VERSION = "puntos-v2"

# Grupos de factores que mejoraron el error en validación (ver factores.GRUPOS).
# Rival, calendario, ritmo del equipo y motivación se midieron y no aportaron.
GRUPOS = ["base", "ausencias", "jugador", "lineas"]

# "directo", "minutos" o "mezcla" (promedio de ambos). La mezcla bajó el MAE
# de validación de 4.873 a 4.865; minutos solo, a 4.871 (no supera el umbral).
MODO = "mezcla"

# Mínimo de picks por semana acordado para que el sistema sea útil.
MIN_PICKS_SEMANA = 10

# Piso de probabilidad para apostar: el de mejor ROI en validación con al menos
# MIN_PICKS_SEMANA picks (0.70 → 11 por semana contra la línea informada).
UMBRAL_PROB = 0.70
