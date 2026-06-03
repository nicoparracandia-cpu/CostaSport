"""
bracket.py — Costa Sport
------------------------
Generador de bracket SVG dinámico y exportador PDF brandeado.
Soporta: eliminación directa, round robin, grupos + eliminación.
"""
from __future__ import annotations
import io
import math
import random
import base64
from datetime import datetime
from pathlib import Path


# ============================================================================
#  Sorteo con seeds
# ============================================================================

def hacer_sorteo(participantes: list[dict], tipo_formato: str) -> list[dict]:
    """
    Genera el orden del bracket respetando el seeding ATP:
    - Seed 1: posición 1 (arriba del todo)
    - Seed 2: posición final (abajo del todo)
    - Seeds 3-4: sorteados, uno en cada mitad opuesta (posiciones centrales de cada mitad)
    - Seeds 5-8: sorteados, uno en cada cuarto
    - Resto: sorteados aleatoriamente en posiciones vacías
    """
    seeded = [p for p in participantes if (p.get("seed") or 0) > 0]
    unseeded = [p for p in participantes if not (p.get("seed") or 0) > 0]
    seeded.sort(key=lambda x: x["seed"])
    random.shuffle(unseeded)

    n = len(participantes)
    size = 2 ** math.ceil(math.log2(n)) if n > 1 else 2
    bracket = [None] * size

    # ── Seed 1 y 2: posiciones fijas extremos ──
    seed_map = {}
    s1 = next((p for p in seeded if p["seed"] == 1), None)
    s2 = next((p for p in seeded if p["seed"] == 2), None)
    if s1: bracket[0] = s1; seed_map[1] = 0
    if s2: bracket[size-1] = s2; seed_map[2] = size-1

    # ── Seeds 3-4: uno en cada mitad, sorteados ──
    s3 = next((p for p in seeded if p["seed"] == 3), None)
    s4 = next((p for p in seeded if p["seed"] == 4), None)
    # Posiciones finales de cada mitad (justo antes del centro)
    pos_mitad_sup = size // 2 - 1   # último de la mitad superior
    pos_mitad_inf = size // 2       # primero de la mitad inferior
    pos_34 = [pos_mitad_sup, pos_mitad_inf]
    random.shuffle(pos_34)
    if s3 and bracket[pos_34[0]] is None:
        bracket[pos_34[0]] = s3; seed_map[3] = pos_34[0]
    if s4 and bracket[pos_34[1]] is None:
        bracket[pos_34[1]] = s4; seed_map[4] = pos_34[1]

    # ── Seeds 5-8: uno en cada cuarto ──
    cuartos_pos = [
        size // 4 - 1,        # fin del 1er cuarto
        size // 4,            # inicio del 2do cuarto
        3 * size // 4 - 1,   # fin del 3er cuarto
        3 * size // 4,        # inicio del 4to cuarto
    ]
    # Asegurarse de que no estén ocupadas
    cuartos_libres = [p for p in cuartos_pos if bracket[p] is None]
    random.shuffle(cuartos_libres)
    seeds_5_8 = [p for p in seeded if p["seed"] in (5,6,7,8)]
    random.shuffle(seeds_5_8)
    for i, s in enumerate(seeds_5_8):
        if i < len(cuartos_libres):
            bracket[cuartos_libres[i]] = s

    # ── Resto: llenar posiciones vacías aleatoriamente ──
    ya_colocados = set(id(p) for p in bracket if p is not None)
    pool = [p for p in seeded if id(p) not in ya_colocados] + list(unseeded)
    random.shuffle(pool)
    for i in range(size):
        if bracket[i] is None and pool:
            bracket[i] = pool.pop(0)

    return bracket


def aplicar_sorteo_supabase(sb, torneo_id: int, participantes: list[dict]) -> None:
    """Actualiza los seeds en Supabase según el sorteo."""
    bracket = hacer_sorteo(participantes, "eliminacion")
    for i, p in enumerate(bracket):
        if p:
            sb.table("torneo_participantes").update(
                {"seed": i + 1}
            ).eq("id", p["id"]).execute()


# ============================================================================
#  Generador SVG de bracket
# ============================================================================

COSTA_BLUE = "#33B9F3"
COSTA_DARK = "#0E1117"
GRAY_LINE = "#2A2F3E"
ACCENT_YELLOW = "#FFD700"
TEXT_MAIN = "#FFFFFF"
TEXT_MUTED = "#8B9CC8"
WIN_BG = "#1A2744"
LOSE_BG = "#131720"
PENDING_BG = "#1A1F2E"

BOX_W = 160
BOX_H = 28
BOX_GAP = 8       # gap entre j1 y j2 dentro de match
ROUND_GAP = 60    # espacio horizontal entre rondas
MATCH_GAP = 20    # espacio vertical entre matches


def _nombre_corto(nombre: str, max_len: int = 18) -> str:
    if not nombre or nombre == "BYE":
        return "BYE"
    partes = nombre.strip().split()
    if len(partes) >= 2:
        return f"{partes[0][0]}. {' '.join(partes[1:])}"[:max_len]
    return nombre[:max_len]


def _marcador_corto(sets: list[dict], es_j1: bool) -> str:
    if not sets:
        return ""
    partes = []
    for s in sets:
        g1, g2 = s["games_1"], s["games_2"]
        partes.append(f"{g1}-{g2}" if es_j1 else f"{g2}-{g1}")
    return "  ".join(partes)


def generar_svg_eliminacion(
    partidos: list[dict],
    participantes: list[dict],
    tipo: str = "singles",
    titulo: str = "Torneo",
) -> str:
    """Genera SVG completo del bracket — muestra TODAS las rondas aunque esten vacias."""

    if not participantes:
        return _svg_vacio(titulo)

    import math

    n = len(participantes)
    size = 2 ** math.ceil(math.log2(n)) if n > 1 else 2
    n_rondas = int(math.log2(size))

    nombres_fase = {
        1: "final", 2: "semifinal", 4: "cuartos",
        8: "octavos", 16: "dieciseisavos", 32: "treintaidosavos", 64: "sesentaicuatroavos"
    }

    partidos_por_fase = {}
    for p in partidos:
        f = p.get("fase", "")
        partidos_por_fase.setdefault(f, [])
        partidos_por_fase[f].append(p)

    BOX_W2   = 140
    BOX_H2   = 22
    BOX_GAP2 = 6
    ROUND_GAP2 = 50
    MATCH_H2 = BOX_H2 * 2 + BOX_GAP2
    MARGIN_X = 30
    MARGIN_Y = 50
    LABEL_H  = 18

    n_matches_r1 = size // 2
    slot_h = MATCH_H2 + 20
    area_h = n_matches_r1 * slot_h

    total_w = MARGIN_X * 2 + n_rondas * (BOX_W2 + ROUND_GAP2)
    total_h = MARGIN_Y + LABEL_H + area_h + 40

    lines = []
    lines.append(f'<svg width="{total_w}" height="{min(total_h, 700)}" '
                 f'viewBox="0 0 {total_w} {total_h}" '
                 f'xmlns="http://www.w3.org/2000/svg" '
                 f'style="background:{COSTA_DARK};border-radius:12px;font-family:sans-serif">')

    lines.append(f'<text x="{total_w//2}" y="24" text-anchor="middle" '
                 f'fill="{COSTA_BLUE}" font-size="13" font-weight="600">{titulo}</text>')

    def get_positions(ronda_idx):
        n_m = max(1, n_matches_r1 // (2 ** ronda_idx))
        spacing = area_h / n_m
        return [MARGIN_Y + LABEL_H + spacing * (i + 0.5) for i in range(n_m)]

    for r_idx in range(n_rondas):
        size_ronda = size // (2 ** r_idx)
        n_matches = size_ronda // 2
        fase_nombre = nombres_fase.get(n_matches, f"ronda_{size_ronda}")
        label = "FINAL" if r_idx == n_rondas - 1 else fase_nombre.replace("_", " ").upper()

        x = MARGIN_X + r_idx * (BOX_W2 + ROUND_GAP2)
        positions = get_positions(r_idx)

        pts_fase = sorted(
            partidos_por_fase.get(fase_nombre, []),
            key=lambda p: p.get("orden") or 0
        )

        lines.append(f'<text x="{x + BOX_W2//2}" y="{MARGIN_Y + 12}" '
                     f'text-anchor="middle" fill="{TEXT_MUTED}" font-size="9">{label}</text>')

        for m_idx, y_center in enumerate(positions):
            y1 = y_center - MATCH_H2 / 2
            y2 = y1 + BOX_H2 + BOX_GAP2
            match = pts_fase[m_idx] if m_idx < len(pts_fase) else None

            if match:
                p1 = match.get("participante1") or {}
                p2 = match.get("participante2") or {}
                gan_id = match.get("ganador_id")
                sets = (match.get("resultado") or {}).get("sets", [])
                n1 = p1.get("jugador1_nombre", "Por definir")
                n2 = p2.get("jugador1_nombre", "Por definir")
                if tipo == "dobles":
                    n1 = f"{p1.get('jugador1_nombre','')} / {p1.get('jugador2_nombre','')}"
                    n2 = f"{p2.get('jugador1_nombre','')} / {p2.get('jugador2_nombre','')}"
                seed1 = p1.get("seed") or 0
                seed2 = p2.get("seed") or 0
                es_gan1 = bool(gan_id and gan_id == p1.get("id"))
                es_gan2 = bool(gan_id and gan_id == p2.get("id"))
                marc = " ".join(f"{s['games_1']}-{s['games_2']}" for s in sets) if sets else ""
            else:
                n1 = n2 = "Por definir"
                seed1 = seed2 = 0
                es_gan1 = es_gan2 = False
                marc = ""

            for j, (y_box, nombre, seed, es_gan) in enumerate([
                (y1, n1, seed1, es_gan1),
                (y2, n2, seed2, es_gan2)
            ]):
                bg = WIN_BG if es_gan else (LOSE_BG if (es_gan1 or es_gan2) and not es_gan else PENDING_BG)
                lines.append(f'<rect x="{x}" y="{y_box:.1f}" width="{BOX_W2}" height="{BOX_H2}" '
                             f'rx="3" fill="{bg}" stroke="{GRAY_LINE}" stroke-width="0.5"/>')
                nx = x + (20 if seed and seed <= 8 else 5)
                if seed and seed <= 8:
                    lines.append(f'<text x="{x+4}" y="{y_box+BOX_H2//2+4:.1f}" '
                                 f'fill="{ACCENT_YELLOW}" font-size="8" font-weight="700">[{seed}]</text>')
                lines.append(f'<text x="{nx}" y="{y_box+BOX_H2//2+4:.1f}" '
                             f'fill="{"#33B9F3" if es_gan else "white"}" font-size="10" '
                             f'font-weight="{"600" if es_gan else "400"}">{_nombre_corto(nombre, 15)}</text>')
                if marc and es_gan:
                    lines.append(f'<text x="{x+BOX_W2-3}" y="{y_box+BOX_H2//2+4:.1f}" '
                                 f'text-anchor="end" fill="{COSTA_BLUE}" font-size="8">{marc}</text>')

            # Conectores hacia siguiente ronda
            if r_idx < n_rondas - 1:
                x_right = x + BOX_W2
                x_mid = x_right + ROUND_GAP2 // 2
                y_mid_match = y_center
                lines.append(f'<line x1="{x_right}" y1="{y_mid_match:.1f}" '
                             f'x2="{x_mid}" y2="{y_mid_match:.1f}" '
                             f'stroke="{GRAY_LINE}" stroke-width="0.5"/>')
                if m_idx % 2 == 0 and m_idx + 1 < len(positions):
                    y_partner = positions[m_idx + 1]
                    y_join = (y_mid_match + y_partner) / 2
                    lines.append(f'<line x1="{x_mid}" y1="{y_mid_match:.1f}" '
                                 f'x2="{x_mid}" y2="{y_partner:.1f}" '
                                 f'stroke="{GRAY_LINE}" stroke-width="0.5"/>')
                    x_next = x + BOX_W2 + ROUND_GAP2
                    lines.append(f'<line x1="{x_mid}" y1="{y_join:.1f}" '
                                 f'x2="{x_next}" y2="{y_join:.1f}" '
                                 f'stroke="{GRAY_LINE}" stroke-width="0.5"/>')

    x_trophy = MARGIN_X + (n_rondas - 0.3) * (BOX_W2 + ROUND_GAP2)
    y_trophy = MARGIN_Y + LABEL_H + area_h / 2
    lines.append(f'<text x="{x_trophy:.0f}" y="{y_trophy:.0f}" font-size="20" '
                 f'dominant-baseline="middle">🏆</text>')

    lines.append('</svg>')
    return '\n'.join(lines)


def generar_svg_round_robin(
    partidos: list[dict],
    participantes: list[dict],
    tipo: str = "singles",
    titulo: str = "Torneo",
) -> str:
    """Genera tabla de posiciones estilo ATP para round robin."""
    from collections import defaultdict

    stats = {}
    for p in participantes:
        n = p.get("jugador1_nombre", "")
        if tipo == "dobles" and p.get("jugador2_nombre"):
            n = f"{p['jugador1_nombre']} / {p['jugador2_nombre']}"
        stats[p["id"]] = {
            "nombre": n, "seed": p.get("seed") or 0,
            "PJ": 0, "G": 0, "P": 0, "SG": 0, "SP": 0, "Pts": 0
        }

    for m in partidos:
        if not m.get("ganador_id"):
            continue
        p1_id = (m.get("participante1") or {}).get("id")
        p2_id = (m.get("participante2") or {}).get("id")
        gan_id = m.get("ganador_id")
        sets = (m.get("resultado") or {}).get("sets", [])
        s1 = sum(1 for s in sets if s["games_1"] > s["games_2"])
        s2 = len(sets) - s1

        for pid in [p1_id, p2_id]:
            if pid in stats:
                stats[pid]["PJ"] += 1
        if gan_id in stats:
            stats[gan_id]["G"] += 1
            stats[gan_id]["Pts"] += 2
            stats[gan_id]["SG"] += s1 if gan_id == p1_id else s2
            stats[gan_id]["SP"] += s2 if gan_id == p1_id else s1
        per_id = p2_id if gan_id == p1_id else p1_id
        if per_id in stats:
            stats[per_id]["P"] += 1
            stats[per_id]["Pts"] += 1
            stats[per_id]["SG"] += s2 if per_id == p2_id else s1
            stats[per_id]["SP"] += s1 if per_id == p2_id else s2

    tabla = sorted(stats.values(), key=lambda x: (-x["Pts"], -x["G"], -(x["SG"]-x["SP"])))

    COL_W = [26, 160, 30, 30, 30, 30, 30, 30, 36]
    headers = ["#", "Jugador", "PJ", "G", "P", "SG", "SP", "Pts", "Dif"]
    total_w = sum(COL_W) + 20
    row_h = 28
    total_h = 60 + (len(tabla) + 1) * row_h + 20

    lines = []
    # Limitar altura máxima del SVG — con muchos jugadores el SVG puede ser muy alto
    # Usamos max_h para limitar el alto visible y permitir scroll
    lines.append(f'<svg width="{max(total_w, 800)}" height="{min(total_h, 600)}" '
                 f'viewBox="0 0 {total_w} {total_h}" '
                 f'xmlns="http://www.w3.org/2000/svg" '
                 f'preserveAspectRatio="xMinYMin meet" '
                 f'style="background:{COSTA_DARK};border-radius:12px;font-family:sans-serif;max-width:100%">')

    lines.append(f'<text x="{total_w//2}" y="24" text-anchor="middle" '
                 f'fill="{COSTA_BLUE}" font-size="13" font-weight="600">{titulo}</text>')

    # Header
    x_cur = 10
    y_h = 50
    lines.append(f'<rect x="10" y="{y_h-16}" width="{total_w-20}" height="{row_h}" '
                 f'rx="4" fill="{WIN_BG}"/>')
    for i, h in enumerate(headers):
        cx = x_cur + COL_W[i] // 2
        lines.append(f'<text x="{cx}" y="{y_h+6}" text-anchor="middle" '
                     f'fill="{COSTA_BLUE}" font-size="10" font-weight="600">{h}</text>')
        x_cur += COL_W[i]

    # Filas
    for row_i, row in enumerate(tabla):
        y_r = y_h + row_h + row_i * row_h
        bg = WIN_BG if row_i == 0 else (PENDING_BG if row_i % 2 == 0 else LOSE_BG)
        lines.append(f'<rect x="10" y="{y_r-16}" width="{total_w-20}" height="{row_h}" '
                     f'rx="2" fill="{bg}"/>')
        x_cur = 10
        vals = [
            str(row_i + 1),
            _nombre_corto(row["nombre"], 22),
            str(row["PJ"]), str(row["G"]), str(row["P"]),
            str(row["SG"]), str(row["SP"]), str(row["Pts"]),
            f"+{row['SG']-row['SP']}" if row["SG"] >= row["SP"] else str(row["SG"]-row["SP"])
        ]
        colors = [TEXT_MUTED, TEXT_MAIN, TEXT_MUTED, TEXT_MAIN, TEXT_MUTED,
                  TEXT_MUTED, TEXT_MUTED, COSTA_BLUE, TEXT_MUTED]
        for i, val in enumerate(vals):
            cx = x_cur + COL_W[i] // 2
            lines.append(f'<text x="{cx}" y="{y_r+6}" text-anchor="middle" '
                         f'fill="{colors[i]}" font-size="{"12" if i==1 else "11"}">{val}</text>')
            x_cur += COL_W[i]

    lines.append('</svg>')
    return '\n'.join(lines)


def generar_svg_grupos(
    partidos: list[dict],
    participantes: list[dict],
    tipo: str = "singles",
    titulo: str = "Torneo",
) -> str:
    """Genera SVGs de tabla por grupo + bracket de eliminación si existe."""
    grupos = list(dict.fromkeys(p.get("grupo") or "A" for p in participantes))
    svgs = []

    for grupo in grupos:
        parts_grupo = [p for p in participantes if (p.get("grupo") or "A") == grupo]
        parts_elim = [p for p in partidos if (p.get("grupo") or "") == grupo]
        svg = generar_svg_round_robin(parts_elim, parts_grupo, tipo, f"{titulo} — Grupo {grupo}")
        svgs.append(svg)

    fases_elim = [p for p in partidos if p.get("fase") not in (None, "grupos") and not (p.get("fase") or "").startswith("ronda_")]
    if fases_elim:
        svg_bracket = generar_svg_eliminacion(fases_elim, participantes, tipo, f"{titulo} — Fase final")
        svgs.append(svg_bracket)

    return svgs


def _svg_vacio(titulo: str) -> str:
    return (f'<svg width="100%" viewBox="0 0 400 100" xmlns="http://www.w3.org/2000/svg" '
            f'style="background:{COSTA_DARK};border-radius:12px">'
            f'<text x="200" y="50" text-anchor="middle" fill="{TEXT_MUTED}" font-size="13">'
            f'Sin partidos generados aún</text></svg>')


# ============================================================================
#  Exportador PDF brandeado
# ============================================================================

def generar_pdf_bracket(
    svg_content: str | list,
    titulo: str,
    subtitulo: str,
    logo_path: str = "assets/logo.png",
) -> bytes:
    """
    Genera PDF brandeado con logo + bracket como tabla textual.
    No requiere cairosvg ni libcairo.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()

    BLUE = HexColor("#33B9F3")
    DARK = HexColor("#0E1117")
    MUTED = HexColor("#8B9CC8")
    WIN = HexColor("#1A2744")
    LOSE = HexColor("#131720")

    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1*cm, bottomMargin=1*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("titulo", parent=styles["Normal"],
        fontSize=18, fontName="Helvetica-Bold", textColor=BLUE,
        alignment=TA_CENTER, spaceAfter=4)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica", textColor=MUTED,
        alignment=TA_CENTER, spaceAfter=12)
    cell_style = ParagraphStyle("cell", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica", textColor=white)
    cell_win = ParagraphStyle("win", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica-Bold", textColor=BLUE)
    fase_style = ParagraphStyle("fase", parent=styles["Normal"],
        fontSize=8, fontName="Helvetica", textColor=MUTED, alignment=TA_CENTER)

    story = []

    # Logo + título
    logo = Path(logo_path)
    if not logo.exists():
        logo = Path("assets/logo.png")

    header_data = [[]]
    if logo.exists():
        try:
            img = RLImage(str(logo), width=1.2*cm, height=1.2*cm)
            header_data[0].append(img)
        except:
            header_data[0].append("")
    else:
        header_data[0].append("")

    header_data[0].append(
        Paragraph(f"<b>{titulo}</b><br/><font size='9' color='#8B9CC8'>{subtitulo}</font>", title_style)
    )
    header_data[0].append(
        Paragraph(f"Costa Sport · Tennis Club<br/><font size='8'>{datetime.now().strftime('%d/%m/%Y')}</font>", sub_style)
    )

    header_table = Table(header_data, colWidths=[2*cm, page_w - 7*cm, 4*cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND", (0,0), (-1,-1), DARK),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [DARK]),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.4*cm))

    svgs = svg_content if isinstance(svg_content, list) else [svg_content]

    for svg_i, svg in enumerate(svgs):
        # Extraer datos del SVG para tabla textual
        filas = _extraer_partidos_de_svg(svg)
        if not filas:
            story.append(Paragraph("Sin partidos generados", sub_style))
            continue

        # Agrupar por fase
        fases = list(dict.fromkeys(f["fase"] for f in filas))
        for fase in fases:
            story.append(Paragraph(fase.replace("_", " ").upper(), fase_style))
            story.append(Spacer(1, 0.1*cm))
            matches_fase = [f for f in filas if f["fase"] == fase]
            col_w = (page_w - 3*cm) / 4
            tabla_data = [["Jugador 1", "Resultado", "Jugador 2", "Ganador"]]
            for m in matches_fase:
                tabla_data.append([
                    Paragraph(m["j1"], cell_win if m["ganador"] == m["j1"] else cell_style),
                    Paragraph(m["marcador"], cell_style),
                    Paragraph(m["j2"], cell_win if m["ganador"] == m["j2"] else cell_style),
                    Paragraph(m["ganador"] or "Por definir", cell_win if m["ganador"] else cell_style),
                ])
            t = Table(tabla_data, colWidths=[col_w]*4, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), HexColor("#1A2744")),
                ("TEXTCOLOR", (0,0), (-1,0), BLUE),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,0), 8),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [DARK, LOSE]),
                ("GRID", (0,0), (-1,-1), 0.3, HexColor("#2A2F3E")),
                ("TOPPADDING", (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                ("LEFTPADDING", (0,0), (-1,-1), 6),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.3*cm))

        if svg_i < len(svgs) - 1:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


def _extraer_partidos_de_svg(svg_str: str) -> list[dict]:
    """Extrae datos de partidos del SVG para armar tabla PDF."""
    import re
    filas = []
    # Buscar datos en el SVG — usa los atributos data-* que generamos
    bloques = re.findall(r'data-fase="([^"]*)"[^>]*data-j1="([^"]*)"[^>]*data-j2="([^"]*)"'
                         r'[^>]*data-marc="([^"]*)"[^>]*data-gan="([^"]*)"', svg_str)
    for fase, j1, j2, marc, gan in bloques:
        filas.append({"fase": fase, "j1": j1, "j2": j2, "marcador": marc, "ganador": gan})
    return filas


def generar_pdf_simple(
    svg_content: str | list,
    titulo: str,
    subtitulo: str,
    logo_path: str = "assets/logo.png",
) -> bytes:
    """
    Versión simplificada sin cairosvg — usa HTML+CSS para el bracket.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import HexColor

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    BLUE = HexColor("#33B9F3")
    DARK = HexColor("#0E1117")
    MUTED = HexColor("#8B9CC8")

    svgs = svg_content if isinstance(svg_content, list) else [svg_content]

    for page_i, svg in enumerate(svgs):
        c.setFillColor(DARK)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        c.setFillColor(BLUE)
        c.rect(0, page_h - 55, page_w, 55, fill=1, stroke=0)

        logo = Path(logo_path)
        if not logo.exists():
            logo = Path("assets/logo.png")
        if logo.exists():
            try:
                img = ImageReader(str(logo))
                c.drawImage(img, 15, page_h - 50, width=40, height=40,
                           mask="auto", preserveAspectRatio=True)
            except Exception:
                pass

        c.setFillColor(HexColor("#0E1117"))
        c.setFont("Helvetica-Bold", 15)
        c.drawString(70, page_h - 24, titulo)
        c.setFont("Helvetica", 10)
        c.drawString(70, page_h - 40, subtitulo)

        fecha = datetime.now().strftime("%d/%m/%Y")
        c.setFont("Helvetica", 8)
        c.drawRightString(page_w - 15, page_h - 24, "Costa Sport · Tennis Club")
        c.drawRightString(page_w - 15, page_h - 38, fecha)

        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(page_w / 2, 10, f"Costa Sport · {datetime.now().year}")

        if page_i < len(svgs) - 1:
            c.showPage()

    c.save()
    return buf.getvalue()

def generar_pdf_desde_partidos(
    partidos: list[dict],
    titulo: str,
    subtitulo: str,
    tipo: str = "singles",
    logo_path: str = "assets/logo.png",
) -> bytes:
    """
    Genera PDF brandeado con tabla de partidos por fase.
    No requiere cairosvg — usa reportlab puro.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.colors import HexColor, white
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()

    BLUE  = HexColor("#33B9F3")
    DARK  = HexColor("#0E1117")
    MUTED = HexColor("#8B9CC8")
    WIN   = HexColor("#1A2744")
    LOSE  = HexColor("#131720")
    GRAY  = HexColor("#2A2F3E")

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=0.8*cm, bottomMargin=0.8*cm)

    styles = getSampleStyleSheet()
    def sty(size=9, bold=False, color=white, align=TA_CENTER):
        return ParagraphStyle("x", parent=styles["Normal"],
            fontSize=size, fontName="Helvetica-Bold" if bold else "Helvetica",
            textColor=color, alignment=align)

    story = []

    # Header
    logo = Path(logo_path)
    if not logo.exists():
        logo = Path("assets/logo.png")
    logo_cell = ""
    if logo.exists():
        try:
            logo_cell = RLImage(str(logo), width=1.2*cm, height=1.2*cm)
        except:
            pass

    hdr = Table([[
        logo_cell,
        Paragraph(f"<b>{titulo}</b>", sty(16, True, BLUE, TA_CENTER)),
        Paragraph(f"{subtitulo}<br/>{datetime.now().strftime('%d/%m/%Y')}", sty(9, False, MUTED, TA_CENTER)),
    ]], colWidths=[2*cm, page_w-7*cm, 4*cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), DARK),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.4*cm))

    # Agrupar partidos por fase
    fases = list(dict.fromkeys(p["fase"] for p in partidos))
    for fase in fases:
        pts_fase = [p for p in partidos if p["fase"] == fase]
        label_fase = fase.replace("_"," ").upper()

        story.append(Paragraph(label_fase, sty(9, True, BLUE, TA_CENTER)))
        story.append(Spacer(1, 0.15*cm))

        col_w = (page_w - 3*cm) / 5
        tabla = [[ Paragraph(h, sty(8, True, BLUE, TA_CENTER))
                   for h in ["Seed", "Jugador 1", "Resultado", "Jugador 2", "Ganador"] ]]

        for m in pts_fase:
            p1 = m.get("participante1") or {}
            p2 = m.get("participante2") or {}
            gan = m.get("ganador") or {}
            gan_id = m.get("ganador_id")
            sets = (m.get("resultado") or {}).get("sets", [])

            if tipo == "dobles":
                n1 = f"{p1.get('jugador1_nombre','')} / {p1.get('jugador2_nombre','')}"
                n2 = f"{p2.get('jugador1_nombre','')} / {p2.get('jugador2_nombre','')}"
                n_gan = f"{gan.get('jugador1_nombre','')} / {gan.get('jugador2_nombre','')}" if gan_id else "Por definir"
            else:
                n1 = p1.get("jugador1_nombre", "—")
                n2 = p2.get("jugador1_nombre", "—")
                n_gan = gan.get("jugador1_nombre", "Por definir") if gan_id else "Por definir"

            marc = " / ".join(f"{s['games_1']}-{s['games_2']}" for s in sets) if sets else "Pendiente"
            s1 = p1.get("seed") or ""
            s2 = p2.get("seed") or ""

            es_gan1 = gan_id and gan_id == p1.get("id")
            es_gan2 = gan_id and gan_id == p2.get("id")

            tabla.append([
                Paragraph(str(s1) if s1 else "—", sty(8, False, MUTED, TA_CENTER)),
                Paragraph(n1, sty(8, es_gan1, BLUE if es_gan1 else white, TA_CENTER)),
                Paragraph(marc, sty(8, False, MUTED, TA_CENTER)),
                Paragraph(n2, sty(8, es_gan2, BLUE if es_gan2 else white, TA_CENTER)),
                Paragraph(n_gan, sty(8, bool(gan_id), BLUE if gan_id else MUTED, TA_CENTER)),
            ])

        t = Table(tabla, colWidths=[col_w*0.4, col_w*1.4, col_w*0.8, col_w*1.4, col_w*0.9], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), WIN),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [DARK, LOSE]),
            ("GRID", (0,0),(-1,-1), 0.3, GRAY),
            ("TOPPADDING", (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING", (0,0),(-1,-1), 4),
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

    # Footer
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Costa Sport · Tennis Club · {datetime.now().year}",
        sty(7, False, MUTED, TA_CENTER)
    ))

    doc.build(story)
    return buf.getvalue()
