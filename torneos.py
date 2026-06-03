"""
torneos.py — Costa Sport
------------------------
Lógica de torneos: singles y dobles.
Formatos: eliminación directa, round robin, grupos + eliminación.
"""
from __future__ import annotations
import json
from datetime import datetime


# ============================================================================
#  DB helpers para torneos
# ============================================================================

def get_torneo_activo(sb) -> dict | None:
    resp = sb.table("torneos").select("*").eq("estado", "activo").execute()
    return resp.data[0] if resp.data else None


def get_todos_torneos(sb) -> list[dict]:
    resp = sb.table("torneos").select("*").order("created_at", desc=True).execute()
    return resp.data


def crear_torneo(sb, nombre: str, tipo: str, formato: str, config: dict) -> dict:
    resp = sb.table("torneos").insert({
        "nombre": nombre,
        "tipo": tipo,
        "formato": formato,
        "estado": "activo",
        "config": config,
    }).execute()
    return resp.data[0]


def finalizar_torneo(sb, torneo_id: int):
    sb.table("torneos").update({"estado": "finalizado"}).eq("id", torneo_id).execute()


def eliminar_torneo(sb, torneo_id: int):
    """Elimina el torneo y todos sus datos (partidos y participantes)."""
    sb.table("torneo_partidos").delete().eq("torneo_id", torneo_id).execute()
    sb.table("torneo_participantes").delete().eq("torneo_id", torneo_id).execute()
    sb.table("torneos").delete().eq("id", torneo_id).execute()


def calcular_puntos_torneo(partidos: list[dict], participantes: list[dict],
                            config: dict, tipo: str = "singles") -> dict[str, int]:
    """
    Calcula cuántos puntos gana cada jugador en el torneo.
    Retorna dict {nombre_jugador: puntos_ganados}.
    """
    pts_config = config.get("puntos_por_victoria", {})
    puntos = {}

    # Orden jerárquico de fases para fallback
    jerarquia_fases = [
        "final", "semifinal", "cuartos", "octavos",
        "dieciseisavos", "treintaidosavos", "sesentaicuatroavos",
        "ronda_3", "ronda_2", "ronda_1", "grupos"
    ]

    def pts_para_fase(fase: str) -> int:
        """Busca puntos para la fase, con fallback a fases anteriores."""
        if fase in pts_config:
            return int(pts_config[fase])
        # Si no está definida, usar la fase inmediatamente anterior en jerarquía
        try:
            idx = jerarquia_fases.index(fase)
            for i in range(idx + 1, len(jerarquia_fases)):
                if jerarquia_fases[i] in pts_config:
                    return int(pts_config[jerarquia_fases[i]])
        except ValueError:
            pass
        return int(pts_config.get("ronda_1", 0))

    for partido in partidos:
        if not partido.get("ganador_id"):
            continue
        gan = partido.get("ganador") or {}
        nombre_gan = gan.get("jugador1_nombre", "")
        nombre_gan2 = gan.get("jugador2_nombre", "") if tipo == "dobles" else ""
        fase = partido.get("fase", "ronda_1")
        pts = pts_para_fase(fase)
        if nombre_gan:
            puntos[nombre_gan] = puntos.get(nombre_gan, 0) + pts
        if tipo == "dobles" and nombre_gan2:
            puntos[nombre_gan2] = puntos.get(nombre_gan2, 0) + pts

    return puntos


def aplicar_puntos_al_ranking(sb, puntos: dict[str, int]) -> tuple[int, list[str]]:
    """
    Suma los puntos del torneo a puntos_base de cada jugador en la escalerilla.
    Retorna (actualizados, no_encontrados).
    """
    actualizados = 0
    no_encontrados = []

    for nombre, pts in puntos.items():
        resp = sb.table("jugadores").select("id, puntos_base, nombre").execute()
        jug = next((j for j in resp.data if j["nombre"].lower() == nombre.lower()), None)
        if jug:
            nueva_base = (jug.get("puntos_base") or 0) + pts
            sb.table("jugadores").update({"puntos_base": nueva_base}).eq("id", jug["id"]).execute()
            actualizados += 1
        else:
            no_encontrados.append(nombre)

    return actualizados, no_encontrados


def get_participantes(sb, torneo_id: int) -> list[dict]:
    resp = sb.table("torneo_participantes").select("*").eq("torneo_id", torneo_id).order("seed").execute()
    return resp.data


def agregar_participante(sb, torneo_id: int, jugador1: str, jugador2: str = None, seed: int = 0) -> dict:
    resp = sb.table("torneo_participantes").insert({
        "torneo_id": torneo_id,
        "jugador1_nombre": jugador1,
        "jugador2_nombre": jugador2,
        "seed": seed,
        "grupo": None,
    }).execute()
    return resp.data[0]


def eliminar_participante(sb, participante_id: int):
    sb.table("torneo_participantes").delete().eq("id", participante_id).execute()


def actualizar_seed(sb, participante_id: int, seed: int):
    sb.table("torneo_participantes").update({"seed": seed}).eq("id", participante_id).execute()


def asignar_grupo(sb, participante_id: int, grupo: str):
    sb.table("torneo_participantes").update({"grupo": grupo}).eq("id", participante_id).execute()


def get_partidos_torneo(sb, torneo_id: int) -> list[dict]:
    resp = sb.table("torneo_partidos").select("*, participante1:torneo_participantes!torneo_partidos_participante1_id_fkey(*), participante2:torneo_participantes!torneo_partidos_participante2_id_fkey(*), ganador:torneo_participantes!torneo_partidos_ganador_id_fkey(*)").eq("torneo_id", torneo_id).order("orden").execute()
    return resp.data


def get_partidos_fase(sb, torneo_id: int, fase: str) -> list[dict]:
    resp = sb.table("torneo_partidos").select("*, participante1:torneo_participantes!torneo_partidos_participante1_id_fkey(*), participante2:torneo_participantes!torneo_partidos_participante2_id_fkey(*)").eq("torneo_id", torneo_id).eq("fase", fase).order("orden").execute()
    return resp.data


def crear_partido(sb, torneo_id: int, fase: str, p1_id: int, p2_id: int, orden: int, grupo: str = None) -> dict:
    resp = sb.table("torneo_partidos").insert({
        "torneo_id": torneo_id,
        "fase": fase,
        "grupo": grupo,
        "participante1_id": p1_id,
        "participante2_id": p2_id,
        "ganador_id": None,
        "resultado": None,
        "orden": orden,
    }).execute()
    return resp.data[0]


def registrar_resultado_torneo(sb, partido_id: int, ganador_id: int, sets: list[dict]) -> None:
    sb.table("torneo_partidos").update({
        "ganador_id": ganador_id,
        "resultado": {"sets": sets},
    }).eq("id", partido_id).execute()


def borrar_resultado_torneo(sb, partido_id: int) -> None:
    sb.table("torneo_partidos").update({
        "ganador_id": None,
        "resultado": None,
    }).eq("id", partido_id).execute()


# ============================================================================
#  Generación de brackets y llaves
# ============================================================================

def nombre_participante(p: dict, tipo: str = "singles") -> str:
    if not p:
        return "BYE"
    if tipo == "dobles" and p.get("jugador2_nombre"):
        return f"{p['jugador1_nombre']} / {p['jugador2_nombre']}"
    return p["jugador1_nombre"]


def generar_bracket_eliminacion(sb, torneo_id: int, participantes: list[dict], tipo: str) -> None:
    """
    Genera bracket de eliminación directa.
    Usa el campo 'seed' como posición en el bracket (ya fue asignado por aplicar_sorteo_supabase).
    Si los seeds son posiciones del sorteo (valores altos), los usa directamente.
    Si son seeds de cabeza de serie (valores bajos, 1-8), aplica sorteo ATP.
    """
    import math
    from bracket import hacer_sorteo

    n = len(participantes)
    size = 2 ** math.ceil(math.log2(n)) if n > 1 else 2

    # Verificar si ya se hizo el sorteo (seeds son posiciones 1..size)
    seeds = [p.get("seed") or 0 for p in participantes]
    max_seed = max(seeds) if seeds else 0

    if max_seed >= n:
        # Seeds son posiciones del bracket (ya sorteado) — usar directamente
        bracket = [None] * size
        for p in participantes:
            pos = (p.get("seed") or 1) - 1
            if 0 <= pos < size:
                bracket[pos] = p
        # Llenar posiciones vacías con participantes sin seed
        sin_pos = [p for p in participantes if not p.get("seed") or p.get("seed") == 0]
        for i in range(size):
            if bracket[i] is None and sin_pos:
                bracket[i] = sin_pos.pop(0)
    else:
        # No se hizo sorteo — aplicar sorteo ATP automáticamente
        bracket = hacer_sorteo(participantes, "eliminacion")

    # Crear partidos de primera ronda
    fase = _nombre_fase(size)
    for i in range(0, size, 2):
        p1 = bracket[i]
        p2 = bracket[i + 1] if i + 1 < size else None
        if p1 is None and p2 is None:
            continue
        if p1 is None or p2 is None:
            continue
        crear_partido(sb, torneo_id, fase, p1["id"], p2["id"], orden=i // 2 + 1)


def _nombre_fase(size: int) -> str:
    nombres = {
        2: "final", 4: "semifinal", 8: "cuartos",
        16: "octavos", 32: "dieciseisavos",
        64: "treintaidosavos", 128: "sesentaicuatroavos",
    }
    return nombres.get(size, f"ronda_{size}")


def generar_round_robin(sb, torneo_id: int, participantes: list[dict]) -> None:
    """Genera todos los partidos de round robin."""
    ps = list(participantes)
    if len(ps) % 2 == 1:
        ps.append(None)  # BYE
    n = len(ps)
    fijo = ps[0]
    rotantes = ps[1:]
    orden = 1
    for ronda in range(n - 1):
        emparejados = [(fijo, rotantes[0])]
        for i in range(1, n // 2):
            emparejados.append((rotantes[i], rotantes[-(i)]))
        for p1, p2 in emparejados:
            if p1 and p2:
                crear_partido(sb, torneo_id, f"ronda_{ronda+1}", p1["id"], p2["id"], orden=orden)
                orden += 1
        rotantes = [rotantes[-1]] + rotantes[:-1]


def generar_grupos(sb, torneo_id: int, participantes: list[dict], n_grupos: int) -> None:
    """Divide en grupos y genera partidos de round robin por grupo."""
    import math
    seeded = sorted(participantes, key=lambda x: x.get("seed") or 999)
    # Distribuir en serpentina (A,B,C,D,D,C,B,A...)
    letras = [chr(65 + i) for i in range(n_grupos)]
    grupos: dict[str, list] = {l: [] for l in letras}
    direccion = 1
    idx = 0
    for p in seeded:
        grupos[letras[idx]]["append" if isinstance(grupos[letras[idx]], list) else "append"](p) if False else grupos[letras[idx]].append(p)
        asignar_grupo(sb, p["id"], letras[idx])
        idx += direccion
        if idx >= n_grupos:
            idx = n_grupos - 1
            direccion = -1
        elif idx < 0:
            idx = 0
            direccion = 1

    # Generar round robin por grupo
    orden = 1
    for letra, miembros in grupos.items():
        ps = list(miembros)
        if len(ps) % 2 == 1:
            ps.append(None)
        n = len(ps)
        fijo = ps[0]
        rotantes = ps[1:]
        for ronda in range(n - 1):
            emparejados = [(fijo, rotantes[0])]
            for i in range(1, n // 2):
                emparejados.append((rotantes[i], rotantes[-i]))
            for p1, p2 in emparejados:
                if p1 and p2:
                    crear_partido(sb, torneo_id, "grupos", p1["id"], p2["id"], orden=orden, grupo=letra)
                    orden += 1
            rotantes = [rotantes[-1]] + rotantes[:-1]


# ============================================================================
#  Clasificación y stats
# ============================================================================

def calcular_tabla_grupo(partidos: list[dict], grupo: str, tipo: str = "singles") -> list[dict]:
    """Calcula la tabla de posiciones de un grupo."""
    stats = {}
    for p in partidos:
        if p.get("grupo") != grupo:
            continue
        p1 = p.get("participante1") or {}
        p2 = p.get("participante2") or {}
        n1 = nombre_participante(p1, tipo)
        n2 = nombre_participante(p2, tipo)
        for n in [n1, n2]:
            if n not in stats and n != "BYE":
                stats[n] = {"PJ": 0, "G": 0, "P": 0, "Sets G": 0, "Sets P": 0, "Pts": 0}
        if not p.get("ganador_id"):
            continue
        gan = p.get("ganador") or {}
        gan_nombre = nombre_participante(gan, tipo)
        per_nombre = n2 if gan_nombre == n1 else n1
        sets = (p.get("resultado") or {}).get("sets", [])
        sets_g = sum(1 for s in sets if s["games_1"] > s["games_2"]) if gan_nombre == n1 else sum(1 for s in sets if s["games_2"] > s["games_1"])
        sets_p = len(sets) - sets_g
        if gan_nombre in stats:
            stats[gan_nombre]["PJ"] += 1
            stats[gan_nombre]["G"] += 1
            stats[gan_nombre]["Sets G"] += sets_g
            stats[gan_nombre]["Sets P"] += sets_p
            stats[gan_nombre]["Pts"] += 2
        if per_nombre in stats:
            stats[per_nombre]["PJ"] += 1
            stats[per_nombre]["P"] += 1
            stats[per_nombre]["Sets G"] += sets_p
            stats[per_nombre]["Sets P"] += sets_g
            stats[per_nombre]["Pts"] += 1

    tabla = [{"Jugador": n, **s} for n, s in stats.items()]
    tabla.sort(key=lambda x: (-x["Pts"], -x["G"], -(x["Sets G"] - x["Sets P"])))
    for i, row in enumerate(tabla):
        row["Pos."] = i + 1
    return tabla


def calcular_puntos_ranking(config: dict, posicion: int) -> int:
    """Retorna puntos de ranking según posición y configuración del torneo."""
    puntos_config = config.get("puntos_ranking", {})
    return int(puntos_config.get(str(posicion), 0))
