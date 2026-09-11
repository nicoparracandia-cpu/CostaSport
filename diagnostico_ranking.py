"""Diagnostico: replica el calculo de fases de app.py e imprime cada paso.
Uso: python3 diagnostico_ranking.py  (desde la carpeta Costa Sport)"""

from db import get_jugadores, cargar_historial
from resultados import calcular_ranking
from pairing import dividir_en_categorias

# 1) Jugadores activos, igual que app.py
jug_db = get_jugadores()
jugadores = [{"Ranking": j["ranking"], "Jugador": j["nombre"],
              "performance": j.get("performance") or 0,
              "puntos_base": j.get("puntos_base") or 0} for j in jug_db]
print(f"1) Jugadores activos desde BD: {len(jugadores)}")
yo = [j for j in jugadores if "Nicol" in j["Jugador"]]
print(f"   Nicolas segun BD -> Ranking {yo[0]['Ranking'] if yo else 'NO ENCONTRADO'}")

# 2) Historial real
h = cargar_historial()
n_part = len(h.get("partidos", []))
con_res = sum(1 for p in h.get("partidos", []) if p.get("resultado"))
print(f"2) Historial: {n_part} partidos, {con_res} con resultado")

# 3) Ranking vivo, igual que el parche
df = calcular_ranking(h, jugadores)
fila = df[df["Jugador"].str.contains("Nicol", case=False)]
print("3) Ranking vivo (calcular_ranking sobre activos):")
print(df[["Pos.", "Jugador", "Puntos", "Performance"]].iloc[14:24].to_string(index=False))
print(f"   -> Nicolas: Pos {int(fila['Pos.'].iloc[0])}, Puntos {int(fila['Puntos'].iloc[0])}")

# 4) Remapeo y division en fases, igual que el parche
pos = {str(r["Jugador"]): int(r["Pos."]) for _, r in df.iterrows()}
for j in jugadores:
    j["Ranking"] = pos.get(j["Jugador"], j["Ranking"])
sin_match = [j["Jugador"] for j in jugadores if j["Jugador"] not in pos]
if sin_match:
    print(f"   OJO: sin match de nombre (quedan con ranking BD): {sin_match}")
jugadores.sort(key=lambda x: x["Ranking"])

cats = dividir_en_categorias(jugadores, n_categorias=3, modo="fases")
print("4) Fases resultantes:")
for nombre, lista in cats.items():
    rangos = f"#{lista[0]['Ranking']}-#{lista[-1]['Ranking']}"
    print(f"   Fase {nombre}: {len(lista)} jugadores ({rangos})")
    for j in lista:
        if "Nicol" in j["Jugador"]:
            print(f"      >>> Nicolas esta AQUI como #{j['Ranking']} <<<")
