# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [0.2.0] · 2026-10-20

Primera versión etiquetada. Reorganiza el proyecto, migra los datos a ESPN,
recalibra el modelo y rediseña el dashboard.

### Añadido

- Datos desde la API de ESPN: box scores con titularidad y motivo de cada
  ausencia, plantillas vigentes, reporte de lesiones y líneas de cierre de cada
  partido. Histórico de 2021-22 a 2025-26 (6 628 partidos).
- Modelo de puntos v2 con factores de forma, historia del jugador, ausencias del
  equipo y líneas de la casa, y probabilidad calibrada de superar cualquier línea.
- Backtest por temporadas con reentreno mensual y holdout único
  (`scripts/recalibrar.py`); resultados en `docs/RECALIBRACION.md`.
- Resolución automática de picks con los box scores del día siguiente.
- Registro de todas las líneas reales de Betano que se ingresan, para medir el
  edge contra la casa.
- Dashboard con tema claro y oscuro y cuatro pestañas: Hoy, Resultados,
  Rendimiento y Modelo.
- Paquete instalable (`pip install -e .`), pruebas en pytest y CI de commits y
  pruebas.
- Skills del equipo y normas de git (`GIT_WORKFLOW.md`, hooks en `.githooks/`).

### Cambiado

- El código pasa de nueve `moduleN_*.py` en la raíz al paquete `nba_predictor/`.
- El piso de probabilidad para apostar sube a 0.70, elegido en validación.
- El gate papel → dinero real se muestra con su criterio decisivo: el límite
  inferior del IC 95 % de Wilson.

### Eliminado

- La fuente `nba_api` (stats.nba.com), el modelo pooled v1, el baseline por
  jugador y el backtest por gamelogs.
- Los modelos de totales y spread y los ajustes heurísticos sin uso.
- La integración con The Odds API.

### Corregido

- `module2` fallaba al importarse por un `datetime` sin importar, lo que impedía
  cargar el modelo pooled.
- Las comprobaciones OVER/UNDER de las pruebas nunca fallaban; ahora son asserts.
- Filtración del futuro en la defensa por posición (detectada por prueba).
- Las líneas sintéticas en la media favorecían al under el 54 % de las veces;
  ahora van en la mediana.
- El reporte de lesiones no se cruzaba con los jugadores.
- El All-Star Game contaba como partido de temporada regular.
- `requirements.txt` pedía el backport `pathlib`, que puede romper la instalación.

[0.2.0]: https://github.com/SantiagoRicaurte06/nba-predictor-pro/releases/tag/v0.2.0
