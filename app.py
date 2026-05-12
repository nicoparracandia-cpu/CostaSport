"""
app.py — Streamlit app para emparejamiento de escalerilla por categorías.
Incluye 3 pestañas: Generar Ronda, Cargar Resultados, Ranking.
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
from resultados import (
    registrar_partidos_generados,
    registrar_resultado,
    borrar_resultado,
    partidos_pendientes,
    partidos_completados,
    calcular_ranking,
    formatear_marcador,
    PUNTOS_GANADO, PUNTOS_PERDIDO, PUNTOS_WO_FAVOR,
)

# ============================================================================
#  Configuración
# ============================================================================
st.set_page_config(
    page_title="Emparejador Escalerilla",
    page_icon="🎾",
    layout="wide",
)

st.title("🎾 Emparejador Escalerilla")
st.caption(
    f"Categorías A/B/C/D · 1 interno + 1 cruzado por jugador · "
    f"Ganado: {PUNTOS_GANADO} · Perdido: {PUNTOS_PERDIDO} · WO: {PUNTOS_WO_FAVOR}"
)

# ============================================================================
#  Estado de sesión
# ============================================================================
if "historial" not in st.session_state:
    st.session_state.historial = {}
if "ultima_ronda" not in st.session_state:
    st.session_state.ultima_ronda = None

# ============================================================================
#  Sidebar
# ============================================================================
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
    )

    st.divider()
    st.subheader("Historial previo")
    archivo_historial = st.file_uploader("historial.json", type=["json"])
    if archivo_historial is not None:
        try:
            historial_cargado = json.loads(archivo_historial.read().decode("utf-8"))
            if "internas" in historial_cargado or "cruces" in historial_cargado or "partidos" in historial_cargado:
                st.session_state.historial = historial_cargado
                st.success(
                    f"Historial cargado ✅\n"
                    f"({len(historial_cargado.get('partidos', []))} partidos)"
                )
            else:
                st.warning("Historial con formato antiguo, se ignora.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    if st.session_state.historial:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label="💾 Descargar historial.json",
            data=historial_a_json(st.session_state.historial),
            file_name=f"historial_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
            help="Descárgalo y guárdalo para no perder el progreso.",
        )

    st.divider()
    if st.button("🔄 Reiniciar todo", use_container_width=True):
        st.session_state.historial = {}
        st.session_state.ultima_ronda = None
        st.success("Historial reiniciado.")
        st.rerun()

# ============================================================================
#  Validación inicial
# ============================================================================
if archivo_excel is None:
    st.info("👈 Sube tu Excel en la barra lateral para empezar.")
    st.markdown("""
    ### 📋 Formato esperado del Excel
    | Ranking | Jugador        |
    |---------|----------------|
    | 1       | Marcelo Rios   |
    | 2       | Roger Federer  |
    | ...     | ...            |

    ### 🎯 Cómo funciona la escalerilla
    - Los jugadores se dividen en **N categorías** (default 4) según ranking.
    - Cada ronda, cada jugador tiene:
        - **1 partido interno** vs alguien de su misma categoría
        - **1 partido cruzado** vs alguien de la categoría adyacente (A↔B, C↔D, ...)
    - No se repiten parejas hasta completar el ciclo.

    ### 🏆 Puntaje
    - **Partido ganado:** 200 puntos
    - **Partido perdido:** 25 puntos
    - **W.O. a favor:** 50 puntos (debe evidenciarse)
    """)
    st.stop()

try:
    df_jugadores = pd.read_excel(archivo_excel)
except Exception as e:
    st.error(f"No se pudo leer el Excel: {e}")
    st.stop()

if "Ranking" not in df_jugadores.columns or "Jugador" not in df_jugadores.columns:
    st.error(f"Columnas requeridas: 'Ranking' y 'Jugador'. Encontradas: {list(df_jugadores.columns)}")
    st.stop()

jugadores = df_jugadores.to_dict("records")
categorias = dividir_en_categorias(jugadores, n_categorias=int(n_categorias))

# ============================================================================
#  Pestañas
# ============================================================================
tab_ronda, tab_resultados, tab_ranking = st.tabs([
    "🎯 Generar Ronda",
    "📝 Cargar Resultados",
    "🏆 Ranking",
])

# ----------------------------------------------------------------------------
#  TAB 1: Generar Ronda
# ----------------------------------------------------------------------------
with tab_ronda:
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

    # Aviso si hay partidos pendientes
    pendientes = partidos_pendientes(st.session_state.historial)
    if pendientes:
        st.warning(f"⚠️ Hay **{len(pendientes)} partido(s) pendiente(s)** sin resultado de rondas anteriores.")

    col_gen, col_info = st.columns([1, 3])
    with col_gen:
        if st.button("🎯 Generar siguiente ronda", type="primary", use_container_width=True):
            resultados = siguiente_ronda_completa(categorias, st.session_state.historial)
            nuevos = registrar_partidos_generados(st.session_state.historial, resultados)
            st.session_state.ultima_ronda = resultados
            st.success(f"Se generaron {nuevos} partidos nuevos.")

    with col_info:
        st.caption("Cada ronda incluye partidos internos + cruzados para todas las categorías.")

    if st.session_state.ultima_ronda:
        st.subheader("🎯 Última ronda generada")
        df_ronda = resultados_a_dataframe(st.session_state.ultima_ronda)
        total = len(df_ronda[df_ronda["Jugador 2"] != "DESCANSA"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Total partidos", total)
        c2.metric("Internos", len(df_ronda[(df_ronda["Tipo"] == "Interno") & (df_ronda["Jugador 2"] != "DESCANSA")]))
        c3.metric("Cruzados", len(df_ronda[df_ronda["Tipo"] == "Cruzado"]))

        st.dataframe(df_ronda, hide_index=True, use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_ronda.to_excel(writer, index=False, sheet_name="Ronda")
        buffer.seek(0)
        st.download_button(
            label="📊 Descargar ronda en Excel",
            data=buffer,
            file_name=f"ronda_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ----------------------------------------------------------------------------
#  TAB 2: Cargar Resultados
# ----------------------------------------------------------------------------
with tab_resultados:
    st.subheader("📝 Cargar resultados de partidos")

    todos_los_partidos = st.session_state.historial.get("partidos", [])
    if not todos_los_partidos:
        st.info("Aún no hay partidos generados. Ve a la pestaña **Generar Ronda** primero.")
    else:
        pendientes = partidos_pendientes(st.session_state.historial)
        completados = partidos_completados(st.session_state.historial)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total partidos", len(todos_los_partidos))
        c2.metric("Pendientes", len(pendientes))
        c3.metric("Completados", len(completados))

        # --- Filtros ---
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            mostrar = st.radio(
                "Mostrar",
                options=["Pendientes", "Completados", "Todos"],
                horizontal=True,
            )
        with col_f2:
            bloques_disponibles = sorted({p["bloque"] for p in todos_los_partidos})
            filtro_bloque = st.multiselect(
                "Filtrar por bloque",
                options=bloques_disponibles,
                default=bloques_disponibles,
            )

        if mostrar == "Pendientes":
            lista = pendientes
        elif mostrar == "Completados":
            lista = completados
        else:
            lista = todos_los_partidos

        lista = [p for p in lista if p["bloque"] in filtro_bloque]

        if not lista:
            st.info("No hay partidos para mostrar con esos filtros.")
        else:
            # --- Selector de partido ---
            def label_partido(p):
                estado = "✅" if p["resultado"] else "⏳"
                return (
                    f"{estado} {p['id']} · [{p['tipo']}] {p['bloque']} R{p['ronda_bloque']} · "
                    f"#{p['jugador_1']['Ranking']} {p['jugador_1']['Jugador']} "
                    f"vs #{p['jugador_2']['Ranking']} {p['jugador_2']['Jugador']}"
                )

            partido_sel = st.selectbox(
                "Selecciona un partido",
                options=lista,
                format_func=label_partido,
            )

            st.divider()

            if partido_sel:
                j1 = partido_sel["jugador_1"]
                j2 = partido_sel["jugador_2"]

                st.markdown(
                    f"### {partido_sel['id']} — {partido_sel['tipo']} {partido_sel['bloque']} "
                    f"(R{partido_sel['ronda_bloque']}/C{partido_sel['ciclo_bloque']})"
                )
                col_j1, col_vs, col_j2 = st.columns([3, 1, 3])
                col_j1.markdown(f"#### #{j1['Ranking']} — {j1['Jugador']}")
                col_vs.markdown("### ↔")
                col_j2.markdown(f"#### #{j2['Ranking']} — {j2['Jugador']}")

                # Mostrar resultado actual si existe
                if partido_sel["resultado"]:
                    st.info(f"Resultado registrado: **{formatear_marcador(partido_sel['resultado'])}**")
                    if st.button("🗑️ Borrar resultado", key="borrar"):
                        borrar_resultado(st.session_state.historial, partido_sel["id"])
                        st.success("Resultado borrado.")
                        st.rerun()

                st.divider()

                # --- Form para cargar/actualizar resultado ---
                tipo_resultado = st.radio(
                    "Tipo de resultado",
                    options=["Normal (partido jugado)", f"W.O. a favor de {j1['Jugador']}", f"W.O. a favor de {j2['Jugador']}"],
                    horizontal=False,
                )

                with st.form(key=f"form_{partido_sel['id']}"):
                    if tipo_resultado.startswith("Normal"):
                        n_sets = st.radio("Cantidad de sets", options=[2, 3], horizontal=True)
                        sets = []
                        for i in range(int(n_sets)):
                            st.markdown(f"**Set {i+1}**")
                            cs1, cs2 = st.columns(2)
                            games_1 = cs1.number_input(
                                f"Games {j1['Jugador']}",
                                min_value=0, max_value=20, value=0, step=1,
                                key=f"g1_{partido_sel['id']}_{i}",
                            )
                            games_2 = cs2.number_input(
                                f"Games {j2['Jugador']}",
                                min_value=0, max_value=20, value=0, step=1,
                                key=f"g2_{partido_sel['id']}_{i}",
                            )
                            sets.append({"games_1": int(games_1), "games_2": int(games_2)})
                        nota_wo = None
                        tipo = "normal"
                    else:
                        sets = None
                        nota_wo = st.text_input(
                            "Evidencia / nota del W.O. (obligatorio)",
                            placeholder="Ej: Foto enviada al grupo, mensaje del jugador, etc.",
                        )
                        tipo = "wo_j1" if j1["Jugador"] in tipo_resultado else "wo_j2"

                    submitted = st.form_submit_button("💾 Guardar resultado", type="primary", use_container_width=True)

                    if submitted:
                        try:
                            if tipo == "normal":
                                # Validar que se ingresaron games
                                if all(s["games_1"] == 0 and s["games_2"] == 0 for s in sets):
                                    st.error("Debes ingresar los games de al menos un set.")
                                else:
                                    # Filtrar sets vacíos (todos 0-0)
                                    sets_validos = [s for s in sets if not (s["games_1"] == 0 and s["games_2"] == 0)]
                                    registrar_resultado(
                                        st.session_state.historial,
                                        partido_sel["id"],
                                        tipo="normal",
                                        sets=sets_validos,
                                    )
                                    st.success("✅ Resultado guardado.")
                                    st.rerun()
                            else:
                                if not nota_wo or not nota_wo.strip():
                                    st.error("Debes ingresar la evidencia/nota del W.O.")
                                else:
                                    registrar_resultado(
                                        st.session_state.historial,
                                        partido_sel["id"],
                                        tipo=tipo,
                                        nota_wo=nota_wo.strip(),
                                    )
                                    st.success("✅ W.O. registrado.")
                                    st.rerun()
                        except ValueError as e:
                            st.error(f"Error: {e}")

# ----------------------------------------------------------------------------
#  TAB 3: Ranking
# ----------------------------------------------------------------------------
with tab_ranking:
    st.subheader("🏆 Ranking acumulado de la temporada")

    if not partidos_completados(st.session_state.historial):
        st.info("Aún no hay resultados cargados. Ve a la pestaña **Cargar Resultados** primero.")
    else:
        df_ranking = calcular_ranking(st.session_state.historial, jugadores)

        # Métricas resumen
        total_partidos = len(partidos_completados(st.session_state.historial))
        lider = df_ranking.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Partidos jugados", total_partidos)
        c2.metric("Líder", lider["Jugador"], f"{lider['Puntos']} pts")
        c3.metric("Jugadores activos", int((df_ranking["PJ"] > 0).sum()))

        st.dataframe(
            df_ranking,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Pos.": st.column_config.NumberColumn(width="small"),
                "Puntos": st.column_config.NumberColumn(format="%d"),
            },
        )

        st.caption(
            f"Criterio de orden: 1° Puntos · 2° Partidos ganados · 3° Ranking inicial · "
            f"PJ=Partidos jugados · G=Ganados · P=Perdidos · WO+=WO a favor · WO-=WO en contra"
        )

        # Descarga
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_ranking.to_excel(writer, index=False, sheet_name="Ranking")
        buffer.seek(0)
        st.download_button(
            label="📊 Descargar ranking en Excel",
            data=buffer,
            file_name=f"ranking_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
