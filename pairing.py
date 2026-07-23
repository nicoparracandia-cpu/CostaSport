
"""
pairing.py
----------
Lógica de emparejamiento para escalerilla. Soporta DOS modos:

MODO "clasico" (original):
- 4 categorías por ranking, tamaños pares (regla de paridad con ancla).
- Cada fecha: 2 partidos por jugador = 1 interno + 1 cruce (A-B, C-D).
- Roster impar: el ancla (último del ranking) juega sus 2 internos.

MODO "fases" (nuevo):
- 3 fases por ranking (ej: 39 → A=15, B=12, C=12).
- Cada fecha: 3 partidos por jugador, TODOS dentro de su fase
  (3 rondas consecutivas del round-robin, método del círculo).
- Fase PAR: todos juegan exactamente 3.
- Fase IMPAR: todos juegan 3 salvo UNO que juega 4 para calzar la
  paridad (n impar × 3 sería impar; el total debe ser par).

Ambos modos comparten historial["partidos"] (anti-repetición global),
pero llevan contadores de ronda separados para poder alternar sin
pisarse el estado.

Uso desde la app:
    modo = "clasico"  # o "fases"
    cats = dividir_en_categorias(jugadores, modo=modo)
    resultados = siguiente_ronda_completa(cats, historial, modo=modo)
"""
from __future__ import annotations
import json
from pathlib import Path

MODO_DEFAULT = "clasico"

# --- modo clásico ---
NUM_CATEGORIAS = 4

# --- modo fases ---
NUM_FASES = 3
PARTIDOS_POR_FECHA = 3  # rondas internas consumidas por fecha


# ============================================================================
#  División en categorías / fases
# ============================================================================

def dividir_en_categorias(jugadores: list[dict], n_categorias: int | None = None,
                          modo: str = MODO_DEFAULT) -> dict[str, list[dict]]:
    """Divide los jugadores según el modo elegido."""
    if modo == "fases":
        return _dividir_fases(jugadores, n_categorias or NUM_FASES)
    return _dividir_clasico(jugadores, n_categorias or NUM_CATEGORIAS)


def _dividir_clasico(jugadores: list[dict], n_categorias: int = NUM_CATEGORIAS) -> dict[str, list[dict]]:
    """
    (MODO CLÁSICO) Divide en N categorías por ranking (las mejores primero).

    Regla de paridad:
    - Total PAR  → todas las categorías quedan con tamaño par.
    - Total IMPAR → la ÚNICA categoría impar es la última (D), donde está
      el último jugador del ranking (el "ancla" que juega 2 internos).

    Ej: 39 → A=10, B=10, C=10, D=9 · 40 → 10/10/10/10
    """
    jugadores_ordenados = sorted(jugadores, key=lambda p: p["Ranking"])
    n = len(jugadores_ordenados)

    if n % 2 == 1:
        prom = n / n_categorias
        ultima = round(prom)
        if ultima % 2 == 0:
            ultima += 1 if prom >= ultima else -1
        ultima = max(1, ultima)
        resto_total = n - ultima
    else:
        ultima = None
        resto_total = n

    n_pares = n_categorias - (1 if ultima is not None else 0)
    base = (resto_total // n_pares)
    if base % 2 == 1:
        base -= 1
    sobra = resto_total - base * n_pares
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


def _dividir_fases(jugadores: list[dict], n_fases: int = NUM_FASES) -> dict[str, list[dict]]:
    """
    (MODO FASES) Divide en N fases por ranking (las mejores primero).

    - Se prefieren fases de tamaño PAR (fechas limpias, todos juegan 3).
    - Si el total es IMPAR, la ÚNICA fase impar es la PRIMERA (A).
      En la fase impar, un jugador juega 4 por fecha.

    Ej: 39 → A=15, B=12, C=12 · 40 → A=14, B=14, C=12
    """
    jugadores_ordenados = sorted(jugadores, key=lambda p: p["Ranking"])
    n = len(jugadores_ordenados)

    base = (n // n_fases)
    if base % 2 == 1:
        base -= 1
    sobra = n - base * n_fases

    tamanos = [base] * n_fases
    i = 0
    while sobra >= 2:
        tamanos[i % n_fases] += 2
        sobra -= 2
        i += 1
    if sobra == 1:
        tamanos[0] += 1

    categorias = {}
    idx = 0
    for i, tamano in enumerate(tamanos):
        nombre = chr(65 + i)
        categorias[nombre] = jugadores_ordenados[idx:idx + tamano]
        idx += tamano
    return categorias


# ============================================================================
#  Round-robin interno (método del círculo) — compartido
# ============================================================================

def generar_todas_las_rondas_internas(jugadores_categoria: list[dict]) -> list[list[tuple]]:
    """
    Genera todas las rondas internas (método del círculo).
    Si el número es impar se agrega None ('bye').
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


# ============================================================================
#  Estado e historial — compartido
# ============================================================================

def _avanzar_estado(historial: dict, seccion: str, bloque: str, total: int) -> tuple[int, int]:
    """Avanza el contador del bloque de a 1, reinicia ciclo si corresponde."""
    historial.setdefault(seccion, {})
    estado = historial[seccion].get(bloque, {"ronda_actual": 0, "ciclo": 1, "total_rondas": total})
    idx = estado["ronda_actual"]
    ciclo = estado["ciclo"]
    if idx >= total:
        idx = 0
        ciclo += 1
    historial[seccion][bloque] = {"ronda_actual": idx + 1, "ciclo": ciclo, "total_rondas": total}
    return idx, ciclo


def _avanzar_estado_n(historial: dict, seccion: str, bloque: str, total: int, paso: int) -> tuple[int, int]:
    """Avanza el contador del bloque `paso` rondas por fecha."""
    historial.setdefault(seccion, {})
    total = max(1, total)
    estado = historial[seccion].get(bloque, {"ronda_actual": 0, "ciclo": 1, "total_rondas": total})
    idx = estado["ronda_actual"] % total
    ciclo = estado["ciclo"]
    nuevo = idx + paso
    if nuevo >= total:
        nuevo %= total
        ciclo += 1
    historial[seccion][bloque] = {"ronda_actual": nuevo, "ciclo": ciclo, "total_rondas": total}
    return idx, ciclo


def _contador_pares(historial: dict):
    """Cuenta cuántas veces se ha enfrentado cada par (todos los modos).
    Fuente única de verdad: historial['partidos']."""
    from collections import Counter
    c = Counter()
    for p in historial.get("partidos", []):
        c[tuple(sorted((p["jugador_1"]["Jugador"], p["jugador_2"]["Jugador"])))] += 1
    return c


def _clave(a: dict, b: dict) -> tuple:
    return tuple(sorted((a["Jugador"], b["Jugador"])))


# ============================================================================
#  Deshacer última jornada (snapshot de un nivel)
# ============================================================================

_CLAVES_ESTADO = ("internas", "cruces", "fases_internas", "partidos", "modo_ultimo")


def _guardar_snapshot(historial: dict) -> None:
    """Guarda una foto del estado ANTES de generar la jornada.
    Se llama automáticamente desde siguiente_ronda_completa()."""
    import copy
    historial["_undo"] = {
        k: copy.deepcopy(historial[k]) for k in _CLAVES_ESTADO if k in historial
    }


def revertir_ultima_jornada(historial: dict) -> bool:
    """
    Restaura el historial al estado previo a la ÚLTIMA jornada generada
    (contadores de ronda Y partidos registrados desde entonces).

    Un solo nivel de deshacer: tras revertir, no se puede revertir de nuevo
    hasta generar una nueva jornada. Recuerda guardar_historial() después.

    Returns: True si se revirtió, False si no había nada que revertir.
    """
    snap = historial.pop("_undo", None)
    if snap is None:
        return False
    for k in _CLAVES_ESTADO:
        if k in snap:
            historial[k] = snap[k]
        else:
            historial.pop(k, None)
    return True


def hay_jornada_para_revertir(historial: dict) -> bool:
    """True si existe una jornada que se puede deshacer."""
    return "_undo" in historial


# ============================================================================
#  MODO CLÁSICO: emparejadores auxiliares
# ============================================================================

def _emparejar_grupo(grupo: list[dict], veces) -> list[tuple]:
    """Empareja un grupo PAR entre sí, minimizando repeticiones
    (prefiere pares jugados menos veces). Backtracking con relajación."""
    n = len(grupo)
    if n == 0:
        return []

    def resolver(umbral):
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


def _jornada_clasico(categorias: dict[str, list[dict]], historial: dict) -> list[dict]:
    """
    (MODO CLÁSICO) Jornada: 1 interno + 1 cruzado = 2 partidos por jugador.

    - Todos juegan EXACTAMENTE 2. Nadie descansa.
    - Categoría impar: el ancla (último del ranking) juega 2 internos.
    - Anti-repetición: se priorizan los pares jugados menos veces.
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
            ronda = todas[idx]
            parejas = [(p1, p2) for p1, p2 in ronda if p1 is not None and p2 is not None]
            participa_cruce[nombre] = list(jugadores)
        else:
            ancla = jugadores[-1]
            otros = jugadores[:-1]
            rivales = sorted(
                otros,
                key=lambda j: (veces.get(_clave(ancla, j), 0), j["Ranking"]),
            )[:2]
            resto = [j for j in otros if j["Jugador"] not in {r["Jugador"] for r in rivales}]
            parejas = [(ancla, rivales[0]), (ancla, rivales[1])]
            parejas += _emparejar_grupo(resto, veces)
            participa_cruce[nombre] = otros
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

        parejas_sobrantes = []
        if len(gx) != len(gy):
            mayor, menor = (gx, gy) if len(gx) > len(gy) else (gy, gx)
            d = len(mayor) - len(menor)  # siempre par
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


# ============================================================================
#  MODO FASES: 3 rondas internas por fecha
# ============================================================================

def _jornada_fase(jugadores: list[dict], idx: int, veces, pares_fecha: set) -> tuple[list[tuple], str]:
    """
    Toma PARTIDOS_POR_FECHA rondas consecutivas del round-robin.

    - Fase PAR: rondas limpias → todos con exactamente 3 partidos.
    - Fase IMPAR: cada ronda deja 1 'bye' (3 byes distintos). Los 3 se
      emparejan entre sí: dos completan sus 3 partidos y UNO juega 4.
      El que juega 4 (doble) es SIEMPRE el de peor ranking (mayor número).
    """
    todas = generar_todas_las_rondas_internas(jugadores)
    total = len(todas)
    if total == 0:
        return [], ""

    n_rondas = min(PARTIDOS_POR_FECHA, total)
    parejas: list[tuple] = []
    byes: list[dict] = []
    for r in range(n_rondas):
        for a, b in todas[(idx + r) % total]:
            if a is None:
                byes.append(b)
            elif b is None:
                byes.append(a)
            else:
                parejas.append((a, b))
                pares_fecha.add(_clave(a, b))

    nota = ""
    if len(byes) == 3:
        import itertools
        candidatos = []
        for (i, j) in itertools.combinations(range(3), 2):
            k = 3 - i - j
            for rival in (i, j):
                par1 = _clave(byes[i], byes[j])
                par2 = _clave(byes[k], byes[rival])
                costo = (
                    (par1 in pares_fecha) + (par2 in pares_fecha),
                    veces.get(par1, 0) + veces.get(par2, 0),
                )
                candidatos.append((costo, i, j, k, rival))
        _, i, j, k, rival = min(candidatos)
        parejas.append((byes[i], byes[j]))
        parejas.append((byes[k], byes[rival]))
        pares_fecha.add(_clave(byes[i], byes[j]))
        pares_fecha.add(_clave(byes[k], byes[rival]))
        doble = byes[rival]
        nota = (f"F. impar: {byes[i]['Jugador']}, {byes[j]['Jugador']} y "
                f"{byes[k]['Jugador']} completan con partidos extra; "
                f"{doble['Jugador']} juega 4 esta fecha para calzar la paridad.")
    elif byes:
        for a, b in zip(byes[0::2], byes[1::2]):
            parejas.append((a, b))
            pares_fecha.add(_clave(a, b))

    return parejas, nota


def _jornada_fases(categorias: dict[str, list[dict]], historial: dict) -> list[dict]:
    """
    (MODO FASES) Jornada: 3 partidos por jugador, todos dentro de su fase.

    - Fase PAR: todos juegan EXACTAMENTE 3, rivales distintos (round-robin).
    - Fase IMPAR: todos juegan 3 salvo UNO que juega 4 (paridad).
    Estado en historial["fases_internas"] (separado del modo clásico).
    """
    veces = _contador_pares(historial)
    resultados = []

    for nombre, jugadores in categorias.items():
        if len(jugadores) < 2:
            continue
        total = len(generar_todas_las_rondas_internas(jugadores))
        idx, ciclo = _avanzar_estado_n(historial, "fases_internas", nombre, total, PARTIDOS_POR_FECHA)

        pares_fecha: set = set()
        parejas, nota = _jornada_fase(jugadores, idx, veces, pares_fecha)

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

    return resultados


# ============================================================================
#  Punto de entrada
# ============================================================================

def siguiente_ronda_completa(categorias: dict[str, list[dict]], historial: dict,
                             modo: str = MODO_DEFAULT) -> list[dict]:
    """
    Genera la jornada según el modo:
    - "clasico": 2 partidos por jugador (1 interno + 1 cruce, 4 categorías).
    - "fases":   3 partidos por jugador (todo interno, 3 fases; en fase
                 impar uno juega 4).

    IMPORTANTE: las categorías deben haberse generado con el MISMO modo
    (dividir_en_categorias(..., modo=modo)).

    Antes de generar guarda un snapshot del estado; si la jornada no
    convence, revertir_ultima_jornada(historial) la deshace por completo.
    """
    _guardar_snapshot(historial)
    historial["modo_ultimo"] = modo  # formato con que se generó la última jornada
    if modo == "fases":
        return _jornada_fases(categorias, historial)
    return _jornada_clasico(categorias, historial)


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
