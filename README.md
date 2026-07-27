# 🏀 NBA PREDICTOR PRO

Sistema completo de predicción NBA con Kelly Criterion.
**Mercados:** Props (Puntos/Rebotes/Asistencias) · Totales O/U · Spread  
**Casa:** Betano (odds decimales)  
**Bankroll:** Kelly Criterion fraccionado al 25%

---

## ⚙️ INSTALACIÓN (una sola vez)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Correr el dashboard
streamlit run dashboard.py
```

Se abrirá automáticamente en tu navegador en: **http://localhost:8501**

---

## 🚀 USO DIARIO

**Cada tarde antes de los juegos:**

1. Abre la terminal en esta carpeta
2. Corre: `streamlit run dashboard.py`
3. En el dashboard:
   - Tab **"Picks del Día"** → Clic en "Cargar datos NBA"
   - Tab **"Ingresar Líneas"** → Ingresa odds de Betano
   - Clic en "Calcular Picks y Stakes"
   - Vuelve a **"Picks del Día"** → tus picks con stakes listos

---

## 📁 ESTRUCTURA

```
nba_predictor/
├── module1_data_engine.py      # Datos + Injury Report
├── module2_prediction_engine.py # Modelos ML
├── module3_stakes_engine.py    # Kelly Criterion
├── dashboard.py                # App Streamlit
├── requirements.txt
└── cache/                      # Datos cacheados (auto-generado)
    ├── gamelog_*.csv           # Historial de jugadores
    ├── injury_report.csv       # Lesiones del día
    ├── bankroll.json           # Estado del bankroll
    └── historial_apuestas.csv  # Registro de picks
```

---

## 🧠 MÓDULOS

| Módulo | Función |
|--------|---------|
| Data Engine | Descarga stats NBA, injury report, efectos de ausencias |
| Prediction Engine | XGBoost para props, Poisson para totales, Normal para spread |
| Stakes Engine | Kelly Criterion 25%, gestión de bankroll, historial |
| Dashboard | Interfaz Streamlit completa |

---

## ⚠️ NOTAS

- El sistema **no se conecta a Betano** — ingresas las odds manualmente
- Cache de gamelogs: 6 horas | Injury report: 2 horas
- Para actualizar jugadores All-Stars editar lista en `module1_data_engine.py`
- Bankroll y historial persisten entre sesiones en carpeta `cache/`
