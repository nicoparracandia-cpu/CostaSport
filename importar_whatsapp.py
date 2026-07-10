"""
Módulo: importar resultados desde un export de WhatsApp (.txt) — Costa Sport
---------------------------------------------------------------------------
Se llama desde app.py dentro de una pestaña:

    import importar_whatsapp
    ...
    with tab_whatsapp:
        importar_whatsapp.render()

Flujo:
  1. En WhatsApp: chat del grupo -> mas -> Exportar chat -> SIN ARCHIVOS.
  2. Subes el .txt.
  3. Se detectan mensajes con marcador de tenis (6-3 6-4, 7-6(5), 10-8, WO...).
  4. Match difuso de nombres contra los jugadores del club.
  5. Revisas/corriges en la tabla y cargas a `resultados_forms` (staging).
     Luego los aplicas al ranking desde la pagina de resultados pendientes.
"""

import re
import difflib

import streamlit as st


# ---------------------------------------------------------------------------
# Conexion / datos  -> reutiliza tus modulos existentes (db.py, resultados.py)
# ---------------------------------------------------------------------------
def _get_supabase():
    """Cliente Supabase desde tu db.py."""
    from db import get_supabase
    return get_supabase()


def _cargar_jugadores() -> list[str]:
    """Nombres de todos los jugadores (activos e inactivos) para el match."""
    try:
        from db import get_todos_jugadores
        return [j["nombre"] if isinstance(j, dict) else str(j)
                for j in get_todos_jugadores()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Parseo del export de WhatsApp (Android e iOS)
# ---------------------------------------------------------------------------
RE_ANDROID = re.compile(
    r"^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}),?\s+(\d{1,2}:\d{2})\s*[-\u2013]\s*([^:]+):\s(.*)$"
)
RE_IOS = re.compile(
    r"^\[(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}),?\s+(\d{1,2}:\d{2})(?::\d{2})?\]\s*([^:]+):\s(.*)$"
)

MENSAJES_SISTEMA = (
    "cifrados de extremo a extremo",
    "Multimedia omitido", "imagen omitida", "video omitido",
    "sticker omitido", "audio omitido", "GIF omitido",
    "Se elimino este mensaje", "cambio el asunto",
    "anadio a", "salio del grupo",
)


def parsear_chat(texto: str) -> list[dict]:
    mensajes = []
    for linea in texto.splitlines():
        linea = linea.strip("\u200e\u200f \ufeff")
        if not linea:
            continue
        m = RE_ANDROID.match(linea) or RE_IOS.match(linea)
        if m:
            fecha, hora, autor, msg = m.groups()
            mensajes.append({"fecha": fecha, "hora": hora,
                             "autor": autor.strip(), "mensaje": msg.strip()})
        elif mensajes:
            mensajes[-1]["mensaje"] += " " + linea
    return [
        m for m in mensajes
        if not any(s.lower() in m["mensaje"].lower() for s in MENSAJES_SISTEMA)
    ]


# ---------------------------------------------------------------------------
# Deteccion de marcadores de tenis
# ---------------------------------------------------------------------------
RE_SET = re.compile(r"\b(\d{1,2})\s*[-/]\s*(\d{1,2})(\s*\(\d+\))?")
RE_WO = re.compile(r"\bw\.?\s?o\.?\b", re.IGNORECASE)


def es_set_valido(a: int, b: int) -> bool:
    """Reglas de tenis: 6-0..6-4, 7-5, 7-6, super TB 10-x / gana por 2.
    Rechaza fechas (12-05), horas y numeros sueltos."""
    hi, lo = max(a, b), min(a, b)
    if hi == 6 and lo <= 4:
        return True
    if hi == 7 and lo in (5, 6):
        return True
    if hi == 10 and lo <= 8:
        return True
    if 10 < hi <= 20 and hi - lo == 2:
        return True
    return False


def extraer_marcador(msg: str) -> str | None:
    if RE_WO.search(msg):
        return "WO"
    validos = []
    for a, b, tb in RE_SET.findall(msg):
        a, b = int(a), int(b)
        if not es_set_valido(a, b):
            continue
        validos.append(f"{a}-{b}{tb.strip() if tb else ''}")
    return ", ".join(validos) if validos else None


def match_jugador(texto: str, jugadores: list[str], excluir: str = "") -> str:
    if not jugadores:
        return ""
    texto_low = texto.lower()
    candidatos = [j for j in jugadores if j != excluir]
    puntajes = []
    for j in candidatos:
        partes = j.lower().split()
        hits = sum(1 for p in partes if len(p) > 2 and p in texto_low)
        if hits:
            puntajes.append((hits, len(j), j))
    if puntajes:
        puntajes.sort(reverse=True)
        return puntajes[0][2]
    mejor, score = "", 0.0
    for w in re.findall(r"[A-Za-z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]{3,}", texto):
        low = [c.lower() for c in candidatos]
        res = difflib.get_close_matches(w.lower(), low, n=1, cutoff=0.8)
        if res:
            s = difflib.SequenceMatcher(None, w.lower(), res[0]).ratio()
            if s > score:
                mejor, score = candidatos[low.index(res[0])], s
    return mejor


def normalizar_autor(autor: str, jugadores: list[str]) -> str:
    if not jugadores:
        return autor
    res = difflib.get_close_matches(autor, jugadores, n=1, cutoff=0.5)
    return res[0] if res else autor


# ---------------------------------------------------------------------------
# UI  -> llamar desde app.py: importar_whatsapp.render()
# ---------------------------------------------------------------------------
def render(jugadores: list[str] | None = None):
    st.subheader("Importar resultados desde WhatsApp")
    st.caption("Exporta el chat del grupo (Exportar chat -> Sin archivos) y sube el .txt.")

    if jugadores is None:
        jugadores = _cargar_jugadores()
    if jugadores:
        st.caption(f"{len(jugadores)} jugadores cargados para el match de nombres.")
    else:
        st.warning("No pude cargar jugadores automaticamente. Pegalos abajo (uno por linea).")
        manual = st.text_area("Jugadores", height=150, key="wa_manual")
        jugadores = [l.strip() for l in manual.splitlines() if l.strip()]

    c1, c2 = st.columns([2, 1])
    with c1:
        archivo = st.file_uploader("Export del chat (.txt)", type=["txt"], key="wa_file")
    with c2:
        jornada = st.text_input("Jornada a asignar", value="", key="wa_jornada")

    if not archivo:
        return

    texto = archivo.read().decode("utf-8", errors="replace")
    mensajes = parsear_chat(texto)
    st.caption(f"Se leyeron {len(mensajes)} mensajes.")

    filas = []
    for m in mensajes:
        marcador = extraer_marcador(m["mensaje"])
        if not marcador:
            continue
        reporta = normalizar_autor(m["autor"], jugadores)
        rival = match_jugador(m["mensaje"], jugadores, excluir=reporta)
        filas.append({
            "incluir": True,
            "fecha": m["fecha"],
            "reporta": reporta,
            "rival": rival,
            "marcador": marcador,
            "mensaje_original": m["mensaje"][:120],
        })

    if not filas:
        st.info("No se detectaron mensajes con marcadores de tenis.")
        return

    st.write(f"**{len(filas)} posibles resultados** — corrige y desmarca los que no correspondan.")

    col_cfg = {
        "incluir": st.column_config.CheckboxColumn("Cargar", default=True),
        "mensaje_original": st.column_config.TextColumn("Mensaje original", disabled=True),
    }
    if jugadores:
        col_cfg["reporta"] = st.column_config.SelectboxColumn("Reporta", options=jugadores)
        col_cfg["rival"] = st.column_config.SelectboxColumn("Rival", options=jugadores)

    editadas = st.data_editor(
        filas, use_container_width=True, num_rows="dynamic",
        column_config=col_cfg, key="wa_editor",
    )

    seleccionadas = [f for f in editadas if f.get("incluir")]
    incompletas = [f for f in seleccionadas if not f.get("reporta") or not f.get("rival")]
    if incompletas:
        st.warning(f"{len(incompletas)} fila(s) sin reporta o rival — completalas o desmarcalas.")

    if st.button(
        f"Cargar {len(seleccionadas)} resultado(s) a pendientes",
        type="primary", disabled=not seleccionadas or bool(incompletas), key="wa_btn",
    ):
        registros = [{
            "jornada": jornada or None,
            "reporta": f["reporta"],
            "rival": f["rival"],
            "marcador": f["marcador"],
            "procesado": False,
        } for f in seleccionadas]
        try:
            _get_supabase().table("resultados_forms").insert(registros).execute()
            st.success(f"{len(registros)} resultado(s) en la bandeja de pendientes.")
            st.balloons()
        except Exception as e:
            st.error(f"Error al insertar en Supabase: {e}")
