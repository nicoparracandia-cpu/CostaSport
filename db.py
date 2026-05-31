"""
db.py — Costa Sport
-------------------
Capa de acceso a Supabase. Reemplaza el historial.json.

Tablas en Supabase:
  - jugadores  (id, nombre, ranking, activo)
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
    """Retorna la lista de jugadores ordenada por ranking."""
    sb = get_supabase()
    resp = sb.table("jugadores").select("*").eq("activo", True).order("ranking").execute()
    return resp.data


def agregar_jugador(nombre: str, ranking: int) -> None:
    sb = get_supabase()
    sb.table("jugadores").insert({"nombre": nombre, "ranking": ranking, "activo": True}).execute()


def actualizar_jugadores_desde_excel(jugadores: list[dict]) -> None:
    """
    Sincroniza la tabla jugadores con el Excel subido.
    Inserta o actualiza por nombre.
    """
    sb = get_supabase()
    for j in jugadores:
        sb.table("jugadores").upsert(
            {"nombre": j["Jugador"], "ranking": int(j["Ranking"]), "activo": True},
            on_conflict="nombre"
        ).execute()


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
