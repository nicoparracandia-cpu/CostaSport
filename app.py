"""
app.py — Costa Sport · Escalerilla
"""
from __future__ import annotations
import io
import json
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
import importlib
import resultados as _resultados_mod
importlib.reload(_resultados_mod)
from resultados import (
    registrar_partidos_generados,
    registrar_resultado,
    borrar_resultado,
    registrar_no_jugado,
    jugadores_a_desactivar,
    partidos_pendientes,
    partidos_completados,
    calcular_ranking,
    formatear_marcador,
    validar_sets,
    PUNTOS_GANADO, PUNTOS_PERDIDO, PUNTOS_WO_FAVOR,
)
from bracket import (
    hacer_sorteo, aplicar_sorteo_supabase,
    generar_svg_eliminacion, generar_svg_round_robin, generar_svg_grupos,
    generar_pdf_bracket,
)
from bracket_pdf import generar_pdf_bracket_visual
from torneos import (
    get_torneo_activo, get_todos_torneos, crear_torneo, finalizar_torneo, eliminar_torneo,
    calcular_puntos_torneo, aplicar_puntos_al_ranking,
    get_participantes, agregar_participante, eliminar_participante,
    actualizar_seed, get_partidos_torneo, get_partidos_fase,
    crear_partido, registrar_resultado_torneo, borrar_resultado_torneo,
    generar_bracket_eliminacion, generar_round_robin, generar_grupos,
    calcular_tabla_grupo, nombre_participante, calcular_puntos_ranking,
)
from db import (
    cargar_historial,
    guardar_historial,
    get_jugadores,
    get_todos_jugadores,
    actualizar_jugadores_desde_excel,
    set_jugador_activo,
    get_supabase,
    get_jugador_by_nombre,
    guardar_caracteristicas,
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

        # ── Importar historial JSON ──
        st.markdown("**📂 Importar historial**")
        archivo_historial = st.file_uploader(
            "historial_completo.json",
            type=["json"],
            key="import_historial",
            help="Importa un historial previo. Se fusiona con el actual.",
        )
        if archivo_historial is not None:
            try:
                historial_nuevo = json.loads(archivo_historial.read().decode("utf-8"))
                partidos_nuevos = historial_nuevo.get("partidos", [])
                if not partidos_nuevos:
                    st.error("El archivo no contiene partidos válidos.")
                else:
                    col_imp1, col_imp2 = st.columns(2)
                    with col_imp1:
                        st.info(f"{len(partidos_nuevos)} partidos")
                    with col_imp2:
                        if st.button("⬆️ Importar", type="primary", use_container_width=True, key="btn_importar"):
                            # Fusionar: reemplazar partidos existentes o agregar nuevos
                            historial_actual = st.session_state.historial
                            ids_actuales = {p["id"] for p in historial_actual.get("partidos", [])}
                            agregados = 0
                            for p in partidos_nuevos:
                                if p["id"] not in ids_actuales:
                                    historial_actual.setdefault("partidos", []).append(p)
                                    agregados += 1
                            guardar_historial(historial_actual)
                            st.session_state.historial = historial_actual
                            st.success(f"✅ {agregados} partidos importados a Supabase.")
                            st.rerun()
            except Exception as e:
                st.error(f"Error al importar: {e}")

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
        st.divider()



# Convertir jugadores de BD al formato que espera pairing.py
jugadores = [{"Ranking": j["ranking"], "Jugador": j["nombre"], "performance": j.get("performance") or 0, "puntos_base": j.get("puntos_base") or 0} for j in jugadores_db]
categorias = dividir_en_categorias(jugadores, n_categorias=int(n_categorias))


# ============================================================================
#  Pestañas
# ============================================================================
tab_ronda, tab_resultados, tab_ranking, tab_perfiles, tab_torneos, tab_jugadores = st.tabs([
    "🎯 Generar Ronda",
    "📝 Cargar Resultados",
    "🏆 Ranking",
    "👤 Perfiles",
    "🏅 Torneos",
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
                    options=[
                        "Normal (partido jugado)",
                        f"W.O. a favor de {j1['Jugador']}",
                        f"W.O. a favor de {j2['Jugador']}",
                        "No jugado",
                    ],
                )

                with st.form(key=f"form_{partido_sel['id']}"):
                    if tipo_resultado.startswith("Normal"):
                        sets = []
                        st.markdown("**Set 1**")
                        cs1, cs2 = st.columns(2)
                        g1 = cs1.number_input(f"Games {j1['Jugador']}", min_value=0, max_value=7, value=0, step=1, key=f"g1_{partido_sel['id']}_0")
                        g2 = cs2.number_input(f"Games {j2['Jugador']}", min_value=0, max_value=7, value=0, step=1, key=f"g2_{partido_sel['id']}_0")
                        sets.append({"games_1": int(g1), "games_2": int(g2)})

                        st.markdown("**Set 2**")
                        cs1, cs2 = st.columns(2)
                        g1 = cs1.number_input(f"Games {j1['Jugador']}", min_value=0, max_value=7, value=0, step=1, key=f"g1_{partido_sel['id']}_1")
                        g2 = cs2.number_input(f"Games {j2['Jugador']}", min_value=0, max_value=7, value=0, step=1, key=f"g2_{partido_sel['id']}_1")
                        sets.append({"games_1": int(g1), "games_2": int(g2)})

                        st.markdown("**Set 3 — Tie-break** *(primero en llegar a 10, diferencia de 2)*")
                        cs1, cs2 = st.columns(2)
                        g1 = cs1.number_input(f"Puntos {j1['Jugador']}", min_value=0, max_value=99, value=0, step=1, key=f"g1_{partido_sel['id']}_2")
                        g2 = cs2.number_input(f"Puntos {j2['Jugador']}", min_value=0, max_value=99, value=0, step=1, key=f"g2_{partido_sel['id']}_2")
                        sets.append({"games_1": int(g1), "games_2": int(g2)})
                        nota_wo = None
                        tipo = "normal"

                    elif tipo_resultado == "No jugado":
                        sets = None
                        nota_wo = None
                        tipo = "no_jugado"
                        justificacion = st.selectbox(
                            "Motivo (obligatorio)",
                            options=["Sin acuerdo", "Por enfermedad", "Por lesión"],
                            key=f"just_{partido_sel['id']}",
                        )

                    else:
                        sets = None
                        tipo = "wo_j1" if j1["Jugador"] in tipo_resultado else "wo_j2"
                        nota_wo = st.text_input(
                            "Justificación del W.O. (obligatorio)",
                            placeholder="Ej: El jugador no se presentó, avisó por WhatsApp, etc.",
                        )

                    submitted = st.form_submit_button("💾 Guardar resultado", type="primary", use_container_width=True)

                    if submitted:
                        try:
                            if tipo == "normal":
                                s1, s2, s3 = sets[0], sets[1], sets[2]
                                sets_1 = sum(1 for s in [s1, s2] if s["games_1"] > s["games_2"])
                                sets_2 = sum(1 for s in [s1, s2] if s["games_2"] > s["games_1"])
                                hubo_tercer_set = sets_1 == 1 and sets_2 == 1
                                if s1["games_1"] == 0 and s1["games_2"] == 0:
                                    st.error("Debes ingresar el resultado del Set 1.")
                                else:
                                    sets_a_guardar = [s1, s2]
                                    if hubo_tercer_set:
                                        sets_a_guardar.append(s3)
                                    errores = validar_sets(sets_a_guardar)
                                    if errores:
                                        for e in errores:
                                            st.error(e)
                                    else:
                                        registrar_resultado(st.session_state.historial, partido_sel["id"], tipo="normal", sets=sets_a_guardar)
                                        guardar_historial(st.session_state.historial)
                                        st.success("✅ Resultado guardado.")
                                        st.rerun()

                            elif tipo == "no_jugado":
                                registrar_no_jugado(st.session_state.historial, partido_sel["id"], justificacion)
                                guardar_historial(st.session_state.historial)
                                # Verificar si algún jugador debe desactivarse
                                a_desactivar = jugadores_a_desactivar(st.session_state.historial, limite=2)
                                jugadores_actuales = {j["nombre"] for j in st.session_state.jugadores_supabase}
                                nuevos_a_desactivar = [n for n in a_desactivar if n in jugadores_actuales]
                                if nuevos_a_desactivar:
                                    from db import set_jugador_activo, get_jugadores
                                    for nombre in nuevos_a_desactivar:
                                        jug = next((j for j in st.session_state.jugadores_supabase if j["nombre"] == nombre), None)
                                        if jug and jug["activo"]:
                                            set_jugador_activo(jug["id"], False)
                                    st.session_state.jugadores_supabase = get_jugadores()
                                    st.warning(f"⚠️ Jugadores desactivados automáticamente por 2 inasistencias consecutivas: {', '.join(nuevos_a_desactivar)}")
                                else:
                                    st.success(f"✅ Partido marcado como No jugado — {justificacion}.")
                                st.rerun()

                            else:
                                if not nota_wo or not nota_wo.strip():
                                    st.error("Debes ingresar la justificación del W.O.")
                                else:
                                    registrar_resultado(st.session_state.historial, partido_sel["id"], tipo=tipo, nota_wo=nota_wo.strip())
                                    guardar_historial(st.session_state.historial)
                                    st.success("✅ W.O. registrado.")
                                    st.rerun()
                        except ValueError as e:
                            st.error(f"Error: {e}")

# ----------------------------------------------------------------------------
#  TAB 3: Ranking
# ----------------------------------------------------------------------------
with tab_ranking:
    st.subheader("🏆 Ranking acumulado de la temporada")

    # Alerta de inasistencias — solo visible para admin
    if st.session_state.es_admin:
        from resultados import jugadores_a_desactivar, inasistencias_consecutivas
        en_riesgo = [
            n for n in {p["jugador_1"]["Jugador"] for p in st.session_state.historial.get("partidos", [])} |
                       {p["jugador_2"]["Jugador"] for p in st.session_state.historial.get("partidos", [])}
            if inasistencias_consecutivas(st.session_state.historial, n) == 1
        ]
        a_desactivar = jugadores_a_desactivar(st.session_state.historial, limite=2)
        if a_desactivar:
            st.error(f"🚫 Desactivados por 2 inasistencias consecutivas: {', '.join(a_desactivar)}")
        if en_riesgo:
            st.warning(f"⚠️ En riesgo (1 inasistencia): {', '.join(en_riesgo)}")

    if not partidos_completados(st.session_state.historial):
        st.info("Aún no hay resultados cargados. Ve a la pestaña **Cargar Resultados** primero.")
    else:
        # DEBUG TEMPORAL
        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFD", s.lower()).encode("ascii","ignore").decode()
        nombres_bd = {_norm(j["Jugador"]): j["Jugador"] for j in jugadores}
        saltados = []
        for p in st.session_state.historial.get("partidos", []):
            res = p.get("resultado")
            if res is None or res.get("tipo") == "no_jugado":
                continue
            j1_raw = p["jugador_1"]["Jugador"]
            j2_raw = p["jugador_2"]["Jugador"]
            j1_found = j1_raw in {j["Jugador"] for j in jugadores} or _norm(j1_raw) in nombres_bd
            j2_found = j2_raw in {j["Jugador"] for j in jugadores} or _norm(j2_raw) in nombres_bd
            if not j1_found or not j2_found:
                saltados.append(f"{p['id']}: j1='{j1_raw}'({'❌' if not j1_found else '✅'}) j2='{j2_raw}'({'❌' if not j2_found else '✅'})")
        if saltados:
            st.warning("Partidos saltados: " + " | ".join(saltados))
        else:
            st.caption("DEBUG: Ningún partido saltado ✅")
        # FIN DEBUG
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

        st.divider()
        st.markdown("#### 👤 Ver perfil de jugador")
        jugador_perfil = st.selectbox(
            "Selecciona jugador para ver su perfil",
            options=["— Selecciona —"] + sorted([j["nombre"] for j in jugadores_db]),
            key="ranking_perfil_selector",
        )
        if jugador_perfil != "— Selecciona —":
            st.session_state["perfil_desde_ranking"] = jugador_perfil
            _jug = get_jugador_by_nombre(jugador_perfil)
            if _jug:
                _caract = _jug.get("caracteristicas") or {}
                _tel = _jug.get("telefono", "") or ""
                _partidos_jug = [
                    p for p in st.session_state.historial.get("partidos", [])
                    if (p["jugador_1"]["Jugador"] == jugador_perfil or p["jugador_2"]["Jugador"] == jugador_perfil)
                    and p["resultado"] is not None and p["resultado"]["tipo"] != "no_jugado"
                ]
                _g = sum(1 for p in _partidos_jug if p["resultado"].get("ganador") == jugador_perfil)
                _pe = sum(1 for p in _partidos_jug if p["resultado"]["tipo"] == "normal" and p["resultado"].get("ganador") != jugador_perfil)
                _wo_f = sum(1 for p in _partidos_jug if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") == jugador_perfil)
                _wo_c = sum(1 for p in _partidos_jug if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") != jugador_perfil)
                _pts = (_jug.get("puntos_base") or 0) + _g * 200 + _pe * 25 + _wo_f * 50

                with st.container():
                    st.markdown(f"### {jugador_perfil}")
                    _c1, _c2, _c3, _c4, _c5 = st.columns(5)
                    _c1.metric("PJ", len(_partidos_jug))
                    _c2.metric("G", _g)
                    _c3.metric("P", _pe)
                    _c4.metric("WO+", _wo_f)
                    _c5.metric("Puntos", _pts)

                    _info_cols = st.columns(3)
                    _info_cols[0].markdown(f"**Categoría:** {next((c for c, lst in categorias.items() if any(j['Jugador'] == jugador_perfil for j in lst)), '—')}")
                    _info_cols[1].markdown(f"**Performance:** {_jug.get('performance') or 0:.2f}")
                    if _tel:
                        _tel_limpio = _tel.replace("+", "").replace(" ", "")
                        _info_cols[2].markdown(f"**WhatsApp:** [📱 Contactar](https://wa.me/{_tel_limpio})")

                    if _caract:
                        _caract_str = " · ".join(f"**{k.replace('_', ' ').title()}:** {v}" for k, v in _caract.items() if v)
                        if _caract_str:
                            st.markdown(_caract_str)

                    with st.expander("📋 Ver historial de partidos"):
                        _filas = []
                        for p in reversed(_partidos_jug):
                            _es_j1 = p["jugador_1"]["Jugador"] == jugador_perfil
                            _rival = p["jugador_2"]["Jugador"] if _es_j1 else p["jugador_1"]["Jugador"]
                            _res = p["resultado"]
                            _gan = _res.get("ganador", "")
                            if _res["tipo"] == "normal":
                                _sets = _res.get("sets", [])
                                _marc = " / ".join(f"{s['games_1']}-{s['games_2']}" if _es_j1 else f"{s['games_2']}-{s['games_1']}" for s in _sets)
                                _rstr = "✅ G" if _gan == jugador_perfil else "❌ P"
                            else:
                                _marc = "W.O."
                                _rstr = "✅ WO+" if _gan == jugador_perfil else "❌ WO-"
                            _filas.append({"Ronda": p.get("ronda_bloque","—"), "Rival": _rival, "Resultado": _rstr, "Marcador": _marc})
                        if _filas:
                            st.dataframe(pd.DataFrame(_filas), hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------
#  TAB 4: Perfiles de jugadores
# ----------------------------------------------------------------------------
with tab_perfiles:
    st.subheader("👤 Perfil de jugador")

    nombres_activos = sorted([j["nombre"] for j in jugadores_db])
    # Pre-seleccionar si viene desde el ranking
    idx_default = 0
    if st.session_state.get("perfil_desde_ranking") in nombres_activos:
        idx_default = nombres_activos.index(st.session_state["perfil_desde_ranking"])
    jugador_nombre = st.selectbox(
        "Selecciona un jugador",
        options=nombres_activos,
        index=idx_default,
        key="perfil_selector"
    )

    if jugador_nombre:
        jug_data = get_jugador_by_nombre(jugador_nombre)
        if not jug_data:
            st.warning("Jugador no encontrado en la base de datos.")
        else:
            # ── Encabezado del perfil ──
            caract = jug_data.get("caracteristicas") or {}
            telefono = jug_data.get("telefono", "") or ""

            col_info, col_stats = st.columns([2, 3])
            with col_info:
                st.markdown(f"## {jugador_nombre}")
                st.markdown(f"**Ranking inicial:** #{jug_data['ranking']}")
                st.markdown(f"**Categoría:** {next((c for c, lst in categorias.items() if any(j['Jugador'] == jugador_nombre for j in lst)), '—')}")
                st.markdown(f"**Estado:** {'✅ Activo' if jug_data['activo'] else '❌ Inactivo'}")
                st.markdown(f"**Performance:** {jug_data.get('performance') or 0:.2f}")
                st.markdown(f"**Pts base:** {jug_data.get('puntos_base') or 0}")
                if telefono:
                    tel_limpio = telefono.replace("+", "").replace(" ", "")
                    st.markdown(f"**WhatsApp:** [📱 Contactar](https://wa.me/{tel_limpio})")
                else:
                    st.markdown("**WhatsApp:** —")

            # Calcular stats del jugador desde historial
            partidos_jugador = [
                p for p in st.session_state.historial.get("partidos", [])
                if (p["jugador_1"]["Jugador"] == jugador_nombre or
                    p["jugador_2"]["Jugador"] == jugador_nombre)
                and p["resultado"] is not None
                and p["resultado"]["tipo"] != "no_jugado"
            ]
            pj = len(partidos_jugador)
            g = sum(1 for p in partidos_jugador if p["resultado"].get("ganador") == jugador_nombre)
            pe = sum(1 for p in partidos_jugador if p["resultado"]["tipo"] == "normal" and p["resultado"].get("ganador") != jugador_nombre)
            wo_favor = sum(1 for p in partidos_jugador if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") == jugador_nombre)
            wo_contra = sum(1 for p in partidos_jugador if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") != jugador_nombre)
            pts_nuevos = g * 200 + pe * 25 + wo_favor * 50
            pts_total = (jug_data.get("puntos_base") or 0) + pts_nuevos

            # Racha actual
            racha = 0
            racha_tipo = "—"
            for p in reversed(partidos_jugador):
                es_ganador = p["resultado"].get("ganador") == jugador_nombre
                if racha == 0:
                    racha_tipo = "🟢 Victoria" if es_ganador else "🔴 Derrota"
                if (racha_tipo.startswith("🟢") and es_ganador) or (racha_tipo.startswith("🔴") and not es_ganador):
                    racha += 1
                else:
                    break

            with col_stats:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("PJ", pj)
                c2.metric("Ganados", g)
                c3.metric("Perdidos", pe)
                c4.metric("Puntos", pts_total)
                c1b, c2b, c3b, c4b = st.columns(4)
                c1b.metric("WO+", wo_favor)
                c2b.metric("WO-", wo_contra)
                c3b.metric("Racha", racha)
                c4b.metric("Tipo racha", racha_tipo)

            st.divider()

            # ── Características ──
            col_caract, col_hist = st.columns([1, 2])
            with col_caract:
                st.markdown("#### 🎾 Características")
                campos = [
                    ("mejor_golpe", "Mejor golpe", "Ej: Revés cruzado"),
                    ("estilo", "Estilo de juego", "Ej: Baseliner agresivo"),
                    ("mano", "Mano dominante", "Derecho / Zurdo"),
                    ("nota", "Nota del admin", "Observaciones generales"),
                ]
                for campo, label, placeholder in campos:
                    valor = caract.get(campo, "")
                    if valor:
                        st.markdown(f"**{label}:** {valor}")
                    else:
                        st.markdown(f"**{label}:** —")

                if st.session_state.es_admin:
                    with st.expander("✏️ Editar características"):
                        with st.form(f"form_caract_{jug_data['id']}"):
                            nuevo_tel = st.text_input(
                                "📱 Teléfono WhatsApp",
                                value=telefono,
                                placeholder="Ej: +56912345678",
                                key=f"caract_tel_{jug_data['id']}"
                            )
                            st.caption("Incluye código de país. Ej: +56 para Chile")
                            nuevas = {}
                            for campo, label, placeholder in campos:
                                nuevas[campo] = st.text_input(
                                    label,
                                    value=caract.get(campo, ""),
                                    placeholder=placeholder,
                                    key=f"caract_{campo}_{jug_data['id']}"
                                )
                            if st.form_submit_button("💾 Guardar características", type="primary", use_container_width=True):
                                guardar_caracteristicas(jug_data["id"], nuevas, telefono=nuevo_tel)
                                st.success("✅ Características guardadas.")
                                st.rerun()

            with col_hist:
                st.markdown("#### 📋 Historial de partidos")
                if not partidos_jugador:
                    st.info("Sin partidos registrados.")
                else:
                    filas = []
                    for p in reversed(partidos_jugador):
                        es_j1 = p["jugador_1"]["Jugador"] == jugador_nombre
                        rival = p["jugador_2"]["Jugador"] if es_j1 else p["jugador_1"]["Jugador"]
                        res = p["resultado"]
                        ganador = res.get("ganador", "")
                        if res["tipo"] == "normal":
                            sets = res.get("sets", [])
                            if es_j1:
                                marcador = " / ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)
                            else:
                                marcador = " / ".join(f"{s['games_2']}-{s['games_1']}" for s in sets)
                            resultado_str = "✅ G" if ganador == jugador_nombre else "❌ P"
                        elif res["tipo"] == "wo":
                            marcador = "W.O."
                            resultado_str = "✅ WO+" if ganador == jugador_nombre else "❌ WO-"
                        else:
                            marcador = "—"
                            resultado_str = "—"
                        filas.append({
                            "Ronda": p.get("ronda_bloque", "—"),
                            "Bloque": p.get("bloque", "—"),
                            "Rival": rival,
                            "Resultado": resultado_str,
                            "Marcador": marcador,
                        })
                    import pandas as pd
                    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------
#  TAB 5: Torneos
# ----------------------------------------------------------------------------
with tab_torneos:
    st.subheader("🏅 Torneos")
    sb = get_supabase()
    torneo_activo = get_torneo_activo(sb)

    # ── Sin torneo activo: crear uno ──
    if not torneo_activo:
        st.info("No hay torneo activo. Crea uno nuevo.")
        if st.session_state.es_admin:
            with st.expander("➕ Crear nuevo torneo", expanded=True):
                with st.form("form_crear_torneo"):
                    t_nombre = st.text_input("Nombre del torneo", placeholder="Ej: Copa Costa Sport 2026")
                    col_t1, col_t2 = st.columns(2)
                    t_tipo = col_t1.selectbox("Tipo", ["singles", "dobles"])
                    t_formato = col_t2.selectbox("Formato", [
                        "eliminacion", "round_robin", "grupos_eliminacion"
                    ], format_func=lambda x: {
                        "eliminacion": "Eliminación directa",
                        "round_robin": "Round Robin",
                        "grupos_eliminacion": "Grupos + Eliminación"
                    }[x])

                    st.markdown("**Puntos por victoria** (solo singles — se suman al ranking de la escalerilla)")
                    st.caption("Cada victoria en esa ronda suma los puntos configurados. Aplica para cualquier tamaño de torneo.")
                    col_p1, col_p2 = st.columns(2)
                    col_p3, col_p4 = st.columns(2)
                    col_p5, col_p6 = st.columns(2)
                    pts_final        = col_p1.number_input("Final (campeón)", min_value=0, value=500, step=50)
                    pts_semifinal    = col_p2.number_input("Semifinal", min_value=0, value=200, step=25)
                    pts_cuartos      = col_p3.number_input("Cuartos de final", min_value=0, value=100, step=25)
                    pts_octavos      = col_p4.number_input("Octavos de final", min_value=0, value=60, step=10)
                    pts_dieciseisavos = col_p5.number_input("16avos de final", min_value=0, value=30, step=10)
                    pts_treintaidosavos = col_p6.number_input("32avos / rondas previas", min_value=0, value=15, step=5,
                        help="Se aplica a 32avos, 64avos y cualquier ronda antes de 16avos")

                    col_tam1, col_tam2 = st.columns(2)
                    tam_bracket = col_tam1.selectbox(
                        "Tamaño del bracket",
                        options=[16, 32, 64, 128],
                        index=1,
                        help="Si hay más jugadores que slots, se genera una ronda previa automática."
                    )
                    col_tam2.caption("Si hay más jugadores que slots, los excedentes juegan una ronda previa. Los seeds entran directo al bracket principal.")

                    n_grupos = 4
                    if t_formato == "grupos_eliminacion":
                        n_grupos = st.number_input("Número de grupos", min_value=2, max_value=8, value=4)

                    if st.form_submit_button("🏅 Crear torneo", type="primary", use_container_width=True):
                        if not t_nombre.strip():
                            st.error("Ingresa un nombre para el torneo.")
                        else:
                            config = {
                                "tam_bracket": int(tam_bracket),
                                "puntos_por_victoria": {
                                    "final": int(pts_final),
                                    "semifinal": int(pts_semifinal),
                                    "cuartos": int(pts_cuartos),
                                    "octavos": int(pts_octavos),
                                    "dieciseisavos": int(pts_dieciseisavos),
                                    "treintaidosavos": int(pts_treintaidosavos),
                                    "sesentaicuatroavos": int(pts_treintaidosavos),
                                    "ronda_1": int(pts_treintaidosavos),
                                    "ronda_2": int(pts_dieciseisavos),
                                    "ronda_3": int(pts_octavos),
                                    "grupos": int(pts_dieciseisavos),
                                },
                                "n_grupos": int(n_grupos),
                            }
                            crear_torneo(sb, t_nombre.strip(), t_tipo, t_formato, config)
                            st.success(f"✅ Torneo '{t_nombre}' creado.")
                            st.rerun()

        # Historial de torneos finalizados
        todos_t = get_todos_torneos(sb)
        finalizados = [t for t in todos_t if t["estado"] == "finalizado"]
        if finalizados:
            st.divider()
            st.markdown("#### Torneos anteriores")
            for tf in finalizados:
                col_th_f, col_del_f = st.columns([5, 1])
                col_th_f.markdown(f"**{tf['nombre']}** — {tf['tipo']} · {tf['formato']}")
                if st.session_state.es_admin:
                    if col_del_f.button("🗑️", key=f"del_t_{tf['id']}", help="Eliminar torneo"):
                        st.session_state["confirm_eliminar_torneo"] = tf["id"]
                if st.session_state.get("confirm_eliminar_torneo") == tf["id"]:
                    st.error(f"⚠️ ¿Eliminar **{tf['nombre']}**?")
                    col_si2, col_no2 = st.columns(2)
                    if col_si2.button("Sí", key=f"si_{tf['id']}", type="primary"):
                        eliminar_torneo(sb, tf["id"])
                        st.session_state.pop("confirm_eliminar_torneo", None)
                        st.rerun()
                    if col_no2.button("No", key=f"no_{tf['id']}"):
                        st.session_state.pop("confirm_eliminar_torneo", None)
                        st.rerun()

    else:
        # ── Torneo activo ──
        t = torneo_activo
        config = t.get("config") or {}
        tipo_t = t["tipo"]
        formato_t = t["formato"]

        col_th, col_tf, col_td = st.columns([4, 1, 1])
        col_th.markdown(f"## {t['nombre']}")
        col_th.markdown(f"**{tipo_t.title()}** · {formato_t.replace('_', ' ').title()}")
        if st.session_state.es_admin:
            if col_tf.button("🏁 Finalizar", use_container_width=True):
                st.session_state["confirm_finalizar_torneo"] = t["id"]
            if col_td.button("🗑️ Eliminar", use_container_width=True):
                st.session_state["confirm_eliminar_torneo"] = t["id"]

        if st.session_state.get("confirm_finalizar_torneo") == t["id"] and st.session_state.es_admin:
            config_t = t.get("config") or {}
            if tipo_t == "singles":
                puntos_preview = calcular_puntos_torneo(partidos, participantes, config_t, tipo_t)
                if puntos_preview:
                    st.info("Se sumarán estos puntos al ranking de la escalerilla:")
                    col_prev = st.columns(min(len(puntos_preview), 4))
                    for i, (nombre, pts) in enumerate(sorted(puntos_preview.items(), key=lambda x: -x[1])):
                        col_prev[i % 4].metric(nombre, f"+{pts} pts")
                else:
                    st.info("No hay resultados completados — no se sumarán puntos.")
            else:
                puntos_preview = {}
                st.info("ℹ️ Torneo de dobles — no aplica puntos al ranking de la escalerilla.")
            col_sf1, col_sf2 = st.columns(2)
            if col_sf1.button("✅ Confirmar y finalizar", type="primary", use_container_width=True, key="btn_conf_fin"):
                if tipo_t == "singles" and puntos_preview:
                    act, no_enc = aplicar_puntos_al_ranking(sb, puntos_preview)
                    st.session_state.jugadores_supabase = get_jugadores()
                    if no_enc:
                        st.warning(f"No encontrados en escalerilla: {', '.join(no_enc)}")
                    finalizar_torneo(sb, t["id"])
                    st.session_state.pop("confirm_finalizar_torneo", None)
                    st.success("✅ Torneo finalizado. Puntos aplicados al ranking de la escalerilla.")
                else:
                    finalizar_torneo(sb, t["id"])
                    st.session_state.pop("confirm_finalizar_torneo", None)
                    st.success("✅ Torneo de dobles finalizado. Sin impacto en el ranking de la escalerilla.")
                st.rerun()
            if col_sf2.button("Cancelar", use_container_width=True, key="btn_canc_fin"):
                st.session_state.pop("confirm_finalizar_torneo", None)
                st.rerun()

        # Confirmación eliminación
        if st.session_state.get("confirm_eliminar_torneo") == t["id"]:
            st.error(f"⚠️ ¿Seguro que quieres eliminar **{t['nombre']}** y todos sus datos? Esta acción no se puede deshacer.")
            col_si, col_no = st.columns(2)
            if col_si.button("Sí, eliminar", type="primary", use_container_width=True):
                eliminar_torneo(sb, t["id"])
                st.session_state.pop("confirm_eliminar_torneo", None)
                st.success("Torneo eliminado.")
                st.rerun()
            if col_no.button("Cancelar", use_container_width=True):
                st.session_state.pop("confirm_eliminar_torneo", None)
                st.rerun()

        participantes = get_participantes(sb, t["id"])
        partidos = get_partidos_torneo(sb, t["id"])
        completados_t = [p for p in partidos if p.get("ganador_id")]
        pendientes_t = [p for p in partidos if not p.get("ganador_id")]

        st_t1, st_t2, st_t3, st_t4 = st.tabs(["👥 Participantes / Sorteo", "🎯 Partidos", "🏆 Bracket", "📊 Resultados"])

        # ── Participantes ──
        with st_t1:
            c1t, c2t, c3t = st.columns(3)
            c1t.metric("Participantes", len(participantes))
            c2t.metric("Partidos jugados", len(completados_t))
            c3t.metric("Pendientes", len(pendientes_t))

            st.divider()
            if participantes:
                filas_p = []
                for p in participantes:
                    filas_p.append({
                        "Seed": p.get("seed") or "—",
                        "Participante": nombre_participante(p, tipo_t),
                        "Grupo": p.get("grupo") or "—",
                    })
                st.dataframe(pd.DataFrame(filas_p), hide_index=True, use_container_width=True)

            if st.session_state.es_admin:
                st.divider()
                st.markdown("#### Cabezas de serie")

                if participantes:
                    n_part = len(participantes)
                    tam = config.get("tam_bracket", 0)

                    # Selector de cuántos cabezas de serie
                    col_ns, col_info_ns = st.columns([1, 3])
                    n_seeds = col_ns.number_input(
                        "¿Cuántos cabezas de serie?",
                        min_value=0, max_value=min(16, n_part),
                        value=min(4, n_part),
                        step=1,
                        key="n_cabezas_serie",
                        help="Los primeros N del ranking serán seeds automáticamente"
                    )
                    col_info_ns.caption(
                        f"Los primeros **{int(n_seeds)}** jugadores del ranking serán seeds 1..{int(n_seeds)}. "
                        f"Los seeds reciben BYE si hay más slots que jugadores."
                    )

                    # Aplicar seeds automáticos por ranking
                    if st.button("✅ Asignar seeds por ranking", use_container_width=True,
                                 disabled=bool(partidos), key="btn_asignar_seeds"):
                        # Ordenar participantes por ranking (seed actual o posición en lista)
                        partic_ordenados = sorted(participantes, key=lambda x: x.get("seed") or 999)
                        # Resetear todos a 0
                        for p in participantes:
                            actualizar_seed(sb, p["id"], 0)
                        # Asignar seeds 1..N a los primeros N
                        for i, p in enumerate(partic_ordenados[:int(n_seeds)], start=1):
                            actualizar_seed(sb, p["id"], i)
                        st.success(f"✅ Seeds 1-{int(n_seeds)} asignados a los primeros {int(n_seeds)} jugadores.")
                        st.rerun()

                    # Mostrar lista con seeds actuales
                    with st.expander("Ver/editar seeds manualmente"):
                        st.caption("Puedes ajustar seeds individuales si necesitas cambiar alguno.")
                        partic_sorted = sorted(participantes, key=lambda x: x.get("seed") or 999)
                        for p in partic_sorted:
                            col_nom, col_seed, col_btn = st.columns([4, 2, 1])
                            seed_actual = p.get("seed") or 0
                            col_nom.markdown(
                                f"**[{seed_actual}]** {nombre_participante(p, tipo_t)}"
                                if seed_actual else nombre_participante(p, tipo_t)
                            )
                            nuevo_seed = col_seed.number_input(
                                "Seed", min_value=0, max_value=256,
                                value=int(seed_actual),
                                key=f"seed_{p['id']}",
                                label_visibility="collapsed"
                            )
                            if col_btn.button("💾", key=f"saveseed_{p['id']}", help="Guardar"):
                                actualizar_seed(sb, p["id"], int(nuevo_seed))
                                st.rerun()

                st.divider()
                col_sorteo, col_info_s = st.columns([1, 2])
                with col_sorteo:
                    if st.button("🎲 Hacer sorteo", type="primary", use_container_width=True,
                                 disabled=bool(partidos),
                                 help="Genera el orden del bracket respetando seeds"):
                        # Recargar participantes con seeds actualizados
                        participantes_fresh = get_participantes(sb, t["id"])
                        aplicar_sorteo_supabase(sb, t["id"], participantes_fresh)
                        st.success("✅ Sorteo realizado. Ahora genera los partidos.")
                        st.rerun()
                with col_info_s:
                    tam = config.get("tam_bracket", 0)
                    if tam and participantes:
                        n_part = len(participantes)
                        n_seeds_act = len([p for p in participantes if (p.get("seed") or 0) > 0])
                        n_byes = tam - n_part
                        if n_part > tam:
                            n_previa = n_part - tam + n_seeds_act
                            st.info(f"ℹ️ {n_part} jugadores en bracket de {tam}. {n_previa} no-seeds jugarán **ronda previa**.")
                        elif n_byes > 0:
                            st.info(f"ℹ️ {n_part} jugadores en bracket de {tam}. {min(n_byes, n_seeds_act)} seeds recibirán **BYE** automático.")
                    if partidos:
                        st.warning("Ya hay partidos generados — el sorteo está bloqueado.")

                st.divider()
                st.markdown("#### Importar participantes desde Excel")
                if tipo_t == "singles":
                    st.caption("Columnas requeridas: **Jugador**, **Seed** (opcional, 0 si no tiene seed).")
                else:
                    st.caption("Columnas requeridas: **Jugador1**, **Jugador2**, **Seed** (opcional). Una fila = una pareja.")

                archivo_part = st.file_uploader(
                    "Subir Excel de participantes",
                    type=["xlsx", "xls"],
                    key="upload_participantes",
                )
                if archivo_part:
                    try:
                        df_part = pd.read_excel(archivo_part, sheet_name=0)
                        col_req = "Jugador" if tipo_t == "singles" else "Jugador1"
                        if col_req not in df_part.columns:
                            st.error(f"Columna requerida: '{col_req}'")
                        else:
                            cols_show = [col_req]
                            if tipo_t == "dobles" and "Jugador2" in df_part.columns:
                                cols_show.append("Jugador2")
                            if "Seed" in df_part.columns:
                                cols_show.append("Seed")
                            st.dataframe(df_part[cols_show].head(10), hide_index=True, use_container_width=True)
                            st.caption(f"{len(df_part)} {'parejas' if tipo_t == 'dobles' else 'jugadores'} en el archivo")
                            if st.button("⬆️ Importar todos", type="primary", use_container_width=True, key="btn_import_part"):
                                importados = 0
                                errores_imp = []
                                for _, row in df_part.iterrows():
                                    if tipo_t == "singles":
                                        nombre = str(row.get("Jugador", "")).strip()
                                        if not nombre or nombre == "nan":
                                            continue
                                        nombre2 = None
                                    else:
                                        nombre = str(row.get("Jugador1", "")).strip()
                                        nombre2 = str(row.get("Jugador2", "")).strip()
                                        if not nombre or nombre == "nan":
                                            continue
                                        if not nombre2 or nombre2 == "nan":
                                            nombre2 = None
                                    seed_val = 0
                                    if "Seed" in df_part.columns and str(row.get("Seed","")) not in ("nan",""):
                                        try:
                                            seed_val = int(row["Seed"])
                                        except:
                                            seed_val = 0
                                    try:
                                        agregar_participante(sb, t["id"], nombre, nombre2, seed_val)
                                        importados += 1
                                    except Exception as e:
                                        errores_imp.append(nombre)
                                st.success(f"✅ {importados} {'parejas' if tipo_t == 'dobles' else 'participantes'} importados.")
                                if errores_imp:
                                    st.warning(f"No se pudieron importar: {', '.join(errores_imp)}")
                                st.rerun()
                    except Exception as e:
                        st.error(f"Error leyendo Excel: {e}")

                st.divider()
                st.markdown("#### Agregar participante manualmente")
                nombres_disp = sorted([j["nombre"] for j in jugadores_db])

                with st.form("form_add_participante"):
                    col_a1, col_a2, col_a3 = st.columns([3, 3, 1])
                    j1_sel = col_a1.selectbox(
                        "Jugador 1" if tipo_t == "singles" else "Pareja — Jugador 1",
                        options=["— Externo —"] + nombres_disp,
                        key="add_j1"
                    )
                    j1_ext = col_a1.text_input("Nombre externo J1", key="add_j1_ext",
                        placeholder="Si no está en la lista") if j1_sel == "— Externo —" else None

                    if tipo_t == "dobles":
                        j2_sel = col_a2.selectbox("Jugador 2", options=["— Externo —"] + nombres_disp, key="add_j2")
                        j2_ext = col_a2.text_input("Nombre externo J2", key="add_j2_ext",
                            placeholder="Si no está en la lista") if j2_sel == "— Externo —" else None
                    else:
                        j2_sel = None
                        j2_ext = None

                    seed_val = col_a3.number_input("Seed", min_value=1, max_value=64, value=len(participantes)+1, key="add_seed")

                    if st.form_submit_button("➕ Agregar", type="primary", use_container_width=True):
                        nombre_j1 = (j1_ext or "").strip() if j1_sel == "— Externo —" else j1_sel
                        nombre_j2 = None
                        if tipo_t == "dobles":
                            nombre_j2 = (j2_ext or "").strip() if j2_sel == "— Externo —" else j2_sel
                        if not nombre_j1:
                            st.error("Ingresa el nombre del jugador.")
                        else:
                            agregar_participante(sb, t["id"], nombre_j1, nombre_j2, int(seed_val))
                            st.success(f"✅ {nombre_j1} agregado.")
                            st.rerun()

                if participantes and not partidos:
                    st.divider()
                    st.markdown("#### Generar partidos")
                    if st.button("🎯 Generar bracket / partidos", type="primary", use_container_width=True, key="btn_gen_bracket"):
                        if formato_t == "eliminacion":
                            generar_bracket_eliminacion(sb, t["id"], participantes, tipo_t, config)
                        elif formato_t == "round_robin":
                            generar_round_robin(sb, t["id"], participantes)
                        elif formato_t == "grupos_eliminacion":
                            generar_grupos(sb, t["id"], participantes, config.get("n_grupos", 4))
                        st.success("✅ Partidos generados.")
                        st.rerun()

        # ── Partidos ──
        with st_t2:
            if not partidos:
                st.info("Aún no hay partidos generados. Ve a **Participantes** y genera el bracket.")
            else:
                # Agrupar por fase
                fases = list(dict.fromkeys(p["fase"] for p in partidos))
                for fase in fases:
                    partidos_fase = [p for p in partidos if p["fase"] == fase]
                    grupos_fase = list(dict.fromkeys(p.get("grupo") or "" for p in partidos_fase))

                    st.markdown(f"#### {fase.replace('_', ' ').title()}")

                    for grupo in grupos_fase:
                        if grupo:
                            st.markdown(f"**Grupo {grupo}**")
                        pts_fase = [p for p in partidos_fase if (p.get("grupo") or "") == grupo]

                        for partido in pts_fase:
                            p1 = partido.get("participante1") or {}
                            p2 = partido.get("participante2") or {}
                            gan = partido.get("ganador") or {}
                            n1 = nombre_participante(p1, tipo_t)
                            n2 = nombre_participante(p2, tipo_t)
                            gan_n = nombre_participante(gan, tipo_t) if gan else None
                            sets = (partido.get("resultado") or {}).get("sets", [])
                            marcador = " / ".join(f"{s['games_1']}-{s['games_2']}" for s in sets) if sets else "—"

                            col_n1, col_vs, col_n2, col_res, col_btn = st.columns([3, 1, 3, 2, 1])
                            col_n1.markdown(f"{'**' if gan_n == n1 else ''}{n1}{'**' if gan_n == n1 else ''}")
                            col_vs.markdown("vs")
                            col_n2.markdown(f"{'**' if gan_n == n2 else ''}{n2}{'**' if gan_n == n2 else ''}")
                            col_res.markdown(f"{'✅ ' if gan_n else ''}{marcador}")

                            if st.session_state.es_admin:
                                if col_btn.button("📝", key=f"edit_t_{partido['id']}"):
                                    st.session_state["partido_torneo_sel"] = partido["id"]

                    st.divider()

                # Formulario de resultado
                if st.session_state.es_admin and st.session_state.get("partido_torneo_sel"):
                    pid_sel = st.session_state["partido_torneo_sel"]
                    partido_sel = next((p for p in partidos if p["id"] == pid_sel), None)
                    if partido_sel:
                        p1 = partido_sel.get("participante1") or {}
                        p2 = partido_sel.get("participante2") or {}
                        n1 = nombre_participante(p1, tipo_t)
                        n2 = nombre_participante(p2, tipo_t)

                        st.markdown(f"#### Ingresar resultado: {n1} vs {n2}")
                        with st.form(f"form_res_torneo_{pid_sel}"):
                            sets = []
                            for i, label in enumerate(["Set 1", "Set 2", "Set 3 (Tie-break)"]):
                                st.markdown(f"**{label}**")
                                cs1, cs2 = st.columns(2)
                                max_val = 99 if i == 2 else 7
                                g1 = cs1.number_input(f"{n1}", min_value=0, max_value=max_val, value=0, key=f"tg1_{pid_sel}_{i}")
                                g2 = cs2.number_input(f"{n2}", min_value=0, max_value=max_val, value=0, key=f"tg2_{pid_sel}_{i}")
                                sets.append({"games_1": int(g1), "games_2": int(g2)})

                            col_f1, col_f2 = st.columns(2)
                            if col_f1.form_submit_button("💾 Guardar", type="primary", use_container_width=True):
                                s1, s2, s3 = sets
                                sets_1 = sum(1 for s in [s1, s2] if s["games_1"] > s["games_2"])
                                sets_2 = sum(1 for s in [s1, s2] if s["games_2"] > s["games_1"])
                                sets_guardar = [s1, s2]
                                if sets_1 == 1 and sets_2 == 1:
                                    sets_guardar.append(s3)
                                sets_1_total = sum(1 for s in sets_guardar if s["games_1"] > s["games_2"])
                                sets_2_total = sum(1 for s in sets_guardar if s["games_2"] > s["games_1"])
                                gan_id = p1["id"] if sets_1_total > sets_2_total else p2["id"]
                                registrar_resultado_torneo(sb, pid_sel, gan_id, sets_guardar)
                                st.session_state.pop("partido_torneo_sel", None)
                                st.success("✅ Resultado guardado.")
                                st.rerun()
                            if col_f2.form_submit_button("Cancelar", use_container_width=True):
                                st.session_state.pop("partido_torneo_sel", None)
                                st.rerun()

        # ── Bracket visual ──
        with st_t3:
            st.subheader("🏆 Cuadro del torneo")

            if not partidos:
                st.info("Genera los partidos primero en la pestaña Participantes.")
            else:
                # Generar SVG según formato
                if formato_t == "eliminacion":
                    svg_bracket = generar_svg_eliminacion(partidos, participantes, tipo_t, t["nombre"])
                    svgs_list = [svg_bracket]
                elif formato_t == "round_robin":
                    svg_bracket = generar_svg_round_robin(partidos, participantes, tipo_t, t["nombre"])
                    svgs_list = [svg_bracket]
                else:
                    svgs_list = generar_svg_grupos(partidos, participantes, tipo_t, t["nombre"])
                    svg_bracket = svgs_list[0] if svgs_list else ""

                # Mostrar SVG con scroll horizontal para brackets grandes
                for svg in svgs_list:
                    st.markdown(
                        f'<div style="overflow-x:auto;overflow-y:auto;max-height:600px;border-radius:12px;border:1px solid #2A2F3E">{svg}</div>',
                        unsafe_allow_html=True
                    )
                    st.divider()

                st.divider()

                # Exportar PDF
                col_pdf1, col_pdf2 = st.columns([2, 3])
                with col_pdf1:
                    subtitulo_pdf = f"{tipo_t.title()} · {formato_t.replace('_', ' ').title()} · {datetime.now().strftime('%d/%m/%Y')}"
                    if st.button("📄 Generar PDF brandeado", type="primary", use_container_width=True):
                        with st.spinner("Generando PDF..."):
                            try:
                                pdf_bytes = generar_pdf_bracket_visual(
                                    partidos=partidos,
                                    titulo=t["nombre"],
                                    subtitulo=subtitulo_pdf,
                                    tipo=tipo_t,
                                    logo_path="assets/logo.png",
                                    participantes=participantes,
                                    config=config,
                                )
                                st.session_state["pdf_bracket"] = pdf_bytes
                                st.success("✅ PDF listo para descargar.")
                            except Exception as e:
                                st.error(f"Error generando PDF: {e}")

                if st.session_state.get("pdf_bracket"):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=st.session_state["pdf_bracket"],
                        file_name=f"costa_sport_{t['nombre'].replace(' ','_')}_{timestamp}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                    st.caption("Comparte el PDF por WhatsApp para que todos vean el cuadro actualizado.")

        # ── Resultados / Tabla ──
        with st_t4:
            if not completados_t:
                st.info("Aún no hay resultados registrados.")
            else:
                if formato_t in ("round_robin", "grupos_eliminacion"):
                    grupos_unicos = list(dict.fromkeys(
                        p.get("grupo") or "A" for p in partidos if p["fase"] in ("grupos", "ronda_1") or not p["fase"].startswith("ronda_") == False
                    ))
                    # Tablas por grupo
                    for grupo in grupos_unicos:
                        if grupo:
                            st.markdown(f"#### Grupo {grupo}")
                        tabla = calcular_tabla_grupo(partidos, grupo or "A", tipo_t)
                        if tabla:
                            st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True)
                        st.divider()

                # Ganadores por fase para eliminación
                fases_elim = [f for f in dict.fromkeys(p["fase"] for p in partidos) if "ronda" not in f]
                for fase in fases_elim:
                    pf = [p for p in completados_t if p["fase"] == fase]
                    if pf:
                        st.markdown(f"**{fase.replace('_',' ').title()}**")
                        for p in pf:
                            gan = p.get("ganador") or {}
                            sets = (p.get("resultado") or {}).get("sets", [])
                            marc = " / ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)
                            st.markdown(f"🏆 {nombre_participante(gan, tipo_t)} — {marc}")

# ----------------------------------------------------------------------------
#  TAB 6: Gestión de Jugadores
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
        # ── Buscador y filtros ──
        col_bus, col_fil = st.columns([3, 2])
        busqueda = col_bus.text_input("🔍 Buscar jugador", placeholder="Nombre...", key="busqueda_jugador")
        filtro_estado = col_fil.radio("Mostrar", ["Todos", "Activos", "Inactivos"], horizontal=True, key="filtro_estado")

        # Aplicar filtros
        lista_filtrada = todos
        if busqueda:
            lista_filtrada = [j for j in lista_filtrada if busqueda.lower() in j["nombre"].lower()]
        if filtro_estado == "Activos":
            lista_filtrada = [j for j in lista_filtrada if j["activo"]]
        elif filtro_estado == "Inactivos":
            lista_filtrada = [j for j in lista_filtrada if not j["activo"]]

        if not lista_filtrada:
            st.info("No se encontraron jugadores con esos filtros.")
        else:
            st.caption(f"Mostrando {len(lista_filtrada)} de {len(todos)} jugadores")
            for j in lista_filtrada:
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


    # ── Importar Puntos Base y Performance ──
    st.markdown("#### 📊 Puntos base y Performance")
    st.caption("Actualiza los puntos históricos y el factor de desempate de cada jugador.")

    imp_tab1, imp_tab2 = st.tabs(["📂 Importar desde Excel", "✏️ Editar en tabla"])

    with imp_tab1:
        st.markdown("El Excel debe tener columnas: **Jugador**, **Puntaje**, **Performance**")
        archivo_pts = st.file_uploader(
            "Subir Excel de puntos",
            type=["xlsx", "xls"],
            key="upload_puntos",
        )
        if archivo_pts:
            try:
                df_pts = pd.read_excel(archivo_pts, sheet_name=0)
                # Limpiar espacios en nombres de columnas
                df_pts.columns = [c.strip() for c in df_pts.columns]
                cols_req = {"Jugador", "Puntaje", "Performance"}
                if not cols_req.issubset(set(df_pts.columns)):
                    st.error(f"Columnas requeridas: {cols_req}. Encontradas: {list(df_pts.columns)}")
                else:
                    st.dataframe(df_pts[["Jugador", "Puntaje", "Performance"]].head(10), hide_index=True, use_container_width=True)
                    if st.button("💾 Importar puntos y performance", type="primary", use_container_width=True, key="btn_import_pts"):
                        sb = get_supabase()
                        actualizados = 0
                        no_encontrados = []
                        for _, row in df_pts.iterrows():
                            nombre = str(row["Jugador"]).strip()
                            jug = next((j for j in todos if j["nombre"].lower() == nombre.lower()), None)
                            if jug:
                                data = {}
                                if "Puntaje" in df_pts.columns and str(row["Puntaje"]) not in ("nan", ""):
                                    try: data["puntos_base"] = int(row["Puntaje"])
                                    except: pass
                                if "Performance" in df_pts.columns and str(row["Performance"]) not in ("nan", ""):
                                    try: data["performance"] = float(row["Performance"])
                                    except: pass
                                if data:
                                    sb.table("jugadores").update(data).eq("id", jug["id"]).execute()
                                    actualizados += 1
                            else:
                                no_encontrados.append(nombre)
                        st.session_state.jugadores_supabase = get_jugadores()
                        st.success(f"✅ {actualizados} jugadores actualizados.")
                        if no_encontrados:
                            st.warning(f"No encontrados en BD: {', '.join(no_encontrados)}")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al leer el Excel: {e}")

    with imp_tab2:
        st.caption("Edita individualmente el puntaje base y performance de cada jugador.")
        todos_refresh = get_todos_jugadores()
        jugador_sel = st.selectbox(
            "Selecciona jugador",
            options=todos_refresh,
            format_func=lambda j: f"#{j['ranking']} {j['nombre']} — Pts base: {j.get('puntos_base') or 0} | Perf: {j.get('performance') or 0}",
            key="sel_jugador_pts"
        )
        if jugador_sel:
            with st.form("form_editar_pts"):
                col_p, col_f = st.columns(2)
                nuevo_pts = col_p.number_input(
                    "Puntos base",
                    min_value=0, max_value=99999,
                    value=int(jugador_sel.get("puntos_base") or 0),
                    step=25,
                    key="input_pts_base"
                )
                nuevo_perf = col_f.number_input(
                    "Performance",
                    min_value=0.0, max_value=1.0,
                    value=float(jugador_sel.get("performance") or 0.0),
                    step=0.01,
                    format="%.2f",
                    key="input_perf"
                )
                if st.form_submit_button("💾 Guardar", type="primary", use_container_width=True):
                    sb = get_supabase()
                    sb.table("jugadores").update({
                        "puntos_base": int(nuevo_pts),
                        "performance": float(nuevo_perf),
                    }).eq("id", jugador_sel["id"]).execute()
                    st.session_state.jugadores_supabase = get_jugadores()
                    st.success(f"✅ {jugador_sel['nombre']} actualizado — Pts: {nuevo_pts} | Perf: {nuevo_perf}")
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
