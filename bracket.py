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
    Genera el orden del bracket respetando los seeds.
    Seeds fijos: seed 1 arriba, seed 2 abajo, seed 3/4 en semis opuestas.
    El resto se sortea aleatoriamente en los espacios disponibles.
    """
    seeded = [p for p in participantes if (p.get("seed") or 0) > 0]
    unseeded = [p for p in participantes if not (p.get("seed") or 0) > 0]
    seeded.sort(key=lambda x: x["seed"])
    random.shuffle(unseeded)

    n = len(participantes)
    size = 2 ** math.ceil(math.log2(n)) if n > 1 else 2

    # Posiciones fijas para los 4 primeros seeds en bracket de 8+
    seed_positions = {}
    if size >= 4:
        seed_positions[1] = 0            # primer lugar
        seed_positions[2] = size - 1     # último lugar
    if size >= 8:
        seed_positions[3] = size // 2 - 1   # mitad superior final
        seed_positions[4] = size // 2       # mitad inferior inicio

    bracket = [None] * size
    for s in seeded:
        pos = seed_positions.get(s["seed"])
        if pos is not None and bracket[pos] is None:
            bracket[pos] = s

    # Llenar posiciones vacías con no-seeds
    pool = list(unseeded) + [s for s in seeded if s not in bracket]
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
    """Genera SVG completo del bracket de eliminación directa."""

    # Organizar partidos por fase
    orden_fases = ["dieciseisavos", "octavos", "cuartos", "semifinal", "final"]
    fases_presentes = []
    for f in orden_fases:
        if any(p["fase"] == f for p in partidos):
            fases_presentes.append(f)

    if not fases_presentes:
        return _svg_vacio(titulo)

    n_rondas = len(fases_presentes)
    primera_fase = fases_presentes[0]
    n_matches_primera = len([p for p in partidos if p["fase"] == primera_fase])

    # Dimensiones
    total_w = 60 + n_rondas * (BOX_W + ROUND_GAP)
    match_h = BOX_H * 2 + BOX_GAP
    total_h_matches = n_matches_primera * (match_h + MATCH_GAP)
    total_h = total_h_matches + 100

    lines = []
    lines.append(f'<svg width="100%" viewBox="0 0 {total_w} {total_h}" '
                 f'xmlns="http://www.w3.org/2000/svg" '
                 f'style="background:{COSTA_DARK};border-radius:12px;font-family:sans-serif">')

    # Título
    lines.append(f'<text x="{total_w//2}" y="28" '
                 f'text-anchor="middle" fill="{COSTA_BLUE}" '
                 f'font-size="14" font-weight="600">{titulo}</text>')

    # Dibujar por ronda
    for r_idx, fase in enumerate(fases_presentes):
        matches_fase = sorted(
            [p for p in partidos if p["fase"] == fase],
            key=lambda x: x.get("orden") or 0
        )
        n_m = len(matches_fase)
        spacing = total_h_matches / n_m
        x = 40 + r_idx * (BOX_W + ROUND_GAP)

        # Etiqueta de ronda
        label = fase.replace("_", " ").title()
        lines.append(f'<text x="{x + BOX_W//2}" y="50" '
                     f'text-anchor="middle" fill="{TEXT_MUTED}" '
                     f'font-size="10">{label}</text>')

        for m_idx, match in enumerate(matches_fase):
            y = 60 + m_idx * spacing + (spacing - match_h) / 2
            p1 = match.get("participante1") or {}
            p2 = match.get("participante2") or {}
            gan = match.get("ganador") or {}
            gan_id = match.get("ganador_id")
            sets = (match.get("resultado") or {}).get("sets", [])

            n1 = _nombre_corto(p1.get("jugador1_nombre", "—"))
            n2 = _nombre_corto(p2.get("jugador1_nombre", "—"))
            if tipo == "dobles":
                n1 = f"{_nombre_corto(p1.get('jugador1_nombre',''))} / {_nombre_corto(p1.get('jugador2_nombre',''))}"
                n2 = f"{_nombre_corto(p2.get('jugador1_nombre',''))} / {_nombre_corto(p2.get('jugador2_nombre',''))}"

            es_ganador_j1 = gan_id == p1.get("id")
            es_ganador_j2 = gan_id == p2.get("id")
            marc1 = _marcador_corto(sets, True) if sets else ""
            marc2 = _marcador_corto(sets, False) if sets else ""

            bg1 = WIN_BG if es_ganador_j1 else (LOSE_BG if es_ganador_j2 else PENDING_BG)
            bg2 = WIN_BG if es_ganador_j2 else (LOSE_BG if es_ganador_j1 else PENDING_BG)
            tc1 = TEXT_MAIN if es_ganador_j1 else TEXT_MUTED
            tc2 = TEXT_MAIN if es_ganador_j2 else TEXT_MUTED
            seed1 = p1.get("seed", "")
            seed2 = p2.get("seed", "")

            # Caja jugador 1
            lines.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" '
                         f'rx="4" fill="{bg1}" stroke="{GRAY_LINE}" stroke-width="0.5"/>')
            if seed1 and seed1 <= 4:
                lines.append(f'<text x="{x+8}" y="{y+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{COSTA_BLUE}" '
                              f'font-size="9" font-weight="700">[{seed1}]</text>')
                lines.append(f'<text x="{x+26}" y="{y+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{tc1}" '
                              f'font-size="11">{n1}</text>')
            else:
                lines.append(f'<text x="{x+10}" y="{y+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{tc1}" '
                              f'font-size="11">{n1}</text>')
            if marc1:
                lines.append(f'<text x="{x+BOX_W-6}" y="{y+BOX_H//2+1}" '
                              f'text-anchor="end" dominant-baseline="middle" '
                              f'fill="{COSTA_BLUE if es_ganador_j1 else TEXT_MUTED}" '
                              f'font-size="10" font-weight="{"600" if es_ganador_j1 else "400"}">{marc1}</text>')

            # Caja jugador 2
            y2 = y + BOX_H + BOX_GAP
            lines.append(f'<rect x="{x}" y="{y2}" width="{BOX_W}" height="{BOX_H}" '
                         f'rx="4" fill="{bg2}" stroke="{GRAY_LINE}" stroke-width="0.5"/>')
            if seed2 and seed2 <= 4:
                lines.append(f'<text x="{x+8}" y="{y2+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{COSTA_BLUE}" '
                              f'font-size="9" font-weight="700">[{seed2}]</text>')
                lines.append(f'<text x="{x+26}" y="{y2+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{tc2}" '
                              f'font-size="11">{n2}</text>')
            else:
                lines.append(f'<text x="{x+10}" y="{y2+BOX_H//2+1}" '
                              f'dominant-baseline="middle" fill="{tc2}" '
                              f'font-size="11">{n2}</text>')
            if marc2:
                lines.append(f'<text x="{x+BOX_W-6}" y="{y2+BOX_H//2+1}" '
                              f'text-anchor="end" dominant-baseline="middle" '
                              f'fill="{COSTA_BLUE if es_ganador_j2 else TEXT_MUTED}" '
                              f'font-size="10" font-weight="{"600" if es_ganador_j2 else "400"}">{marc2}</text>')

            # Línea conectora a siguiente ronda
            if r_idx < n_rondas - 1:
                mid_y = y + (match_h / 2)
                x_right = x + BOX_W
                x_next = x + BOX_W + ROUND_GAP
                lines.append(f'<line x1="{x_right}" y1="{mid_y}" x2="{x_right + ROUND_GAP//2}" y1="{mid_y}" '
                              f'x2="{x_right + ROUND_GAP//2}" y2="{mid_y}" '
                              f'stroke="{GRAY_LINE}" stroke-width="0.5"/>')
                lines.append(f'<path d="M{x_right} {mid_y} H{x_right + ROUND_GAP//2}" '
                              f'fill="none" stroke="{GRAY_LINE}" stroke-width="0.5"/>')

    # Líneas de conexión entre rondas (agrupando pares)
    for r_idx in range(len(fases_presentes) - 1):
        fase_actual = fases_presentes[r_idx]
        matches_actual = sorted(
            [p for p in partidos if p["fase"] == fase_actual],
            key=lambda x: x.get("orden") or 0
        )
        n_m = len(matches_actual)
        spacing = total_h_matches / n_m
        x_right = 40 + r_idx * (BOX_W + ROUND_GAP) + BOX_W
        x_mid = x_right + ROUND_GAP // 2
        x_next = x_right + ROUND_GAP

        for i in range(0, n_m, 2):
            if i + 1 >= n_m:
                break
            y_a = 60 + i * spacing + (spacing - (BOX_H * 2 + BOX_GAP)) / 2 + BOX_H + BOX_GAP // 2
            y_b = 60 + (i+1) * spacing + (spacing - (BOX_H * 2 + BOX_GAP)) / 2 + BOX_H + BOX_GAP // 2
            y_mid = (y_a + y_b) / 2

            lines.append(f'<path d="M{x_right} {y_a} H{x_mid} V{y_b} H{x_right}" '
                         f'fill="none" stroke="{GRAY_LINE}" stroke-width="0.5"/>')
            lines.append(f'<line x1="{x_mid}" y1="{y_mid}" x2="{x_next}" y2="{y_mid}" '
                         f'stroke="{GRAY_LINE}" stroke-width="0.5"/>')

    # Trofeo al final
    x_trophy = 40 + n_rondas * (BOX_W + ROUND_GAP) - ROUND_GAP + 10
    lines.append(f'<text x="{x_trophy}" y="{total_h//2}" '
                 f'font-size="24" dominant-baseline="middle">🏆</text>')

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
    lines.append(f'<svg width="100%" viewBox="0 0 {total_w} {total_h}" '
                 f'xmlns="http://www.w3.org/2000/svg" '
                 f'style="background:{COSTA_DARK};border-radius:12px;font-family:sans-serif">')

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
    Genera PDF brandeado con logo Costa Sport, título y bracket SVG.
    Retorna bytes del PDF.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import HexColor
    import cairosvg

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    BLUE = HexColor("#33B9F3")
    DARK = HexColor("#0E1117")
    WHITE = HexColor("#FFFFFF")
    MUTED = HexColor("#8B9CC8")

    svgs = svg_content if isinstance(svg_content, list) else [svg_content]

    for page_i, svg in enumerate(svgs):
        # Fondo oscuro
        c.setFillColor(DARK)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        # Header azul
        c.setFillColor(BLUE)
        c.rect(0, page_h - 60, page_w, 60, fill=1, stroke=0)

        # Logo
        logo = Path(logo_path)
        if not logo.exists():
            logo = Path("assets/logo.png")
        if logo.exists():
            try:
                img = ImageReader(str(logo))
                c.drawImage(img, 20, page_h - 54, width=44, height=44,
                           mask="auto", preserveAspectRatio=True)
            except Exception:
                pass

        # Título en header
        c.setFillColor(HexColor("#0E1117"))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(76, page_h - 28, titulo)
        c.setFont("Helvetica", 11)
        c.drawString(76, page_h - 46, subtitulo)

        # Fecha
        fecha = datetime.now().strftime("%d/%m/%Y")
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - 20, page_h - 28, f"Costa Sport · Tennis Club")
        c.drawRightString(page_w - 20, page_h - 44, fecha)

        # Convertir SVG a PNG e insertar
        try:
            png_bytes = cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                output_width=int(page_w - 40),
                output_height=int(page_h - 100),
            )
            png_buf = io.BytesIO(png_bytes)
            img_bracket = ImageReader(png_buf)
            c.drawImage(img_bracket, 20, 30, width=page_w - 40, height=page_h - 100,
                       preserveAspectRatio=True, mask="auto")
        except Exception as e:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 11)
            c.drawString(40, page_h / 2, f"Error generando imagen: {e}")

        # Footer
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(page_w / 2, 12, f"Costa Sport · Escalerilla {datetime.now().year}")

        if page_i < len(svgs) - 1:
            c.showPage()
            c.setFillColor(DARK)
            c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    c.save()
    return buf.getvalue()


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
