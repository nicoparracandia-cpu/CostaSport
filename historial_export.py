"""
historial_export.py — Costa Sport
---------------------------------
Descarga de resultados históricos de la escalerilla.

Fuente de datos: historial["partidos"] (tabla `historial` de Supabase,
id=1, columna `data`). Cada partido trae:
    id, fecha_generado, tipo, bloque, ronda_bloque, ciclo_bloque,
    jugador_1 {Ranking, Jugador}, jugador_2 {...}, resultado {...}

Expone:
  - partidos_a_dataframe()      → detalle plano de partidos
  - filtrar_partidos()          → filtros combinables (fechas/jugadores/fases)
  - fases_disponibles()         → fases (bloques) presentes en el historial
  - calcular_estadisticas()     → resumen de un jugador único
  - resumen_a_dataframe()       → resumen como tabla Métrica/Valor
  - exportar_csv/excel/pdf()    → bytes en memoria, sin escribir a disco
"""
from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from bracket_pdf import C_BLUE, C_CARD, C_DARK, C_MUTED, C_WHITE, C_YELLOW
from resultados import formatear_marcador

LOGO_PATH = Path("assets/logo.png")

# Columnas del detalle que van al PDF (el resto solo a CSV/Excel).
COLUMNAS_PDF = [
    "Fecha", "Ronda", "Jugador 1", "Jugador 2",
    "Ganador", "Marcador", "Estado",
]


# ============================================================================
#  Lectura del historial
# ============================================================================
def _fecha_partido(partido: dict) -> str:
    """Fecha de referencia: la del resultado si existe, si no la de generación."""
    res = partido.get("resultado") or {}
    return res.get("fecha_registro") or partido.get("fecha_generado") or ""


def _a_date(valor: str) -> date | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor).date()
    except ValueError:
        return None


def _estado(partido: dict) -> str:
    res = partido.get("resultado")
    if res is None:
        return "Pendiente"
    if res["tipo"] == "no_jugado":
        return "No jugado"
    if res["tipo"] == "wo":
        return "W.O."
    return "Jugado"


def _conteo_sets(res: dict | None) -> tuple[int, int, int, int]:
    """(sets_1, sets_2, games_1, games_2) desde la óptica del jugador 1."""
    if not res or res.get("tipo") != "normal":
        return 0, 0, 0, 0
    sets = res.get("sets") or []
    s1 = sum(1 for s in sets if s["games_1"] > s["games_2"])
    s2 = sum(1 for s in sets if s["games_2"] > s["games_1"])
    g1 = sum(s["games_1"] for s in sets)
    g2 = sum(s["games_2"] for s in sets)
    return s1, s2, g1, g2


def fases_disponibles(historial: dict) -> list[str]:
    """Fases/bloques presentes en el historial, ordenadas."""
    return sorted({
        p.get("bloque") for p in historial.get("partidos", [])
        if p.get("bloque")
    })


def ciclos_disponibles(historial: dict) -> list[int]:
    """Ciclos (temporadas internas) presentes en el historial."""
    return sorted({
        int(p["ciclo_bloque"]) for p in historial.get("partidos", [])
        if p.get("ciclo_bloque") is not None
    })


def jugadores_del_historial(historial: dict) -> list[str]:
    """Nombres que aparecen en algún partido del historial."""
    nombres = set()
    for p in historial.get("partidos", []):
        nombres.add(p["jugador_1"]["Jugador"])
        nombres.add(p["jugador_2"]["Jugador"])
    return sorted(nombres)


# ============================================================================
#  Filtros
# ============================================================================
def filtrar_partidos(
    historial: dict,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    jugadores: list[str] | None = None,
    fases: list[str] | None = None,
    ciclos: list[int] | None = None,
    incluir_no_jugados: bool = False,
    incluir_pendientes: bool = False,
    solo_no_jugados: bool = False,
) -> list[dict]:
    """
    Filtros combinables sobre historial["partidos"].
    Sin ningún filtro → partidos resueltos (jugados y W.O.). Los partidos
    no jugados y los pendientes se suman con sus flags respectivos.
    solo_no_jugados deja únicamente los no jugados e ignora esos dos flags.
    """
    jugadores = set(jugadores or [])
    fases = set(fases or [])
    ciclos = set(ciclos or [])

    salida = []
    for p in historial.get("partidos", []):
        res = p.get("resultado")
        if solo_no_jugados:
            if res is None or res["tipo"] != "no_jugado":
                continue
        elif res is None:
            if not incluir_pendientes:
                continue
        elif res["tipo"] == "no_jugado" and not incluir_no_jugados:
            continue
        if fases and p.get("bloque") not in fases:
            continue
        if ciclos and int(p.get("ciclo_bloque") or 0) not in ciclos:
            continue
        if jugadores and not (
            p["jugador_1"]["Jugador"] in jugadores
            or p["jugador_2"]["Jugador"] in jugadores
        ):
            continue
        if fecha_desde or fecha_hasta:
            f = _a_date(_fecha_partido(p))
            if f is None:
                continue
            if fecha_desde and f < fecha_desde:
                continue
            if fecha_hasta and f > fecha_hasta:
                continue
        salida.append(p)
    return salida


def partidos_a_dataframe(partidos: list[dict]) -> pd.DataFrame:
    """Detalle plano de partidos, una fila por partido."""
    filas = []
    for p in partidos:
        res = p.get("resultado")
        s1, s2, g1, g2 = _conteo_sets(res)
        fecha = _a_date(_fecha_partido(p))
        filas.append({
            "ID": p["id"],
            "Fecha": fecha.strftime("%d/%m/%Y") if fecha else "—",
            "Tipo": p.get("tipo", "—"),
            "Ronda": p.get("ronda_bloque", "—"),
            "Ciclo": p.get("ciclo_bloque", "—"),
            "Ranking 1": p["jugador_1"]["Ranking"],
            "Jugador 1": p["jugador_1"]["Jugador"],
            "Ranking 2": p["jugador_2"]["Ranking"],
            "Jugador 2": p["jugador_2"]["Jugador"],
            "Estado": _estado(p),
            "Ganador": (res or {}).get("ganador", "—") or "—",
            "Marcador": formatear_marcador(res),
            "Sets J1": s1,
            "Sets J2": s2,
            "Games J1": g1,
            "Games J2": g2,
        })
    df = pd.DataFrame(filas, columns=[
        "ID", "Fecha", "Tipo", "Ronda", "Ciclo",
        "Ranking 1", "Jugador 1", "Ranking 2", "Jugador 2",
        "Estado", "Ganador", "Marcador",
        "Sets J1", "Sets J2", "Games J1", "Games J2",
    ])
    return df


# ============================================================================
#  Estadísticas de un jugador único
# ============================================================================
def calcular_estadisticas(partidos: list[dict], jugador: str) -> dict:
    """
    Resumen del jugador sobre los partidos ya filtrados.
    Solo tiene sentido para un jugador único (ver requisito de la UI).
    """
    propios = [
        p for p in partidos
        if (p["jugador_1"]["Jugador"] == jugador or p["jugador_2"]["Jugador"] == jugador)
        and p.get("resultado") is not None
        and p["resultado"]["tipo"] != "no_jugado"
    ]
    propios.sort(key=_fecha_partido)

    pj = len(propios)
    victorias = sum(1 for p in propios if p["resultado"].get("ganador") == jugador)
    derrotas = pj - victorias
    wo_favor = sum(
        1 for p in propios
        if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") == jugador
    )
    wo_contra = sum(
        1 for p in propios
        if p["resultado"]["tipo"] == "wo" and p["resultado"].get("ganador") != jugador
    )

    sets_ganados = sets_perdidos = 0
    games_favor = games_contra = 0
    con_sets = 0
    for p in propios:
        res = p["resultado"]
        if res["tipo"] != "normal" or not res.get("sets"):
            continue
        con_sets += 1
        s1, s2, g1, g2 = _conteo_sets(res)
        es_j1 = p["jugador_1"]["Jugador"] == jugador
        sets_ganados += s1 if es_j1 else s2
        sets_perdidos += s2 if es_j1 else s1
        games_favor += g1 if es_j1 else g2
        games_contra += g2 if es_j1 else g1

    # Racha actual: victorias o derrotas consecutivas más recientes.
    racha = 0
    racha_tipo = "—"
    for p in reversed(propios):
        gano = p["resultado"].get("ganador") == jugador
        if racha == 0:
            racha_tipo = "Victorias" if gano else "Derrotas"
        if (racha_tipo == "Victorias") == gano:
            racha += 1
        else:
            break

    # Rival más enfrentado y balance contra él.
    balance: dict[str, list[int]] = {}
    for p in propios:
        es_j1 = p["jugador_1"]["Jugador"] == jugador
        rival = p["jugador_2"]["Jugador"] if es_j1 else p["jugador_1"]["Jugador"]
        reg = balance.setdefault(rival, [0, 0, 0])   # [PJ, G, P]
        reg[0] += 1
        if p["resultado"].get("ganador") == jugador:
            reg[1] += 1
        else:
            reg[2] += 1

    rival_top = None
    if balance:
        rival_top = max(balance.items(), key=lambda kv: (kv[1][0], kv[1][1]))

    fases = sorted({p.get("bloque") for p in propios if p.get("bloque")})
    ciclos = sorted({int(p["ciclo_bloque"]) for p in propios if p.get("ciclo_bloque") is not None})

    return {
        "jugador": jugador,
        "pj": pj,
        "victorias": victorias,
        "derrotas": derrotas,
        "pct_victorias": round(victorias / pj * 100, 1) if pj else 0.0,
        "wo_favor": wo_favor,
        "wo_contra": wo_contra,
        "sets_ganados": sets_ganados,
        "sets_perdidos": sets_perdidos,
        "games_favor": games_favor,
        "games_contra": games_contra,
        "hay_sets": con_sets > 0,
        "racha": racha,
        "racha_tipo": racha_tipo,
        "rival_top": rival_top[0] if rival_top else None,
        "rival_top_pj": rival_top[1][0] if rival_top else 0,
        "rival_top_g": rival_top[1][1] if rival_top else 0,
        "rival_top_p": rival_top[1][2] if rival_top else 0,
        "fases": fases,
        "ciclos": ciclos,
    }


def texto_racha(stats: dict) -> str:
    if not stats["racha"]:
        return "—"
    return f"{stats['racha']} {stats['racha_tipo'].lower()}"


def texto_rival_top(stats: dict) -> str:
    if not stats["rival_top"]:
        return "—"
    return (f"{stats['rival_top']} ({stats['rival_top_pj']} PJ · "
            f"{stats['rival_top_g']}G-{stats['rival_top_p']}P)")


def resumen_a_dataframe(stats: dict) -> pd.DataFrame:
    """Resumen del jugador como tabla Métrica/Valor (para CSV/Excel/PDF)."""
    filas = [
        ("Jugador", stats["jugador"]),
        ("Partidos jugados", stats["pj"]),
        ("Victorias", stats["victorias"]),
        ("Derrotas", stats["derrotas"]),
        ("% de victorias", f"{stats['pct_victorias']:.1f}%"),
        ("W.O. a favor", stats["wo_favor"]),
        ("W.O. en contra", stats["wo_contra"]),
    ]
    if stats["hay_sets"]:
        filas += [
            ("Sets ganados", stats["sets_ganados"]),
            ("Sets perdidos", stats["sets_perdidos"]),
            ("Games a favor", stats["games_favor"]),
            ("Games en contra", stats["games_contra"]),
        ]
    else:
        filas.append(("Sets", "Sin detalle de sets en el histórico"))
    filas += [
        ("Racha actual", texto_racha(stats)),
        ("Rival más enfrentado", texto_rival_top(stats)),
        ("Fases participadas", ", ".join(stats["fases"]) or "—"),
        ("Ciclos participados", ", ".join(str(c) for c in stats["ciclos"]) or "—"),
    ]
    return pd.DataFrame(filas, columns=["Métrica", "Valor"])


# ============================================================================
#  Exportadores — todos devuelven bytes en memoria
# ============================================================================
def exportar_csv(df_partidos: pd.DataFrame,
                 df_resumen: pd.DataFrame | None = None) -> bytes:
    """CSV con el bloque de resumen (si aplica) antes del detalle."""
    buf = io.StringIO()
    if df_resumen is not None and not df_resumen.empty:
        buf.write("RESUMEN DEL JUGADOR\n")
        df_resumen.to_csv(buf, index=False)
        buf.write("\n")
    buf.write("DETALLE DE PARTIDOS\n")
    df_partidos.to_csv(buf, index=False)
    # utf-8-sig para que Excel respete las tildes al abrir el CSV.
    return buf.getvalue().encode("utf-8-sig")


def exportar_excel(df_partidos: pd.DataFrame,
                   df_resumen: pd.DataFrame | None = None) -> bytes:
    """Excel con hoja 'Resumen' (si aplica) + hoja 'Partidos'."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if df_resumen is not None and not df_resumen.empty:
            df_resumen.to_excel(writer, index=False, sheet_name="Resumen")
        df_partidos.to_excel(writer, index=False, sheet_name="Partidos")
    buf.seek(0)
    return buf.getvalue()


def _dibujar_marco(c, doc, titulo: str, subtitulo: str):
    """Encabezado con logo + pie, en la línea gráfica del bracket PDF."""
    page_w, page_h = doc.pagesize
    header_h = 42

    c.saveState()
    c.setFillColor(C_CARD)
    c.rect(0, page_h - header_h, page_w, header_h, fill=1, stroke=0)
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(0.8)
    c.line(0, page_h - header_h, page_w, page_h - header_h)

    if LOGO_PATH.exists():
        try:
            c.drawImage(ImageReader(str(LOGO_PATH)), 8, page_h - header_h + 6,
                        width=30, height=30, mask="auto", preserveAspectRatio=True)
        except Exception:
            pass

    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(page_w / 2, page_h - 18, titulo)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(page_w / 2, page_h - 29, subtitulo)
    c.setFont("Helvetica", 6)
    c.drawRightString(page_w - 8, page_h - 18, "Costa Sport · Tennis Club")
    c.drawRightString(page_w - 8, page_h - 27, datetime.now().strftime("%d/%m/%Y"))

    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(page_w / 2, 8,
                        f"Costa Sport · Tennis Club · {datetime.now().year}")
    c.drawRightString(page_w - 8, 8, f"Página {doc.page}")
    c.restoreState()


def exportar_pdf(
    df_partidos: pd.DataFrame,
    df_resumen: pd.DataFrame | None = None,
    titulo: str = "Historial de resultados",
    subtitulo: str = "",
) -> bytes:
    """PDF apaisado: encabezado con logo, resumen arriba y tabla de partidos."""
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=8 * mm, rightMargin=8 * mm,
        topMargin=52, bottomMargin=16,
        title=titulo, author="Costa Sport · Tennis Club",
    )

    base = getSampleStyleSheet()
    st_seccion = ParagraphStyle(
        "Seccion", parent=base["Heading3"],
        fontName="Helvetica-Bold", fontSize=9, spaceAfter=4, textColor=C_BLUE,
    )
    st_celda = ParagraphStyle(
        "Celda", parent=base["BodyText"],
        fontName="Helvetica", fontSize=6.5, leading=8,
    )
    st_vacio = ParagraphStyle(
        "Vacio", parent=base["BodyText"],
        fontName="Helvetica-Oblique", fontSize=8, alignment=TA_CENTER,
    )

    story = []

    # ── Resumen del jugador (arriba del documento) ──
    if df_resumen is not None and not df_resumen.empty:
        story.append(Paragraph("RESUMEN DEL JUGADOR", st_seccion))
        datos = [list(df_resumen.columns)] + [
            [str(v) for v in fila] for fila in df_resumen.itertuples(index=False)
        ]
        t = Table(datos, colWidths=[55 * mm, 95 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_BLUE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D0E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, colors.HexColor("#EEF3FA")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # ── Detalle de partidos ──
    story.append(Paragraph("DETALLE DE PARTIDOS", st_seccion))
    if df_partidos.empty:
        story.append(Paragraph("Sin partidos para los filtros seleccionados.", st_vacio))
    else:
        cols = [c for c in COLUMNAS_PDF if c in df_partidos.columns]
        df_pdf = df_partidos[cols]
        datos = [cols] + [
            [Paragraph(str(v), st_celda) for v in fila]
            for fila in df_pdf.itertuples(index=False)
        ]
        ancho_util = page_w - doc.leftMargin - doc.rightMargin
        pesos = {
            "Fecha": 1.0, "Ronda": 0.5, "Jugador 1": 2.0,
            "Jugador 2": 2.0, "Ganador": 2.0, "Marcador": 2.2, "Estado": 0.9,
        }
        total_peso = sum(pesos.get(c, 1.0) for c in cols)
        col_widths = [ancho_util * pesos.get(c, 1.0) / total_peso for c in cols]

        t = Table(datos, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_BLUE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D0E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, colors.HexColor("#EEF3FA")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t)

    def _marco(c, d):
        _dibujar_marco(c, d, titulo, subtitulo)

    doc.build(story, onFirstPage=_marco, onLaterPages=_marco)
    buf.seek(0)
    return buf.getvalue()


def descripcion_filtros(
    fecha_desde: date | None,
    fecha_hasta: date | None,
    jugadores: list[str] | None,
    fases: list[str] | None,
    ciclos: list[int] | None,
    incluir_no_jugados: bool = False,
    incluir_pendientes: bool = False,
    solo_no_jugados: bool = False,
) -> str:
    """Texto legible con los filtros aplicados (subtítulo del PDF / caption UI)."""
    partes = []
    if fecha_desde or fecha_hasta:
        d = fecha_desde.strftime("%d/%m/%Y") if fecha_desde else "inicio"
        h = fecha_hasta.strftime("%d/%m/%Y") if fecha_hasta else "hoy"
        partes.append(f"Fechas: {d} → {h}")
    if jugadores:
        partes.append(f"Jugadores: {', '.join(jugadores)}")
    if fases:
        partes.append(f"Fases: {', '.join(fases)}")
    if ciclos:
        partes.append(f"Ciclos: {', '.join(str(c) for c in ciclos)}")
    base = " · ".join(partes) if partes else "Historial completo · sin filtros"
    if solo_no_jugados:
        return f"{base} · solo partidos no jugados"
    extra = [t for t, on in (("no jugados", incluir_no_jugados),
                             ("pendientes", incluir_pendientes)) if on]
    return f"{base} · incluye {' y '.join(extra)}" if extra else base
