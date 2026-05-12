"""
app.py — Streamlit app para emparejamiento de escalerilla por categorías.
"""
from __future__ import annotations
import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from pairing import (
    dividir_en_categorias,
    siguiente_ronda_completa,
    historial_a_json,
    resultados_a_dataframe,
)

st.set_page_config(
    page_title="Emparejador Escalerilla",
    page_icon="🎾",
    layout="wide",
)

st.title("🎾 Emparejador Escalerilla")
st.caption("Categorías A/B/C/D · 1 partido interno + 1 cruzado por jugador · sin parejas repetidas.")

# --- Estado de sesión ---
if "historial" not in st.session_state:
    st.session_state.historial = {}
if "ultima_ronda" not in st.session_state:
    st.session_state.ultima_ronda = None

# --- Sidebar ---
with st.sidebar:
    st.header("📥 Entradas")
    archivo_excel = st.file_uploader(
        "Lista de jugadores (Excel)",
        type=["xlsx", "xls"],
        help="Columnas requeridas: 'Ranking' y 'Jugador'.",
    )

    n_categorias = st.number_input(
        "Número de categorías",
        min_value=2, max_value=8, value=4, step=2,
        help="Debe ser par para que los cruces funcionen (A-B, C-D, ...).",
    )

    st.divider()
    st.subheader("Historial previo (opcional)")
    archivo_historial = st.file_uploader("historial.json", type=["json"])
    if archivo_historial is not None:
        try:
            historial_cargado = json.loads(archivo_historial.read().decode("utf-8"))
            if "internas" in historial_cargado or "cruces" in historial_cargado:
                st.session_state.historial = historial_cargado
                st.success("Historial cargado ✅")
            else:
                st.warning("Historial con formato antiguo, se ignora.")
        except Exception as e:
            st.error(f"Error al leer historial: {e}")

    st.divider()
    if st.button("🔄 Reiniciar historial", use_container_width=True):
        st.session_state.historial = {}
        st.session_state.ultima_ronda = None
        st.success("Historial reiniciado.")

# --- Cuerpo ---
if archivo_excel is None:
    st.info("👈 Sube tu Excel en la barra lateral para empezar.")
    st.markdown("""
    ### 📋 Formato esperado del Excel
    | Ranking | Jugador        |
    |---------|----------------|
    | 1       | Diego Beas     |
    | 2       | Jaime Hussein  |
    | ...     | ...            |

    ### 🎯 Cómo funciona la escalerilla
    - Los jugadores se dividen en **N categorías** (default 4) según ranking.
    - Cada ronda, cada jugador tiene:
        - **1 partido interno** vs alguien de su misma categoría
        - **1 partido cruzado** vs alguien de la categoría adyacente (A↔B, C↔D, ...)
    - No se repiten parejas hasta completar el ciclo.
    """)
    st.stop()

try:
    df = pd.read_excel(archivo_excel)
except Exception as e:
    st.error(f"No se pudo leer el Excel: {e}")
    st.stop()

if "Ranking" not in df.columns or "Jugador" not in df.columns:
    st.error(f"Columnas requeridas: 'Ranking' y 'Jugador'. Encontradas: {list(df.columns)}")
    st.stop()

jugadores = df.to_dict("records")
categorias = dividir_en_categorias(jugadores, n_categorias=int(n_categorias))

# --- Resumen de categorías ---
st.subheader("👥 Categorías detectadas")
cols = st.columns(len(categorias))
for col, (nombre, lista) in zip(cols, categorias.items()):
    with col:
        estado_int = st.session_state.historial.get("internas", {}).get(nombre, {})
        ronda_int = estado_int.get("ronda_actual", 0)
        ciclo_int = estado_int.get("ciclo", 1)
        st.metric(
            label=f"Categoría {nombre} · {len(lista)} jug.",
            value=f"Ronda {ronda_int}",
            delta=f"Ciclo {ciclo_int} · #{lista[0]['Ranking']}–#{lista[-1]['Ranking']}",
        )

with st.expander("Ver listado completo por categoría"):
    for nombre, lista in categorias.items():
        st.markdown(f"**Categoría {nombre}** ({len(lista)} jugadores)")
        st.dataframe(pd.DataFrame(lista)[["Ranking", "Jugador"]], hide_index=True, use_container_width=True)

st.divider()

# --- Botón ---
col_gen, col_info = st.columns([1, 3])
with col_gen:
    if st.button("🎯 Generar siguiente ronda", type="primary", use_container_width=True):
        resultados = siguiente_ronda_completa(categorias, st.session_state.historial)
        st.session_state.ultima_ronda = resultados

with col_info:
    st.caption("Cada ronda incluye partidos internos + cruzados para todas las categorías.")

# --- Resultados ---
if st.session_state.ultima_ronda:
    st.subheader("🎯 Última ronda generada")
    resultados = st.session_state.ultima_ronda
    df_ronda = resultados_a_dataframe(resultados)

    # Métricas
    total_partidos = len(df_ronda[df_ronda["Jugador 2"] != "DESCANSA"])
    total_descansos = len(df_ronda[df_ronda["Jugador 2"] == "DESCANSA"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total partidos", total_partidos)
    c2.metric("Partidos internos", len(df_ronda[(df_ronda["Tipo"] == "Interno") & (df_ronda["Jugador 2"] != "DESCANSA")]))
    c3.metric("Partidos cruzados", len(df_ronda[df_ronda["Tipo"] == "Cruzado"]))

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtro_tipo = st.multiselect(
            "Filtrar por tipo",
            options=sorted(df_ronda["Tipo"].unique()),
            default=sorted(df_ronda["Tipo"].unique()),
        )
    with col_f2:
        filtro_bloque = st.multiselect(
            "Filtrar por bloque",
            options=sorted(df_ronda["Bloque"].unique()),
            default=sorted(df_ronda["Bloque"].unique()),
        )

    df_filtrado = df_ronda[df_ronda["Tipo"].isin(filtro_tipo) & df_ronda["Bloque"].isin(filtro_bloque)]
    st.dataframe(df_filtrado, hide_index=True, use_container_width=True)

    if total_descansos > 0:
        st.caption(f"💤 {total_descansos} jugador(es) descansa(n) internamente esta ronda (categorías con número impar).")

    st.divider()

    # --- Descargas ---
    st.subheader("📤 Descargas")
    col1, col2 = st.columns(2)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    with col1:
        st.download_button(
            label="📄 Descargar historial.json",
            data=historial_a_json(st.session_state.historial),
            file_name=f"historial_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
            help="Súbelo la próxima vez para continuar desde aquí.",
        )

    with col2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_ronda.to_excel(writer, index=False, sheet_name="Ronda")
        buffer.seek(0)
        st.download_button(
            label="📊 Descargar ronda en Excel",
            data=buffer,
            file_name=f"ronda_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
