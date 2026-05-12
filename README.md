# 🎾 Emparejador Escalerilla

App para generar emparejamientos tipo **escalerilla** por categorías, sin repetir parejas hasta completar el ciclo.

## 📋 Cómo funciona

- Lee una lista de jugadores desde Excel (columnas `Ranking` y `Jugador`).
- Divide automáticamente en **N categorías** (default 4) según ranking, llenando las mejores primero.
  - Ej: 46 jugadores → **A=12, B=12, C=11, D=11**
- Cada ronda, cada jugador tiene:
  - **1 partido interno** (vs su misma categoría)
  - **1 partido cruzado** (A↔B, C↔D, ...)
- Usa round-robin (método del círculo) para internos y rotación para cruces.
- Mantiene historial separado por bloque para no repetir parejas.

## 🚀 Uso

### App Streamlit (web)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Flujo:
1. Sube tu Excel con la lista.
2. (Opcional) Sube el `historial.json` de rondas anteriores.
3. Presiona **Generar siguiente ronda**.
4. Descarga el historial actualizado y el Excel de la ronda.

### Script local

```bash
pip install -r requirements.txt
python emparejador.py lista_.xlsx 4
```

Argumentos: `[ruta_excel] [n_categorias]` (ambos opcionales).

Genera:
- `historial.json` — estado para la próxima ronda.
- `rondas/ronda_YYYYMMDD_HHMMSS.xlsx` — partidos de esta ronda.

## 📊 Formato del Excel

| Ranking | Jugador          |
|---------|------------------|
| 1       | Diego Beas       |
| 2       | Jaime Hussein    |
| ...     | ...              |

## 📁 Estructura

```
emparejador-grupos/
├── app.py              # App Streamlit
├── emparejador.py      # Script local
├── pairing.py          # Lógica compartida
├── requirements.txt
├── README.md
└── .gitignore
```
