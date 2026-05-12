"""
emparejador.py
--------------
Script local para generar la siguiente ronda de escalerilla.

USO:
    python emparejador.py [ruta_excel] [n_categorias]

Genera:
  - historial.json
  - rondas/ronda_YYYYMMDD_HHMMSS.xlsx
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

from pairing import (
    dividir_en_categorias,
    cargar_historial,
    guardar_historial,
    siguiente_ronda_completa,
    resultados_a_dataframe,
)

RUTA_EXCEL_DEFAULT = "lista_.xlsx"
RUTA_HISTORIAL = "historial.json"
CARPETA_RONDAS = "rondas"
N_CATEGORIAS = 4


def main():
    ruta_excel = sys.argv[1] if len(sys.argv) > 1 else RUTA_EXCEL_DEFAULT
    n_cat = int(sys.argv[2]) if len(sys.argv) > 2 else N_CATEGORIAS

    if not Path(ruta_excel).exists():
        print(f"❌ No se encontró el archivo: {ruta_excel}")
        sys.exit(1)

    df = pd.read_excel(ruta_excel)
    if "Ranking" not in df.columns or "Jugador" not in df.columns:
        print(f"❌ Columnas requeridas: 'Ranking' y 'Jugador'. Encontradas: {list(df.columns)}")
        sys.exit(1)

    jugadores = df.to_dict("records")
    categorias = dividir_en_categorias(jugadores, n_categorias=n_cat)

    print(f"📋 {len(jugadores)} jugadores cargados.")
    for nombre, lista in categorias.items():
        print(f"   Categoría {nombre}: {len(lista)} jugadores (#{lista[0]['Ranking']}–#{lista[-1]['Ranking']})")

    historial = cargar_historial(RUTA_HISTORIAL)
    if "grupos" in historial and "internas" not in historial:
        print("⚠️  Historial con formato antiguo detectado, se reiniciará.")
        historial = {}

    resultados = siguiente_ronda_completa(categorias, historial)

    print("\n" + "=" * 70)
    print("🎯 RONDA GENERADA")
    print("=" * 70)
    for res in resultados:
        print(f"\n[{res['tipo']}] {res['bloque']} — Ronda {res['ronda']}/{res['total_rondas']} (Ciclo {res['ciclo']})")
        print("-" * 70)
        for i, (p1, p2) in enumerate(res["parejas"], 1):
            print(f"  {i:>2}. #{p1['Ranking']:>2} {p1['Jugador']:<22} ↔ #{p2['Ranking']:>2} {p2['Jugador']}")
        for j in res["descansan"]:
            print(f"  💤 Descansa: #{j['Ranking']} {j['Jugador']}")

    guardar_historial(historial, RUTA_HISTORIAL)

    Path(CARPETA_RONDAS).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{CARPETA_RONDAS}/ronda_{timestamp}.xlsx"
    df_ronda = resultados_a_dataframe(resultados)
    df_ronda.to_excel(nombre_archivo, index=False)

    print(f"\n✅ Historial guardado: {RUTA_HISTORIAL}")
    print(f"✅ Ronda exportada: {nombre_archivo}")


if __name__ == "__main__":
    main()
