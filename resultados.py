"""
resultados.py v2
-------------
Lógica de resultados y ranking para la escalerilla.
Incluye búsqueda flexible de nombres (tolera tildes y mayúsculas).
"""
from __future__ import annotations
from datetime import datetime

PUNTOS_GANADO = 200
PUNTOS_PERDIDO = 25
PUNTOS_WO_FAVOR = 50
PUNTOS_WO_CONTRA = 0


def registrar_partidos_generados(historial: dict, resultados_ronda: list[dict]) -> int:
    historial.setdefault("partidos", [])
    siguiente_id = len(historial["partidos"]) + 1
    fecha_generado = datetime.now().isoformat(timespec="seconds")

    nuevos = 0
    for res in resultados_ronda:
        for p1, p2 in res["parejas"]:
            historial["partidos"].append({
                "id": f"p_{siguiente_id:04d}",
                "fecha_generado": fecha_generado,
                "tipo": res["tipo"],
                "bloque": res["bloque"],
                "ronda_bloque": res["ronda"],
                "ciclo_bloque": res["ciclo"],
                "jugador_1": {
                    "Ranking": int(p1["Ranking"]),
                    "Jugador": str(p1["Jugador"]),
                },
                "jugador_2": {
                    "Ranking": int(p2["Ranking"]),
                    "Jugador": str(p2["Jugador"]),
                },
                "resultado": None,
            })
            siguiente_id += 1
            nuevos += 1
    return nuevos


def _ganador_desde_sets(sets: list[dict], j1: str, j2: str) -> str:
    sets_1 = sum(1 for s in sets if s["games_1"] > s["games_2"])
    sets_2 = sum(1 for s in sets if s["games_2"] > s["games_1"])
    if sets_1 > sets_2:
        return j1
    elif sets_2 > sets_1:
        return j2
    else:
        raise ValueError("Empate de sets: no hay ganador claro.")


def validar_sets(sets: list[dict]) -> list[str]:
    errores = []
    for i, s in enumerate(sets):
        g1, g2 = s["games_1"], s["games_2"]
        num_set = i + 1
        if num_set < 3:
            if g1 == g2:
                errores.append(f"Set {num_set}: no puede terminar empatado ({g1}-{g2}).")
            elif max(g1, g2) < 6:
                errores.append(f"Set {num_set}: el ganador debe llegar al menos a 6 games ({g1}-{g2}).")
            elif max(g1, g2) == 7 and min(g1, g2) not in (5, 6):
                errores.append(f"Set {num_set}: marcador inválido ({g1}-{g2}). 7 games solo con 7-5 o 7-6.")
            elif max(g1, g2) > 7:
                errores.append(f"Set {num_set}: máximo 7 games en sets normales ({g1}-{g2}).")
        else:
            if g1 == g2:
                errores.append(f"Set 3 (tie-break): no puede terminar empatado ({g1}-{g2}).")
            elif max(g1, g2) < 10:
                errores.append(f"Set 3 (tie-break): el ganador debe llegar al menos a 10 puntos ({g1}-{g2}).")
            elif abs(g1 - g2) < 2:
                errores.append(f"Set 3 (tie-break): se necesita diferencia de 2 puntos ({g1}-{g2}).")
    return errores


def registrar_resultado(
    historial: dict,
    partido_id: str,
    tipo: str,
    sets: list[dict] | None = None,
    nota_wo: str | None = None,
) -> dict:
    partido = next((p for p in historial.get("partidos", []) if p["id"] == partido_id), None)
    if partido is None:
        raise ValueError(f"Partido {partido_id} no encontrado")

    j1 = partido["jugador_1"]["Jugador"]
    j2 = partido["jugador_2"]["Jugador"]

    if tipo == "wo_j1":
        partido["resultado"] = {
            "tipo": "wo", "ganador": j1,
            "puntos_ganador": PUNTOS_WO_FAVOR, "puntos_perdedor": PUNTOS_WO_CONTRA,
            "nota_wo": nota_wo or "",
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    elif tipo == "wo_j2":
        partido["resultado"] = {
            "tipo": "wo", "ganador": j2,
            "puntos_ganador": PUNTOS_WO_FAVOR, "puntos_perdedor": PUNTOS_WO_CONTRA,
            "nota_wo": nota_wo or "",
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    elif tipo == "normal":
        if not sets:
            raise ValueError("Se requieren los sets para un resultado normal.")
        ganador = _ganador_desde_sets(sets, j1, j2)
        partido["resultado"] = {
            "tipo": "normal", "ganador": ganador, "sets": sets,
            "puntos_ganador": PUNTOS_GANADO, "puntos_perdedor": PUNTOS_PERDIDO,
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        raise ValueError(f"Tipo desconocido: {tipo}")

    return partido


def borrar_resultado(historial: dict, partido_id: str) -> None:
    partido = next((p for p in historial.get("partidos", []) if p["id"] == partido_id), None)
    if partido is None:
        raise ValueError(f"Partido {partido_id} no encontrado")
    partido["resultado"] = None


def registrar_no_jugado(historial: dict, partido_id: str, justificacion: str) -> dict:
    JUSTIFICACIONES_VALIDAS = ["Sin acuerdo", "Por enfermedad", "Por lesión"]
    if justificacion not in JUSTIFICACIONES_VALIDAS:
        raise ValueError(f"Justificación inválida. Opciones: {JUSTIFICACIONES_VALIDAS}")
    partido = next((p for p in historial.get("partidos", []) if p["id"] == partido_id), None)
    if partido is None:
        raise ValueError(f"Partido {partido_id} no encontrado")
    partido["resultado"] = {
        "tipo": "no_jugado", "justificacion": justificacion,
        "fecha_registro": datetime.now().isoformat(timespec="seconds"),
    }
    return partido


def inasistencias_consecutivas(historial: dict, nombre_jugador: str) -> int:
    partidos_jugador = [
        p for p in historial.get("partidos", [])
        if p["jugador_1"]["Jugador"] == nombre_jugador
        or p["jugador_2"]["Jugador"] == nombre_jugador
    ]
    con_resultado = [p for p in partidos_jugador if p["resultado"] is not None]
    if not con_resultado:
        return 0
    consecutivas = 0
    for p in reversed(con_resultado):
        if p["resultado"]["tipo"] == "no_jugado":
            consecutivas += 1
        else:
            break
    return consecutivas


def jugadores_a_desactivar(historial: dict, limite: int = 2) -> list[str]:
    nombres = set()
    for p in historial.get("partidos", []):
        nombres.add(p["jugador_1"]["Jugador"])
        nombres.add(p["jugador_2"]["Jugador"])
    return [n for n in nombres if inasistencias_consecutivas(historial, n) >= limite]


def partidos_pendientes(historial: dict) -> list[dict]:
    return [p for p in historial.get("partidos", []) if p["resultado"] is None]


def partidos_completados(historial: dict) -> list[dict]:
    return [p for p in historial.get("partidos", []) if p["resultado"] is not None]


def calcular_ranking(historial: dict, jugadores_base: list[dict]):
    """
    Puntos totales = puntos_base + puntos nuevos.
    Desempate: 1° Puntos · 2° Performance · 3° Ranking inicial.
    Búsqueda flexible de nombres (tolera tildes y mayúsculas).
    """
    import pandas as pd
    import unicodedata

    def _norm(s):
        return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

    stats = {}
    nombre_map = {}

    for j in jugadores_base:
        nombre = j["Jugador"]
        puntos_base = int(j.get("puntos_base") or j.get("Puntaje") or 0)
        performance = float(j.get("performance") or j.get("Performance") or 0)
        stats[nombre] = {
            "Jugador": nombre,
            "Ranking inicial": int(j["Ranking"]),
            "Performance": performance,
            "PJ": 0, "G": 0, "P": 0, "WO+": 0, "WO-": 0,
            "Pts base": puntos_base,
            "Pts nuevos": 0,
            "Puntos": puntos_base,
        }
        nombre_map[_norm(nombre)] = nombre

    def _buscar(nombre_raw):
        if nombre_raw in stats:
            return nombre_raw
        return nombre_map.get(_norm(nombre_raw))

    for partido in historial.get("partidos", []):
        res = partido["resultado"]
        if res is None:
            continue
        if res["tipo"] == "no_jugado":
            continue
        j1 = _buscar(partido["jugador_1"]["Jugador"])
        j2 = _buscar(partido["jugador_2"]["Jugador"])
        if j1 is None or j2 is None:
            continue

        ganador = _buscar(res["ganador"]) or res["ganador"]
        perdedor = j2 if ganador == j1 else j1

        stats[j1]["PJ"] += 1
        stats[j2]["PJ"] += 1

        if res["tipo"] == "wo":
            stats[ganador]["WO+"] += 1
            stats[ganador]["Puntos"] += res["puntos_ganador"]
            stats[ganador]["Pts nuevos"] += res["puntos_ganador"]
            stats[perdedor]["WO-"] += 1
            stats[perdedor]["Puntos"] += res["puntos_perdedor"]
            stats[perdedor]["Pts nuevos"] += res["puntos_perdedor"]
        else:
            stats[ganador]["G"] += 1
            stats[ganador]["Puntos"] += res["puntos_ganador"]
            stats[ganador]["Pts nuevos"] += res["puntos_ganador"]
            stats[perdedor]["P"] += 1
            stats[perdedor]["Puntos"] += res["puntos_perdedor"]
            stats[perdedor]["Pts nuevos"] += res["puntos_perdedor"]

    df = pd.DataFrame(stats.values())
    df = df.sort_values(
        ["Puntos", "Performance", "Ranking inicial"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    df.insert(0, "Pos.", range(1, len(df) + 1))
    return df


def formatear_marcador(resultado: dict) -> str:
    if resultado is None:
        return "Pendiente"
    if resultado["tipo"] == "wo":
        return f"W.O. a favor de {resultado['ganador']} — {resultado.get('nota_wo', '')}"
    if resultado["tipo"] == "no_jugado":
        return f"No jugado — {resultado.get('justificacion', '')}"
    sets = resultado["sets"]
    return " · ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)


def deshacer_ultima_jornada(historial: dict) -> tuple[bool, str]:
    """
    Revierte la última jornada generada (sorteo), en cualquier modo
    (clásico o fases).

    Seguridad: NO permite deshacer si algún partido de esa jornada ya
    tiene resultado registrado (hay que borrar esos resultados primero).

    Mecanismo: usa el snapshot que pairing.py guarda automáticamente al
    generar (restaura contadores y partidos de forma exacta). Si el
    historial es antiguo y no tiene snapshot, cae a la reversión manual
    (solo válida para jornadas del modo clásico).

    Retorna (exito, mensaje).
    """
    partidos = historial.get("partidos", [])
    if not partidos:
        return False, "No hay partidos para deshacer."

    ultima_fecha = max(p["fecha_generado"] for p in partidos)
    de_la_jornada = [p for p in partidos if p["fecha_generado"] == ultima_fecha]

    con_resultado = [p for p in de_la_jornada if p.get("resultado") is not None]
    if con_resultado:
        return False, (f"No se puede deshacer: {len(con_resultado)} partido(s) de la "
                       f"última jornada ya tienen resultado registrado. "
                       f"Borra esos resultados primero.")

    # --- Vía preferida: snapshot guardado por pairing al generar ---
    from pairing import revertir_ultima_jornada
    n_antes = len(partidos)
    if revertir_ultima_jornada(historial):
        eliminados = n_antes - len(historial.get("partidos", []))
        return True, (f"Se deshizo la última jornada: "
                      f"{eliminados} partidos eliminados.")

    # --- Fallback (historiales antiguos sin snapshot, modo clásico) ---
    return _deshacer_manual_clasico(historial, de_la_jornada, ultima_fecha)


def _deshacer_manual_clasico(historial: dict, de_la_jornada: list[dict],
                             ultima_fecha: str) -> tuple[bool, str]:
    """Reversión manual paso-a-paso (lógica original). Solo sabe retroceder
    contadores del modo clásico ('internas'/'cruces', avance de a 1)."""
    if any(p["fecha_generado"] == ultima_fecha and p["tipo"] == "Interno"
           and historial.get("fases_internas", {}).get(p["bloque"]) for p in de_la_jornada):
        return False, ("No se pudo deshacer: la jornada parece del modo fases "
                       "pero no hay snapshot disponible.")

    partidos = historial.get("partidos", [])

    # 1) Retroceder contadores de ronda por bloque
    bloques_vistos = set()
    for p in de_la_jornada:
        seccion = "internas" if p["tipo"] == "Interno" else "cruces"
        bloque = p["bloque"]
        if (seccion, bloque) in bloques_vistos:
            continue
        bloques_vistos.add((seccion, bloque))
        estado = historial.get(seccion, {}).get(bloque)
        if not estado:
            continue
        ronda = p["ronda_bloque"]   # ronda que se generó (1-based)
        ciclo = p["ciclo_bloque"]
        total = estado.get("total_rondas", ronda)
        if ronda <= 1 and ciclo > 1:
            historial[seccion][bloque] = {"ronda_actual": total, "ciclo": ciclo - 1,
                                          "total_rondas": total}
        else:
            historial[seccion][bloque] = {"ronda_actual": ronda - 1, "ciclo": ciclo,
                                          "total_rondas": total}

    # 2) Quitar pares del registro anti-repetición (formato antiguo)
    registro = historial.get("pares_cruce", {})
    for p in de_la_jornada:
        if p["tipo"] != "Cruzado":
            continue
        par = sorted((p["jugador_1"]["Jugador"], p["jugador_2"]["Jugador"]))
        lista = registro.get(p["bloque"], [])
        if par in lista:
            lista.remove(par)

    # 3) Eliminar los partidos de la jornada
    historial["partidos"] = [p for p in partidos if p["fecha_generado"] != ultima_fecha]

    return True, f"Se deshizo la última jornada: {len(de_la_jornada)} partidos eliminados."
