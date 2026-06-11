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
    Divide los jugadores en N categorías. Las primeras (mejor ranking) llenan primero.

    Ej: 46 jugadores, 4 categorías → A=12, B=12, C=11, D=11.
    """
    jugadores_ordenados = sorted(jugadores, key=lambda p: p["Ranking"])
    n = len(jugadores_ordenados)
    base = n // n_categorias
    resto = n % n_categorias

    categorias = {}
    idx = 0
    for i in range(n_categorias):
        tamano = base + (1 if i < resto else 0)
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


def _reconstruir_pares_cruce(historial: dict) -> None:
    """
    Si el historial aún no tiene registro anti-repetición ('pares_cruce'),
    lo reconstruye a partir de los partidos cruzados ya generados.
    Así las jornadas previas al cambio de lógica también cuentan
    y no se repiten cruces ya jugados.
    """
    if "pares_cruce" in historial:
        return
    registro: dict[str, list] = {}
    for p in historial.get("partidos", []):
        if p.get("tipo") != "Cruzado":
            continue
        bloque = p.get("bloque", "")
        par = sorted((p["jugador_1"]["Jugador"], p["jugador_2"]["Jugador"]))
        registro.setdefault(bloque, []).append(par)
    historial["pares_cruce"] = registro


def siguiente_ronda_completa(categorias: dict[str, list[dict]], historial: dict) -> list[dict]:
    """
    Genera una ronda completa: internos para cada categoría + cruces entre pares (A-B, C-D, ...).
    """
    _reconstruir_pares_cruce(historial)
    resultados = []
    nombres = list(categorias.keys())

    # --- Internos ---
    # Si una categoría es impar, el jugador que queda libre del interno
    # se guarda aquí para asignarle un partido extra en el cruce.
    libres_interno: dict[str, dict] = {}

    for nombre in nombres:
        jugadores = categorias[nombre]
        if len(jugadores) < 2:
            continue
        todas = generar_todas_las_rondas_internas(jugadores)
        total = len(todas)
        idx, ciclo = _avanzar_estado(historial, "internas", nombre, total)

        # Round-robin normal: si la categoría es impar, uno queda libre
        ronda = todas[idx]
        parejas = []
        libre = None
        for p1, p2 in ronda:
            if p1 is None:
                libre = p2
            elif p2 is None:
                libre = p1
            else:
                parejas.append((p1, p2))

        if libre is not None:
            libres_interno[nombre] = libre

        resultados.append({
            "tipo": "Interno",
            "bloque": nombre,
            "ronda": idx + 1,
            "total_rondas": total,
            "ciclo": ciclo,
            "parejas": parejas,
            "descansan": [],
            "nota": f"ℹ️ {libre['Jugador']} no tiene interno: jugará 2 cruces." if libre else "",
        })

    # --- Cruces (A-B, C-D, ...) ---
    for i in range(0, len(nombres), 2):
        if i + 1 >= len(nombres):
            break
        nombre_x, nombre_y = nombres[i], nombres[i + 1]
        grupo_x, grupo_y = categorias[nombre_x], categorias[nombre_y]
        if not grupo_x or not grupo_y:
            continue
        total = max(len(grupo_x), len(grupo_y))
        bloque = f"{nombre_x}-{nombre_y}"
        idx, ciclo = _avanzar_estado(historial, "cruces", bloque, total)

        libre_x = libres_interno.pop(nombre_x, None)
        libre_y = libres_interno.pop(nombre_y, None)

        registro = historial.setdefault("pares_cruce", {})
        jugados = registro.setdefault(bloque, [])

        parejas, jugados = _matching_cruce(grupo_x, grupo_y, libre_x, libre_y, jugados)
        registro[bloque] = jugados

        notas = []
        for libre in (libre_x, libre_y):
            if libre is not None:
                rivales = [p2["Jugador"] if p1["Jugador"] == libre["Jugador"] else p1["Jugador"]
                           for p1, p2 in parejas
                           if libre["Jugador"] in (p1["Jugador"], p2["Jugador"])]
                if len(rivales) > 1:
                    notas.append(f"⚡ {libre['Jugador']} juega 2 cruces ({' y '.join(rivales)}).")

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


def _matching_cruce(grupo_x: list[dict], grupo_y: list[dict],
                    libre_x: dict | None, libre_y: dict | None,
                    jugados_lista: list) -> tuple[list, list]:
    """
    Construye los cruces de una jornada garantizando:
    - Cada jugador juega exactamente 1 cruce; el 'libre' del interno
      (categoria impar) juega 2 cruces.
    - Prioriza pares nunca jugados. Si es imposible (rivales agotados),
      permite la repeticion MINIMA necesaria (pares jugados menos veces),
      sin borrar nunca el historial.

    jugados_lista: lista de pares [j1, j2] jugados (con duplicados = contador).
    """
    from collections import Counter

    def construir_slots(grupo, libre):
        slots = []
        for j in grupo:
            n = 2 if (libre is not None and j["Jugador"] == libre["Jugador"]) else 1
            slots.extend([j] * n)
        return slots

    slots_x = construir_slots(grupo_x, libre_x)
    slots_y = construir_slots(grupo_y, libre_y)

    if len(slots_x) != len(slots_y):
        minimo = min(len(slots_x), len(slots_y))
        slots_x, slots_y = slots_x[:minimo], slots_y[:minimo]

    def clave(a, b):
        return tuple(sorted((a["Jugador"], b["Jugador"])))

    veces = Counter(tuple(sorted(p)) for p in jugados_lista)

    def resolver(umbral):
        """Solo permite pares jugados menos de 'umbral' veces."""
        n = len(slots_x)
        usados_y = [False] * n
        asignacion = [None] * n

        def backtrack(i, pares_jornada):
            if i == n:
                return True
            x = slots_x[i]
            # Probar primero los rivales menos jugados (minimiza repeticiones)
            orden = sorted(range(n), key=lambda k: veces.get(clave(x, slots_y[k]), 0))
            for k in orden:
                if usados_y[k]:
                    continue
                y = slots_y[k]
                c = clave(x, y)
                if veces.get(c, 0) >= umbral or c in pares_jornada:
                    continue
                usados_y[k] = True
                asignacion[i] = y
                pares_jornada.add(c)
                if backtrack(i + 1, pares_jornada):
                    return True
                usados_y[k] = False
                asignacion[i] = None
                pares_jornada.discard(c)
            return False

        if backtrack(0, set()):
            return [(slots_x[i], asignacion[i]) for i in range(n)]
        return None

    parejas = None
    for umbral in range(1, 10):  # 1 = solo pares nunca jugados
        parejas = resolver(umbral)
        if parejas is not None:
            break
    if parejas is None:
        return [], jugados_lista

    for p1, p2 in parejas:
        jugados_lista.append(list(clave(p1, p2)))
    return parejas, jugados_lista



# ============================================================================
#  Historial I/O
# ============================================================================

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
