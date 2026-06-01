"""
db.py — Costa Sport
-------------------
Capa de acceso a Supabase. Reemplaza el historial.json.

Tablas en Supabase:
  - jugadores  (id, nombre, ranking, performance, activo)
  - historial  (id, data)   ← una sola fila con todo el historial serializado
"""
from __future__ import annotations
import json
import streamlit as st
from supabase import create_client


# ============================================================================
#  Conexión (singleton cacheado)
# ============================================================================

@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


# ============================================================================
#  Jugadores
# ============================================================================

def get_jugadores() -> list[dict]:
    """Retorna la lista de jugadores activos ordenada por ranking."""
    sb = get_supabase()
    resp = sb.table("jugadores").select("*").eq("activo", True).order("ranking").execute()
    return resp.data


def get_todos_jugadores() -> list[dict]:
    """Retorna todos los jugadores (activos e inactivos) ordenados por ranking."""
    sb = get_supabase()
    resp = sb.table("jugadores").select("*").order("ranking").execute()
    return resp.data


def actualizar_jugadores_desde_excel(jugadores: list[dict]) -> None:
    """
    Sincroniza la tabla jugadores con el Excel subido (Hoja2).
    Soporta columnas: Ranking, Jugador, Performance (opcional), Puntaje (ignorado).
    """
    sb = get_supabase()
    for j in jugadores:
        data = {
            "nombre": str(j["Jugador"]),
            "ranking": int(j["Ranking"]),
            "activo": True,
        }
        if "Performance" in j and j["Performance"] is not None:
            try:
                data["performance"] = float(j["Performance"])
            except (ValueError, TypeError):
                data["performance"] = 0.0
        sb.table("jugadores").upsert(data, on_conflict="nombre").execute()


def set_jugador_activo(jugador_id: int, activo: bool) -> None:
    """Activa o desactiva un jugador."""
    sb = get_supabase()
    sb.table("jugadores").update({"activo": activo}).eq("id", jugador_id).execute()


# ============================================================================
#  Historial (una sola fila JSON en Supabase)
# ============================================================================

HISTORIAL_ID = 1  # siempre usamos la fila con id=1


def cargar_historial() -> dict:
    """Carga el historial desde Supabase. Retorna {} si no existe."""
    sb = get_supabase()
    resp = sb.table("historial").select("data").eq("id", HISTORIAL_ID).execute()
    if resp.data:
        return json.loads(resp.data[0]["data"])
    return {}


def guardar_historial(historial: dict) -> None:
    """Guarda (upsert) el historial completo en Supabase."""
    sb = get_supabase()
    sb.table("historial").upsert(
        {"id": HISTORIAL_ID, "data": json.dumps(historial, ensure_ascii=False)},
        on_conflict="id"
    ).execute()
