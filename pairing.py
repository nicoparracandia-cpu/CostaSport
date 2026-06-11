"""
pairing.py
----------
Lógica de emparejamiento para escalerilla por categorías.

- Divide la lista en N categorías (default 4) llenando las mejores primero.
- Cada ronda genera: 1 partido interno + 1 partido cruzado por jugador.
- Cruces: A-B, C-D, E-F, ...
- Historial separado por bloque (cada uno con su propio ciclo).
"""
from __future__ import annotations
import json
from pathlib import Path

NUM_CATEGORIAS = 4


# ============================================================================
#  División en categorías
# ============================================================================

def dividir_en_categorias(jugadores: list[dict], n_categorias: int = NUM_CATEGORIAS) -> dict[str, list[dict]]:
    """
    Divide los jugadores en N categorías por ranking (las mejores primero).

    Regla de paridad:
    - Total PAR  → todas las categorías quedan con tamaño par
      (jornadas perfectas, sin partidos especiales).
    - Total IMPAR → la ÚNICA categoría impar es la última (D), donde está
      el último jugador del ranking (el "ancla" que juega 2 internos).

    Ej: 39 → A=10, B=10, C=10, D=9 · 41 → A=10, B=10, C=10, D=11
        40 → 10/10/10/10 · 42 → A=12, B=10, C=10, D=10
    """
    jugadores_ordenados = sorted(jugadores, key=lambda p: p["Ranking"])
    n = len(jugadores_ordenados)

    if n % 2 == 1:
        # Última categoría impar, lo más cercana al promedio
        prom = n / n_categorias
        ultima = round(prom)
        if ultima % 2 == 0:
            ultima += 1 if prom >= ultima else -1
        ultima = max(1, ultima)
        resto_total = n - ultima
    else:
        ultima = None
        resto_total = n

    # Repartir el resto en (n_categorias - 1 si hay impar, si no n_categorias)
    # tamaños PARES y balanceados, dando los extras a las primeras categorías
    n_pares = n_categorias - (1 if ultima is not None else 0)
    base = (resto_total // n_pares)
    if base % 2 == 1:
        base -= 1
    sobra = resto_total - base * n_pares  # múltiplo de 2
    tamanos = []
    for i in range(n_pares):
        extra = 2 if sobra > 0 else 0
        sobra -= extra
        tamanos.append(base + extra)
    if ultima is not None:
        tamanos.append(ultima)

    categorias = {}
    idx = 0
    for i, tamano in enumerate(tamanos):
        nombre = chr(65 + i)
        categorias[nombre] = jugadores_ordenados[idx:idx + tamano]
        idx += tamano
    return categorias


# ============================================================================
#  Round-robin interno (método del círculo)
# ============================================================================

def generar_todas_las_rondas_internas(jugadores_categoria: list[dict]) -> list[list[tuple]]:
    """
    Genera todas las rondas internas de una categoría (método del círculo).
    Si el número es par: todos juegan, sin descanso.
    Si es impar: todos juegan igualmente (se agrega None para el algoritmo,
    pero el llamador decide cómo manejar al que "descansa").
    """
    jugadores = list(jugadores_categoria)
    if len(jugadores) % 2 == 1:
        jugadores.append(None)

    n = len(jugadores)
    mitad = n // 2
    rondas = []
    fijo = jugadores[0]
    rotantes = jugadores[1:]

    for _ in range(n - 1):
        ronda = [(fijo, rotantes[0])]
        for i in range(1, mitad):
            ronda.append((rotantes[i], rotantes[-i]))
        rondas.append(ronda)
        rotantes = [rotantes[-1]] + rotantes[:-1]
    return rondas


def generar_ronda_interna_sin_descanso(jugadores_categoria: list[dict], idx: int) -> list:
    """
    Para categoría impar: el que iba a descansar juega un partido extra
    contra un rival aleatorio de la misma categoría.
    Nadie descansa — todos juegan al menos 1 partido.
    """
    import random
    todas = generar_todas_las_rondas_internas(jugadores_categoria)
    ronda = todas[idx % len(todas)]

    parejas = []
    jugador_sin_partido = None

    for p1, p2 in ronda:
        if p1 is None:
            jugador_sin_partido = p2
        elif p2 is None:
            jugador_sin_partido = p1
        else:
            parejas.append((p1, p2))

    if jugador_sin_partido is not None:
        # Elegir rival aleatorio entre todos los que ya tienen pareja
        rivales_posibles = [j for par in parejas for j in par if j != jugador_sin_partido]
        if rivales_posibles:
            rival_extra = random.choice(rivales_posibles)
            parejas.append((jugador_sin_partido, rival_extra))

    return parejas


# ============================================================================
#  Cruces entre dos categorías
# ============================================================================

def cruce_para_ronda(grupo_x: list[dict], grupo_y: list[dict], ronda_idx: int) -> tuple:
    """
    Genera cruces grupo_x vs grupo_y para la ronda dada.
    Si tamaños son iguales: rotación clásica, todos juegan.
    Si son distintos: el más grande tiene un descanso rotativo.

    Returns: (parejas, descansan, total_rondas_unicas)
    """
    n_x, n_y = len(grupo_x), len(grupo_y)

    if n_x == n_y:
        n = n_x
        parejas = [(grupo_x[i], grupo_y[(i + ronda_idx) % n]) for i in range(n)]
        return parejas, [], n

    # Tamaños distintos: extender con None
    if n_x < n_y:
        x_ext = list(grupo_x) + [None] * (n_y - n_x)
        y_ext = list(grupo_y)
    else:
        x_ext = list(grupo_x)
        y_ext = list(grupo_y) + [None] * (n_x - n_y)

    n = len(x_ext)
    parejas = []
    descansan = []
    for i in range(n):
        x = x_ext[i]
        y = y_ext[(i + ronda_idx) % n]
        if x is None and y is not None:
            descansan.append(y)
        elif y is None and x is not None:
            descansan.append(x)
        elif x is not None and y is not None:
            parejas.append((x, y))
    return parejas, descansan, n


# ============================================================================
#  Estado e historial
# ============================================================================

def _avanzar_estado(historial: dict, seccion: str, bloque: str, total: int) -> tuple[int, int]:
    """Avanza el contador del bloque, reinicia ciclo si corresponde."""
    historial.setdefault(seccion, {})
    estado = historial[seccion].get(bloque, {"ronda_actual": 0, "ciclo": 1, "total_rondas": total})
    idx = estado["ronda_actual"]
    ciclo = estado["ciclo"]
    if idx >= total:
        idx = 0
        ciclo += 1
    historial[seccion][bloque] = {"ronda_actual": idx + 1, "ciclo": ciclo, "total_rondas": total}
    return idx, ciclo


def _contador_pares(historial: dict):
    """Cuenta cuántas veces se ha enfrentado cada par, según los partidos
    ya generados. Fuente única de verdad: historial['partidos']."""
    from collections import Counter
    c = Counter()
    for p in historial.get("partidos", []):
        c[tuple(sorted((p["jugador_1"]["Jugador"], p["jugador_2"]["Jugador"])))] += 1
    return c


def _clave(a: dict, b: dict) -> tuple:
    return tuple(sorted((a["Jugador"], b["Jugador"])))


def _emparejar_grupo(grupo: list[dict], veces) -> list[tuple]:
    """Empareja un grupo PAR entre sí, minimizando repeticiones
    (prefiere pares jugados menos veces). Backtracking con relajación."""
    n = len(grupo)
    if n == 0:
        return []

    def resolver(umbral):
        usados = [False] * n
        resultado = []

        def backtrack(restantes):
            if not restantes:
                return True
            i = restantes[0]
            orden = sorted(restantes[1:], key=lambda k: veces.get(_clave(grupo[i], grupo[k]), 0))
            for k in orden:
                if veces.get(_clave(grupo[i], grupo[k]), 0) >= umbral:
                    continue
                resultado.append((grupo[i], grupo[k]))
                if backtrack([r for r in restantes[1:] if r != k]):
                    return True
                resultado.pop()
            return False

        if backtrack(list(range(n))):
            return list(resultado)
        return None

    for umbral in range(1, 20):
        sol = resolver(umbral)
        if sol is not None:
            return sol
    return []


def _emparejar_cruzado(grupo_x: list[dict], grupo_y: list[dict], veces) -> list[tuple]:
    """Empareja dos grupos del MISMO tamaño 1 a 1, minimizando
    repeticiones. Backtracking con relajación de umbral."""
    n = len(grupo_x)
    if n == 0:
        return []

    def resolver(umbral):
        usados = [False] * n
        asignacion = [None] * n

        def backtrack(i):
            if i == n:
                return True
            x = grupo_x[i]
            orden = sorted(range(n), key=lambda k: veces.get(_clave(x, grupo_y[k]), 0))
            for k in orden:
                if usados[k]:
                    continue
                if veces.get(_clave(x, grupo_y[k]), 0) >= umbral:
                    continue
                usados[k] = True
                asignacion[i] = grupo_y[k]
                if backtrack(i + 1):
                    return True
                usados[k] = False
                asignacion[i] = None
            return False

        if backtrack(0):
            return [(grupo_x[i], asignacion[i]) for i in range(n)]
        return None

    for umbral in range(1, 20):
        sol = resolver(umbral)
        if sol is not None:
            return sol
    return []


def siguiente_ronda_completa(categorias: dict[str, list[dict]], historial: dict) -> list[dict]:
    """
    Genera la jornada: partidos internos + cruzados.

    Reglas:
    - Todos los jugadores quedan con EXACTAMENTE 2 partidos. Nadie descansa.
    - Si una categoría es impar, su ÚLTIMO jugador del ranking (el "ancla")
      juega sus 2 partidos como internos contra 2 compañeros de categoría.
      Esos 2 rivales no juegan el interno normal (completan con su cruce).
    - El ancla no participa del cruce; si por eso el cruce queda desparejo,
      los sobrantes del grupo mayor juegan entre sí.
    - Anti-repetición: se priorizan SIEMPRE los pares jugados menos veces
      (calculado desde el historial real de partidos).
    """
    veces = _contador_pares(historial)
    resultados = []
    nombres = list(categorias.keys())
    participa_cruce: dict[str, list] = {}

    # --- Internos ---
    for nombre in nombres:
        jugadores = categorias[nombre]
        if len(jugadores) < 2:
            participa_cruce[nombre] = list(jugadores)
            continue
        todas = generar_todas_las_rondas_internas(jugadores)
        total = len(todas)
        idx, ciclo = _avanzar_estado(historial, "internas", nombre, total)
        nota = ""

        if len(jugadores) % 2 == 0:
            # Categoría par: round-robin clásico, sin repeticiones por ciclo
            ronda = todas[idx]
            parejas = [(p1, p2) for p1, p2 in ronda if p1 is not None and p2 is not None]
            participa_cruce[nombre] = list(jugadores)
        else:
            # Categoría impar: el ÚLTIMO del ranking es el ancla
            ancla = jugadores[-1]
            otros = jugadores[:-1]
            # Sus 2 rivales: los compañeros que MENOS veces ha enfrentado
            rivales = sorted(
                otros,
                key=lambda j: (veces.get(_clave(ancla, j), 0), j["Ranking"]),
            )[:2]
            resto = [j for j in otros if j["Jugador"] not in {r["Jugador"] for r in rivales}]
            parejas = [(ancla, rivales[0]), (ancla, rivales[1])]
            parejas += _emparejar_grupo(resto, veces)
            participa_cruce[nombre] = otros  # todos menos el ancla
            nota = (f"⚓ {ancla['Jugador']} juega sus 2 partidos internos contra "
                    f"{rivales[0]['Jugador']} y {rivales[1]['Jugador']} "
                    f"(ellos completan su jornada con el cruce).")

        for p1, p2 in parejas:
            veces[_clave(p1, p2)] += 1

        resultados.append({
            "tipo": "Interno",
            "bloque": nombre,
            "ronda": idx + 1,
            "total_rondas": total,
            "ciclo": ciclo,
            "parejas": parejas,
            "descansan": [],
            "nota": nota,
        })

    # --- Cruces (A-B, C-D, ...) ---
    for i in range(0, len(nombres), 2):
        if i + 1 >= len(nombres):
            break
        nombre_x, nombre_y = nombres[i], nombres[i + 1]
        gx = list(participa_cruce.get(nombre_x, []))
        gy = list(participa_cruce.get(nombre_y, []))
        if not gx or not gy:
            continue
        total = max(len(categorias[nombre_x]), len(categorias[nombre_y]))
        bloque = f"{nombre_x}-{nombre_y}"
        idx, ciclo = _avanzar_estado(historial, "cruces", bloque, total)
        notas = []

        # Balancear: los sobrantes del grupo mayor juegan entre sí
        parejas_sobrantes = []
        if len(gx) != len(gy):
            mayor, menor = (gx, gy) if len(gx) > len(gy) else (gy, gx)
            d = len(mayor) - len(menor)  # siempre par
            # Elegir los d sobrantes cuyo emparejamiento mutuo esté menos repetido
            import itertools
            mejor = None
            for combo in itertools.combinations(range(len(mayor)), d):
                cand = [mayor[c] for c in combo]
                pares = _emparejar_grupo(cand, veces)
                costo = sum(veces.get(_clave(p1, p2), 0) for p1, p2 in pares)
                if mejor is None or costo < mejor[0]:
                    mejor = (costo, combo, pares)
                if mejor[0] == 0:
                    break
            _, combo, parejas_sobrantes = mejor
            sobrantes_nombres = {mayor[c]["Jugador"] for c in combo}
            mayor_filtrado = [j for j in mayor if j["Jugador"] not in sobrantes_nombres]
            if len(gx) > len(gy):
                gx = mayor_filtrado
            else:
                gy = mayor_filtrado
            for p1, p2 in parejas_sobrantes:
                notas.append(f"🔁 {p1['Jugador']} y {p2['Jugador']} juegan entre sí "
                             f"(sin rival de cruce esta jornada).")

        parejas = _emparejar_cruzado(gx, gy, veces)
        parejas += parejas_sobrantes

        for p1, p2 in parejas:
            veces[_clave(p1, p2)] += 1

        resultados.append({
            "tipo": "Cruzado",
            "bloque": bloque,
            "ronda": idx + 1,
            "total_rondas": total,
            "ciclo": ciclo,
            "parejas": parejas,
            "descansan": [],
            "nota": " ".join(notas),
        })

    return resultados


def cargar_historial(ruta) -> dict:
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_historial(historial: dict, ruta) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)


def historial_a_json(historial: dict) -> str:
    return json.dumps(historial, ensure_ascii=False, indent=2)


# ============================================================================
#  Conversión a DataFrame
# ============================================================================

def resultados_a_dataframe(resultados: list[dict]):
    """Convierte resultados a DataFrame (una fila por pareja o descanso)."""
    import pandas as pd
    filas = []
    for res in resultados:
        for n, (p1, p2) in enumerate(res["parejas"], 1):
            filas.append({
                "Tipo": res["tipo"],
                "Bloque": res["bloque"],
                "Ronda": res["ronda"],
                "Ciclo": res["ciclo"],
                "Pareja N°": n,
                "Ranking 1": p1["Ranking"],
                "Jugador 1": p1["Jugador"],
                "Ranking 2": p2["Ranking"],
                "Jugador 2": p2["Jugador"],
            })
        for jugador in res["descansan"]:
            filas.append({
                "Tipo": res["tipo"],
                "Bloque": res["bloque"],
                "Ronda": res["ronda"],
                "Ciclo": res["ciclo"],
                "Pareja N°": "—",
                "Ranking 1": jugador["Ranking"],
                "Jugador 1": jugador["Jugador"],
                "Ranking 2": "",
                "Jugador 2": "DESCANSA",
            })
    return pd.DataFrame(filas)
