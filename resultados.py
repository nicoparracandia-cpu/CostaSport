"""
resultados.py
-------------
Lógica de resultados y ranking para la escalerilla.

- Registra resultados de partidos en el historial.
- Calcula el ranking acumulado de la temporada.
"""
from __future__ import annotations
from datetime import datetime

# Puntajes
PUNTOS_GANADO = 200
PUNTOS_PERDIDO = 25
PUNTOS_WO_FAVOR = 50
PUNTOS_WO_CONTRA = 0


# ============================================================================
#  Registro de partidos generados
# ============================================================================

def registrar_partidos_generados(historial: dict, resultados_ronda: list[dict]) -> int:
    """
    Agrega los partidos de una ronda al historial con IDs únicos.
    Retorna cuántos partidos nuevos se registraron.
    """
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


# ============================================================================
#  Registro de resultados
# ============================================================================

def _ganador_desde_sets(sets: list[dict], j1: str, j2: str) -> str:
    """Determina el ganador en base a los sets. Lanza ValueError si hay empate."""
    sets_1 = sum(1 for s in sets if s["games_1"] > s["games_2"])
    sets_2 = sum(1 for s in sets if s["games_2"] > s["games_1"])
    if sets_1 > sets_2:
        return j1
    elif sets_2 > sets_1:
        return j2
    else:
        raise ValueError("Empate de sets: no hay ganador claro.")


def registrar_resultado(
    historial: dict,
    partido_id: str,
    tipo: str,                       # "normal" | "wo_j1" | "wo_j2"
    sets: list[dict] | None = None,  # [{"games_1": 6, "games_2": 4}, ...]
    nota_wo: str | None = None,
) -> dict:
    """
    Registra (o sobrescribe) el resultado de un partido.
    Retorna el partido actualizado.
    """
    partido = next((p for p in historial.get("partidos", []) if p["id"] == partido_id), None)
    if partido is None:
        raise ValueError(f"Partido {partido_id} no encontrado")

    j1 = partido["jugador_1"]["Jugador"]
    j2 = partido["jugador_2"]["Jugador"]

    if tipo == "wo_j1":
        partido["resultado"] = {
            "tipo": "wo",
            "ganador": j1,
            "puntos_ganador": PUNTOS_WO_FAVOR,
            "puntos_perdedor": PUNTOS_WO_CONTRA,
            "nota_wo": nota_wo or "",
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    elif tipo == "wo_j2":
        partido["resultado"] = {
            "tipo": "wo",
            "ganador": j2,
            "puntos_ganador": PUNTOS_WO_FAVOR,
            "puntos_perdedor": PUNTOS_WO_CONTRA,
            "nota_wo": nota_wo or "",
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    elif tipo == "normal":
        if not sets:
            raise ValueError("Se requieren los sets para un resultado normal.")
        ganador = _ganador_desde_sets(sets, j1, j2)
        partido["resultado"] = {
            "tipo": "normal",
            "ganador": ganador,
            "sets": sets,
            "puntos_ganador": PUNTOS_GANADO,
            "puntos_perdedor": PUNTOS_PERDIDO,
            "fecha_registro": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        raise ValueError(f"Tipo desconocido: {tipo}")

    return partido


def borrar_resultado(historial: dict, partido_id: str) -> None:
    """Borra el resultado de un partido (lo vuelve pendiente)."""
    partido = next((p for p in historial.get("partidos", []) if p["id"] == partido_id), None)
    if partido is None:
        raise ValueError(f"Partido {partido_id} no encontrado")
    partido["resultado"] = None


# ============================================================================
#  Consultas
# ============================================================================

def partidos_pendientes(historial: dict) -> list[dict]:
    """Lista de partidos sin resultado."""
    return [p for p in historial.get("partidos", []) if p["resultado"] is None]


def partidos_completados(historial: dict) -> list[dict]:
    """Lista de partidos con resultado."""
    return [p for p in historial.get("partidos", []) if p["resultado"] is not None]


# ============================================================================
#  Cálculo de ranking
# ============================================================================

def calcular_ranking(historial: dict, jugadores_base: list[dict]):
    """
    Calcula el ranking acumulado de todos los jugadores.
    Orden de desempate: 1° Puntos · 2° Performance · 3° Ranking inicial
    Retorna un DataFrame ordenado por puntos descendente.
    """
    import pandas as pd

    stats = {}
    for j in jugadores_base:
        nombre = j["Jugador"]
        stats[nombre] = {
            "Jugador": nombre,
            "Ranking inicial": int(j["Ranking"]),
            "Performance": float(j.get("Performance") or j.get("performance") or 0),
            "PJ": 0, "G": 0, "P": 0, "WO+": 0, "WO-": 0,
            "Puntos": 0,
        }

    for partido in historial.get("partidos", []):
        res = partido["resultado"]
        if res is None:
            continue
        j1 = partido["jugador_1"]["Jugador"]
        j2 = partido["jugador_2"]["Jugador"]
        if j1 not in stats or j2 not in stats:
            continue

        ganador = res["ganador"]
        perdedor = j2 if ganador == j1 else j1

        stats[j1]["PJ"] += 1
        stats[j2]["PJ"] += 1

        if res["tipo"] == "wo":
            stats[ganador]["WO+"] += 1
            stats[ganador]["Puntos"] += res["puntos_ganador"]
            stats[perdedor]["WO-"] += 1
            stats[perdedor]["Puntos"] += res["puntos_perdedor"]
        else:
            stats[ganador]["G"] += 1
            stats[ganador]["Puntos"] += res["puntos_ganador"]
            stats[perdedor]["P"] += 1
            stats[perdedor]["Puntos"] += res["puntos_perdedor"]

    df = pd.DataFrame(stats.values())
    df = df.sort_values(
        ["Puntos", "Performance", "Ranking inicial"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    df.insert(0, "Pos.", range(1, len(df) + 1))
    return df


# ============================================================================
#  Formato del marcador para mostrar en UI
# ============================================================================

def formatear_marcador(resultado: dict) -> str:
    """Devuelve un string con el marcador del partido."""
    if resultado is None:
        return "Pendiente"
    if resultado["tipo"] == "wo":
        return f"W.O. a favor de {resultado['ganador']}"
    sets = resultado["sets"]
    return " · ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)
