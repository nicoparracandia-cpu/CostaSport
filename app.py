"""
app.py — Costa Sport · Escalerilla
"""
from __future__ import annotations
import io
import base64
from datetime import datetime
from pathlib import Path

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
from db import (
    cargar_historial,
    guardar_historial,
    get_jugadores,
    get_todos_jugadores,
    actualizar_jugadores_desde_excel,
    set_jugador_activo,
)

# ============================================================================
#  Configuración + Branding
# ============================================================================
LOGO_PATH = Path("assets/logo.png")

st.set_page_config(
    page_title="Costa Sport — Escalerilla",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🎾",
    layout="wide",
    initial_sidebar_state="expanded",
)

COSTA_BLUE = "#33B9F3"
COSTA_BLUE_DARK = "#1A8FC4"
COSTA_BLUE_LIGHT = "#7FD4FA"
DARK_BG = "#0E1117"
DARK_CARD = "#1A1F2E"
ACCENT_YELLOW = "#FFD54F"
SUCCESS_GREEN = "#66BB6A"
DANGER_RED = "#EF5350"

st.markdown(f"""
<style>
    .costa-header {{
        background: linear-gradient(135deg, {DARK_CARD} 0%, #0E1117 100%);
        border-left: 4px solid {COSTA_BLUE};
        border-radius: 8px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 1.2rem;
    }}
    .costa-header h1 {{
        margin: 0;
        font-size: 1.8rem;
        color: white;
        letter-spacing: 0.5px;
    }}
    .costa-header p {{
        margin: 0.2rem 0 0 0;
        color: {COSTA_BLUE_LIGHT};
        font-size: 0.9rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px;
        background-color: {DARK_CARD};
        padding: 6px;
        border-radius: 10px;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 44px;
        padding: 0 20px;
        background-color: transparent;
        border-radius: 6px;
        color: #B0B7C3;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {COSTA_BLUE} !important;
        color: white !important;
        font-weight: 600;
    }}
    .stButton button[kind="primary"] {{
        background-color: {COSTA_BLUE};
        border: none;
        font-weight: 600;
    }}
    .stButton button[kind="primary"]:hover {{
        background-color: {COSTA_BLUE_DARK};
    }}
    [data-testid="stMetric"] {{
        background-color: {DARK_CARD};
        padding: 1rem;
        border-radius: 8px;
        border-left: 3px solid {COSTA_BLUE};
    }}
    .costa-footer {{
        text-align: center;
        color: #6B7280;
        font-size: 0.8rem;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #2A2F3E;
    }}
    .costa-footer strong {{
        color: {COSTA_BLUE};
    }}
</style>
""", unsafe_allow_html=True)


# ============================================================================
#  Helpers
# ============================================================================
def render_header():
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" height="80" style="border-radius: 6px;">'
    else:
        logo_html = '<div style="font-size: 3rem;">🎾</div>'
    st.markdown(f"""
    <div class="costa-header">
        {logo_html}
        <div>
            <h1>Escalerilla</h1>
            <p>Costa Sport · Tennis Club</p>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_footer():
    st.markdown(f"""
    <div class="costa-footer">
        <strong>Costa Sport · Tennis Club</strong> — Escalerilla {datetime.now().year}
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
#  Estado de sesión — ahora carga desde Supabase al iniciar
# ============================================================================
if "historial" not in st.session_state:
    with st.spinner("Cargando historial..."):
        st.session_state.historial = cargar_historial()

if "ultima_ronda" not in st.session_state:
    st.session_state.ultima_ronda = None

if "jugadores_supabase" not in st.session_state:
    st.session_state.jugadores_supabase = get_jugadores()

if "es_admin" not in st.session_state:
    st.session_state.es_admin = False
    st.session_state.jugadores_supabase = get_jugadores()


def _guardar_y_rerun():
    """Guarda el historial en Supabase y hace rerun."""
    guardar_historial(st.session_state.historial)
    st.rerun()


# ============================================================================
#  Sidebar
# ============================================================================
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)

    st.divider()

    # ── Login / Logout Admin ──
    if st.session_state.es_admin:
        st.success("🔐 Modo Admin activo")
        if st.button("Cerrar sesión admin", use_container_width=True):
            st.session_state.es_admin = False
            st.rerun()
    else:
        with st.expander("🔐 Acceso Admin"):
            pwd = st.text_input("Contraseña", type="password", key="pwd_input")
            if st.button("Ingresar", use_container_width=True):
                if pwd == st.secrets.get("ADMIN_PASSWORD", ""):
                    st.session_state.es_admin = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta.")

    st.divider()

    # ── Sección solo visible para admin ──
    if st.session_state.es_admin:
        st.header("📥 Lista de jugadores")
        jugadores_db = st.session_state.jugadores_supabase
        if jugadores_db:
            st.success(f"✅ {len(jugadores_db)} jugadores en BD")
            with st.expander("Ver jugadores"):
                st.dataframe(
                    pd.DataFrame(jugadores_db)[["ranking", "nombre"]].rename(
                        columns={"ranking": "Ranking", "nombre": "Jugador"}
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

        archivo_excel = st.file_uploader(
            "Actualizar lista (Excel)",
            type=["xlsx", "xls"],
            help="Columnas: Ranking, Jugador, Performance, Puntaje",
        )
        if archivo_excel is not None:
            try:
                df_excel = pd.read_excel(archivo_excel, sheet_name=0)
                if "Ranking" not in df_excel.columns or "Jugador" not in df_excel.columns:
                    st.error("Columnas requeridas: 'Ranking' y 'Jugador'.")
                else:
                    if st.button("💾 Guardar jugadores en BD", type="primary", use_container_width=True):
                        with st.spinner("Guardando..."):
                            actualizar_jugadores_desde_excel(df_excel.to_dict("records"))
                            st.session_state.jugadores_supabase = get_jugadores()
                        st.success(f"✅ {len(df_excel)} jugadores guardados.")
                        st.rerun()
            except Exception as e:
                st.error(f"No se pudo leer el Excel: {e}")

        st.divider()
        if st.session_state.historial:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="💾 Backup historial.json",
                data=historial_a_json(st.session_state.historial),
                file_name=f"historial_{timestamp}.json",
                mime="application/json",
                use_container_width=True,
            )
        if st.button("🔄 Reiniciar todo", use_container_width=True):
            st.session_state.historial = {}
            st.session_state.ultima_ronda = None
            guardar_historial({})
            st.success("Reiniciado.")
            st.rerun()

    st.divider()
    n_categorias = st.number_input(
        "Número de categorías",
        min_value=2, max_value=8, value=4, step=2,
    )


# ============================================================================
#  Header
# ============================================================================
render_header()

# ============================================================================
#  Validación: necesitamos jugadores en la BD
# ============================================================================
jugadores_db = st.session_state.jugadores_supabase

if not jugadores_db:
    st.info("👈 Sube tu Excel en la barra lateral para cargar los jugadores por primera vez.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📋 Formato esperado del Excel")
        st.markdown("""
        | Ranking | Jugador        |
        |---------|----------------|
        | 1       | Marcelo Rios   |
        | 2       | Roger Federer  |
        | ...     | ...            |
        """)
    with col2:
        st.markdown("### 🏆 Sistema de puntaje")
        st.markdown(f"""
        - 🥇 **Partido ganado:** {PUNTOS_GANADO} pts
        - 🥈 **Partido perdido:** {PUNTOS_PERDIDO} pts
        - ⚠️ **W.O. a favor:** {PUNTOS_WO_FAVOR} pts
        """)
    render_footer()
    st.stop()

# Convertir jugadores de BD al formato que espera pairing.py
jugadores = [{"Ranking": j["ranking"], "Jugador": j["nombre"], "performance": j.get("performance") or 0, "puntos_base": j.get("puntos_base") or 0} for j in jugadores_db]
categorias = dividir_en_categorias(jugadores, n_categorias=int(n_categorias))


# ============================================================================
#  Pestañas
# ============================================================================
tab_ronda, tab_resultados, tab_ranking, tab_jugadores = st.tabs([
    "🎯 Generar Ronda",
    "📝 Cargar Resultados",
    "🏆 Ranking",
    "⚙️ Jugadores",
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

    pendientes = partidos_pendientes(st.session_state.historial)
    if pendientes:
        st.warning(f"⚠️ Hay **{len(pendientes)} partido(s) pendiente(s)** sin resultado.")

    col_gen, col_info = st.columns([1, 3])
    with col_gen:
        if st.session_state.es_admin:
            if st.button("🎯 Generar siguiente ronda", type="primary", use_container_width=True):
                resultados = siguiente_ronda_completa(categorias, st.session_state.historial)
                nuevos = registrar_partidos_generados(st.session_state.historial, resultados)
                st.session_state.ultima_ronda = resultados
                guardar_historial(st.session_state.historial)
                st.success(f"✅ Se generaron {nuevos} partidos nuevos. Guardado en base de datos.")
        else:
            st.info("🔐 Solo el administrador puede generar rondas.")

    with col_info:
        st.caption("Cada ronda incluye partidos internos + cruzados para todas las categorías.")

    if st.session_state.ultima_ronda:
        st.subheader("🎯 Última ronda generada")

        # Mostrar notas especiales (ej: jugador con doble partido)
        for res in st.session_state.ultima_ronda:
            if res.get("nota"):
                st.warning(res["nota"])

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
            file_name=f"costa_sport_ronda_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ── Editor de emparejamientos (solo admin, solo si no hay resultados aún) ──
        if st.session_state.es_admin:
            partidos_ronda = st.session_state.historial.get("partidos", [])
            partidos_sin_resultado = [p for p in partidos_ronda if p["resultado"] is None]
            todos_con_resultado = len(partidos_sin_resultado) == 0

            if todos_con_resultado:
                st.info("Ya hay resultados registrados — no se puede editar el emparejamiento.")
            else:
                with st.expander("✏️ Editar emparejamientos"):
                    st.caption("Solo disponible antes de registrar cualquier resultado.")

                    # Obtener todos los jugadores activos para los selectbox
                    nombres_jugadores = sorted([j["nombre"] for j in st.session_state.jugadores_supabase])

                    st.markdown("#### Cambiar jugador en una pareja")
                    # Seleccionar partido a editar
                    def label_partido_edicion(p):
                        return (f"[{p['tipo']}] {p['bloque']} · "
                                f"#{p['jugador_1']['Ranking']} {p['jugador_1']['Jugador']} "
                                f"vs #{p['jugador_2']['Ranking']} {p['jugador_2']['Jugador']}")

                    partido_editar = st.selectbox(
                        "Partido a editar",
                        options=partidos_sin_resultado,
                        format_func=label_partido_edicion,
                        key="partido_editar"
                    )

                    if partido_editar:
                        col_j1, col_vs, col_j2 = st.columns([5, 1, 5])
                        with col_j1:
                            nuevo_j1 = st.selectbox(
                                "Jugador 1",
                                options=nombres_jugadores,
                                index=nombres_jugadores.index(partido_editar["jugador_1"]["Jugador"])
                                      if partido_editar["jugador_1"]["Jugador"] in nombres_jugadores else 0,
                                key="edit_j1"
                            )
                        with col_vs:
                            st.markdown("<br><center>vs</center>", unsafe_allow_html=True)
                        with col_j2:
                            nuevo_j2 = st.selectbox(
                                "Jugador 2",
                                options=nombres_jugadores,
                                index=nombres_jugadores.index(partido_editar["jugador_2"]["Jugador"])
                                      if partido_editar["jugador_2"]["Jugador"] in nombres_jugadores else 0,
                                key="edit_j2"
                            )

                        if st.button("💾 Guardar cambio", type="primary", key="btn_guardar_edicion"):
                            if nuevo_j1 == nuevo_j2:
                                st.error("Los dos jugadores no pueden ser el mismo.")
                            else:
                                # Buscar ranking de los nuevos jugadores
                                jug_data = {j["nombre"]: j for j in st.session_state.jugadores_supabase}
                                j1_data = jug_data.get(nuevo_j1, {})
                                j2_data = jug_data.get(nuevo_j2, {})
                                # Actualizar en historial
                                for p in st.session_state.historial["partidos"]:
                                    if p["id"] == partido_editar["id"]:
                                        p["jugador_1"] = {"Ranking": j1_data.get("ranking", 0), "Jugador": nuevo_j1}
                                        p["jugador_2"] = {"Ranking": j2_data.get("ranking", 0), "Jugador": nuevo_j2}
                                        break
                                guardar_historial(st.session_state.historial)
                                st.success(f"✅ Pareja actualizada: {nuevo_j1} vs {nuevo_j2}")
                                st.rerun()

                    st.divider()
                    st.markdown("#### Intercambiar jugadores entre dos parejas")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        partido_a = st.selectbox(
                            "Pareja A",
                            options=partidos_sin_resultado,
                            format_func=label_partido_edicion,
                            key="intercambio_a"
                        )
                        pos_a = st.radio("Jugador de A a intercambiar", ["Jugador 1", "Jugador 2"], key="pos_a", horizontal=True)
                    with col_p2:
                        partido_b = st.selectbox(
                            "Pareja B",
                            options=partidos_sin_resultado,
                            format_func=label_partido_edicion,
                            key="intercambio_b"
                        )
                        pos_b = st.radio("Jugador de B a intercambiar", ["Jugador 1", "Jugador 2"], key="pos_b", horizontal=True)

                    if st.button("🔄 Intercambiar", type="primary", key="btn_intercambiar"):
                        if partido_a["id"] == partido_b["id"]:
                            st.error("Selecciona dos parejas distintas.")
                        else:
                            key_a = "jugador_1" if pos_a == "Jugador 1" else "jugador_2"
                            key_b = "jugador_1" if pos_b == "Jugador 1" else "jugador_2"
                            for p in st.session_state.historial["partidos"]:
                                if p["id"] == partido_a["id"]:
                                    pa = p
                                if p["id"] == partido_b["id"]:
                                    pb = p
                            # Intercambiar
                            pa[key_a], pb[key_b] = pb[key_b], pa[key_a]
                            guardar_historial(st.session_state.historial)
                            st.success("✅ Jugadores intercambiados correctamente.")
                            st.rerun()

# ----------------------------------------------------------------------------
#  TAB 2: Cargar Resultados
# ----------------------------------------------------------------------------
with tab_resultados:
    st.subheader("📝 Cargar resultados de partidos")

    todos = st.session_state.historial.get("partidos", [])
    if not todos:
        st.info("Aún no hay partidos generados. Ve a la pestaña **Generar Ronda** primero.")
    else:
        pendientes = partidos_pendientes(st.session_state.historial)
        completados = partidos_completados(st.session_state.historial)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total partidos", len(todos))
        c2.metric("Pendientes", len(pendientes))
        c3.metric("Completados", len(completados))

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            mostrar = st.radio("Mostrar", options=["Pendientes", "Completados", "Todos"], horizontal=True)
        with col_f2:
            bloques_disponibles = sorted({p["bloque"] for p in todos})
            filtro_bloque = st.multiselect("Filtrar por bloque", options=bloques_disponibles, default=bloques_disponibles)

        lista = {"Pendientes": pendientes, "Completados": completados, "Todos": todos}[mostrar]
        lista = [p for p in lista if p["bloque"] in filtro_bloque]

        if not lista:
            st.info("No hay partidos para mostrar con esos filtros.")
        else:
            def label_partido(p):
                estado = "✅" if p["resultado"] else "⏳"
                return (
                    f"{estado} {p['id']} · [{p['tipo']}] {p['bloque']} R{p['ronda_bloque']} · "
                    f"#{p['jugador_1']['Ranking']} {p['jugador_1']['Jugador']} "
                    f"vs #{p['jugador_2']['Ranking']} {p['jugador_2']['Jugador']}"
                )

            partido_sel = st.selectbox("Selecciona un partido", options=lista, format_func=label_partido)

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

                if partido_sel["resultado"]:
                    st.info(f"Resultado registrado: **{formatear_marcador(partido_sel['resultado'])}**")
                    if st.session_state.es_admin:
                        if st.button("🗑️ Borrar resultado", key="borrar"):
                            borrar_resultado(st.session_state.historial, partido_sel["id"])
                            guardar_historial(st.session_state.historial)
                            st.success("Resultado borrado.")
                            st.rerun()

                st.divider()

                tipo_resultado = st.radio(
                    "Tipo de resultado",
                    options=["Normal (partido jugado)", f"W.O. a favor de {j1['Jugador']}", f"W.O. a favor de {j2['Jugador']}"],
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
                                if all(s["games_1"] == 0 and s["games_2"] == 0 for s in sets):
                                    st.error("Debes ingresar los games de al menos un set.")
                                else:
                                    sets_validos = [s for s in sets if not (s["games_1"] == 0 and s["games_2"] == 0)]
                                    registrar_resultado(st.session_state.historial, partido_sel["id"], tipo="normal", sets=sets_validos)
                                    guardar_historial(st.session_state.historial)   # ← guarda en Supabase
                                    st.success("✅ Resultado guardado.")
                                    st.rerun()
                            else:
                                if not nota_wo or not nota_wo.strip():
                                    st.error("Debes ingresar la evidencia/nota del W.O.")
                                else:
                                    registrar_resultado(st.session_state.historial, partido_sel["id"], tipo=tipo, nota_wo=nota_wo.strip())
                                    guardar_historial(st.session_state.historial)   # ← guarda en Supabase
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

        total_partidos = len(partidos_completados(st.session_state.historial))
        lider = df_ranking.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Partidos jugados", total_partidos)
        c2.metric("Líder 🥇", lider["Jugador"], f"{lider['Puntos']} pts")
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
            "Orden: 1° Puntos · 2° Partidos ganados · 3° Ranking inicial · "
            "Puntos = Pts base (historial) + Pts nuevos (partidos jugados) · Desempate: Performance · Ranking inicial"
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_ranking.to_excel(writer, index=False, sheet_name="Ranking")
        buffer.seek(0)
        st.download_button(
            label="📊 Descargar ranking en Excel",
            data=buffer,
            file_name=f"costa_sport_ranking_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ----------------------------------------------------------------------------
#  TAB 4: Gestión de Jugadores
# ----------------------------------------------------------------------------
with tab_jugadores:
    if not st.session_state.es_admin:
        st.warning("🔐 Esta sección es solo para administradores. Ingresa con tu contraseña en el panel lateral.")
        st.stop()
    st.subheader("⚙️ Gestión de jugadores")

    todos = get_todos_jugadores()
    activos = [j for j in todos if j["activo"]]
    inactivos = [j for j in todos if not j["activo"]]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total inscritos", len(todos))
    c2.metric("Activos en escalerilla", len(activos))
    c3.metric("Fuera (inactivos)", len(inactivos))

    st.divider()

    st.markdown("#### Lista completa")
    st.caption("Solo los jugadores activos participan en la escalerilla.")

    if not todos:
        st.info("No hay jugadores cargados aún.")
    else:
        for j in todos:
            col_rank, col_nombre, col_estado, col_accion = st.columns([1, 4, 2, 2])
            col_rank.markdown(f"**#{j['ranking']}**")
            col_nombre.markdown(j["nombre"])
            if j["activo"]:
                col_estado.success("✅ Activo")
                if col_accion.button("Desactivar", key=f"toggle_{j['id']}", use_container_width=True):
                    set_jugador_activo(j["id"], False)
                    st.session_state.jugadores_supabase = get_jugadores()
                    st.rerun()
            else:
                col_estado.error("❌ Inactivo")
                if col_accion.button("Reactivar", key=f"toggle_{j['id']}", use_container_width=True):
                    set_jugador_activo(j["id"], True)
                    st.session_state.jugadores_supabase = get_jugadores()
                    st.rerun()

    st.divider()

    st.markdown("#### Agregar jugador manualmente")
    with st.form("form_agregar_jugador"):
        col_n, col_r = st.columns([3, 1])
        nuevo_nombre = col_n.text_input("Nombre", placeholder="Ej: Juan Pérez")
        nuevo_ranking = col_r.number_input("Ranking", min_value=1, max_value=500, value=len(todos) + 1)
        if st.form_submit_button("➕ Agregar jugador", type="primary", use_container_width=True):
            if not nuevo_nombre.strip():
                st.error("Debes ingresar un nombre.")
            else:
                try:
                    from db import get_supabase
                    sb = get_supabase()
                    sb.table("jugadores").insert({
                        "nombre": nuevo_nombre.strip(),
                        "ranking": int(nuevo_ranking),
                        "activo": True,
                    }).execute()
                    st.session_state.jugadores_supabase = get_jugadores()
                    st.success(f"✅ {nuevo_nombre.strip()} agregado con ranking #{nuevo_ranking}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al agregar: {e}")

render_footer()
