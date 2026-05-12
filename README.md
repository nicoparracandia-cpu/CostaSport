# 🎾 Emparejador Escalerilla

App para generar emparejamientos tipo **escalerilla** por categorías, cargar resultados y mantener ranking acumulado de toda la temporada.

## 📋 Cómo funciona

- Divide la lista en **N categorías** (default 4) según ranking, llenando las mejores primero.
  - Ej: 46 jugadores → **A=12, B=12, C=11, D=11**
- Cada ronda, cada jugador tiene:
  - **1 partido interno** (vs su misma categoría)
  - **1 partido cruzado** (A↔B, C↔D, ...)
- No se repiten parejas hasta completar el ciclo.

## 🏆 Sistema de puntaje

| Resultado | Puntos |
|---|---|
| Partido ganado | 200 |
| Partido perdido | 25 |
| W.O. a favor (te presentaste) | 50 |
| W.O. en contra (no te presentaste) | 0 |

> El W.O. debe evidenciarse (foto, mensaje, etc.) al registrarlo en la app.

## 🚀 Uso (App web)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Flujo de uso

1. **Sidebar:** sube tu Excel con la lista de jugadores.
2. **Tab "Generar Ronda":** presiona el botón para crear los partidos de la siguiente ronda.
3. **Tab "Cargar Resultados":** ingresa los resultados (sets y games, o W.O.) de cada partido.
4. **Tab "Ranking":** mira el ranking acumulado de la temporada.
5. **Descarga `historial.json`** desde el sidebar para no perder el progreso. La próxima vez súbelo al inicio para continuar.

## 📊 Formato del Excel

| Ranking | Jugador          |
|---------|------------------|
| 1       | Marcelo Rios     |
| 2       | Roger Federer    |
| ...     | ...              |

## 📁 Estructura

```
emparejador-grupos/
├── app.py              # App Streamlit con 3 pestañas
├── emparejador.py      # Script local (solo generación de rondas)
├── pairing.py          # Lógica de emparejamiento
├── resultados.py       # Lógica de resultados y ranking
├── requirements.txt
├── README.md
└── .gitignore
```
