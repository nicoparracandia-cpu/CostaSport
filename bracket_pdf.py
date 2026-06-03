"""
bracket_pdf.py — Costa Sport
----------------------------
Generador de PDF con bracket visual estilo ATP/torneo.
Usa reportlab canvas con coordenadas para dibujar cajas y líneas conectoras.
"""
from __future__ import annotations
import io
import math
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import ImageReader

# ── Paleta Costa Sport ──
C_DARK    = HexColor("#0E1117")
C_CARD    = HexColor("#1A1F2E")
C_WIN     = HexColor("#1A2744")
C_BLUE    = HexColor("#33B9F3")
C_MUTED   = HexColor("#8B9CC8")
C_LINE    = HexColor("#2A2F3E")
C_YELLOW  = HexColor("#FFD700")  # seeds

# ── Dimensiones de caja ──
BOX_W  = 120   # ancho caja jugador
BOX_H  = 16    # alto caja jugador
GAP    = 4     # gap entre j1 y j2 en un match
FONT_S = 7     # font size nombres
FONT_T = 8     # font size títulos ronda

MARGIN_TOP    = 50   # margen superior para header
MARGIN_LEFT   = 30
MARGIN_RIGHT  = 30
COL_GAP       = 40   # espacio horizontal entre columnas de rondas


def _cortar(nombre: str, max_c: int = 16) -> str:
    if not nombre:
        return "—"
    partes = nombre.strip().split()
    if len(partes) >= 2:
        s = f"{partes[0][0]}. {' '.join(partes[1:])}"
        return s[:max_c]
    return nombre[:max_c]


def _marcador(sets: list[dict]) -> str:
    if not sets:
        return ""
    return "  ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)


def _dibujar_caja(c, x, y, nombre, seed, ganador, marcador, w=BOX_W):
    """Dibuja una caja de jugador."""
    bg = C_WIN if ganador else C_CARD
    c.setFillColor(bg)
    c.setStrokeColor(C_LINE)
    c.setLineWidth(0.4)
    c.roundRect(x, y, w, BOX_H, 2, fill=1, stroke=1)

    if seed and seed <= 8:
        c.setFillColor(C_YELLOW)
        c.setFont("Helvetica-Bold", FONT_S - 1)
        c.drawString(x + 3, y + BOX_H/2 - 3, str(seed))
        nombre_x = x + 14
    else:
        nombre_x = x + 4

    c.setFillColor(C_BLUE if ganador else white)
    c.setFont("Helvetica-Bold" if ganador else "Helvetica", FONT_S)
    c.drawString(nombre_x, y + BOX_H/2 - 3, _cortar(nombre))

    if marcador:
        c.setFillColor(C_BLUE if ganador else C_MUTED)
        c.setFont("Helvetica", FONT_S - 1)
        c.drawRightString(x + w - 3, y + BOX_H/2 - 3, marcador)


def generar_pdf_bracket_visual(
    partidos: list[dict],
    titulo: str,
    subtitulo: str,
    tipo: str = "singles",
    logo_path: str = "assets/logo.png",
) -> bytes:
    """
    Genera PDF con bracket visual tipo ATP.
    Los partidos se organizan por ronda y se dibujan con líneas conectoras.
    """
    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))

    # Ordenar fases
    orden = ["sesentaicuatroavos","treintaidosavos","dieciseisavos",
             "octavos","cuartos","semifinal","final"]

    fases_raw = list(dict.fromkeys(p["fase"] for p in partidos))
    rondas_num = sorted(
        [f for f in fases_raw if f.startswith("ronda_")],
        key=lambda x: int(x.split("_")[1]) if x.split("_")[1].isdigit() else 0,
        reverse=True
    )
    fases = rondas_num + [f for f in orden if f in fases_raw]
    if not fases:
        fases = fases_raw

    n_rondas = len(fases)

    # Calcular matches por ronda
    matches_por_ronda = {}
    for fase in fases:
        matches_por_ronda[fase] = sorted(
            [p for p in partidos if p["fase"] == fase],
            key=lambda x: x.get("orden") or 0
        )

    n_primera = len(matches_por_ronda[fases[0]])

    # Área disponible para el bracket
    area_w = page_w - MARGIN_LEFT - MARGIN_RIGHT
    area_h = page_h - MARGIN_TOP - 40
    col_w  = (area_w - (n_rondas - 1) * COL_GAP) / n_rondas
    match_h = BOX_H * 2 + GAP  # alto de un match (j1 + gap + j2)

    def get_match_y(ronda_idx: int, match_idx: int, total_matches: int) -> float:
        """Calcula la Y del centro del match en esa ronda."""
        slot_h = area_h / total_matches
        # En rondas posteriores los matches se espacian más
        factor = 2 ** ronda_idx
        espaciado = area_h / (n_primera / factor)
        offset = espaciado / 2
        return MARGIN_TOP + offset + match_idx * espaciado

    # ── Fondo ──
    c.setFillColor(C_DARK)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── Header ──
    c.setFillColor(C_CARD)
    c.rect(0, page_h - MARGIN_TOP, page_w, MARGIN_TOP, fill=1, stroke=0)
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(1.5)
    c.line(0, page_h - MARGIN_TOP, page_w, page_h - MARGIN_TOP)

    # Logo
    logo = Path(logo_path)
    if not logo.exists():
        logo = Path("assets/logo.png")
    if logo.exists():
        try:
            img = ImageReader(str(logo))
            c.drawImage(img, MARGIN_LEFT, page_h - MARGIN_TOP + 5,
                       width=32, height=32, mask="auto", preserveAspectRatio=True)
        except:
            pass

    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w/2, page_h - 22, titulo)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(page_w/2, page_h - 36, subtitulo)
    c.setFont("Helvetica", 7)
    c.drawRightString(page_w - MARGIN_RIGHT, page_h - 22, "Costa Sport · Tennis Club")
    c.drawRightString(page_w - MARGIN_RIGHT, page_h - 34, datetime.now().strftime("%d/%m/%Y"))

    # ── Etiquetas de ronda ──
    for r_idx, fase in enumerate(fases):
        x_col = MARGIN_LEFT + r_idx * (col_w + COL_GAP)
        label = fase.replace("_", " ").upper()
        if fase == "final": label = "FINAL"
        elif fase == "semifinal": label = "SEMIFINAL"
        elif fase == "cuartos": label = "CUARTOS"
        elif fase == "octavos": label = "OCTAVOS"
        c.setFillColor(C_BLUE)
        c.setFont("Helvetica-Bold", FONT_T)
        c.drawCentredString(x_col + col_w/2, page_h - MARGIN_TOP - 10, label)

    # ── Dibujar matches y líneas conectoras ──
    coords_por_ronda = {}  # {fase: [(x_right, y_mid), ...]} para conectar

    for r_idx, fase in enumerate(fases):
        matches = matches_por_ronda[fase]
        x_col = MARGIN_LEFT + r_idx * (col_w + COL_GAP)
        coords_por_ronda[fase] = []

        for m_idx, match in enumerate(matches):
            n_total = len(matches)
            y_center = get_match_y(r_idx, m_idx, n_total)
            y1 = y_center + GAP/2              # Y jugador 1 (arriba)
            y2 = y_center - BOX_H - GAP/2     # Y jugador 2 (abajo)

            p1 = match.get("participante1") or {}
            p2 = match.get("participante2") or {}
            gan = match.get("ganador") or {}
            gan_id = match.get("ganador_id")
            sets = (match.get("resultado") or {}).get("sets", [])

            if tipo == "dobles":
                n1 = f"{p1.get('jugador1_nombre','')} / {p1.get('jugador2_nombre','')}"
                n2 = f"{p2.get('jugador1_nombre','')} / {p2.get('jugador2_nombre','')}"
            else:
                n1 = p1.get("jugador1_nombre", "Por definir")
                n2 = p2.get("jugador1_nombre", "Por definir")

            marc = _marcador(sets)
            es_gan1 = gan_id and gan_id == p1.get("id")
            es_gan2 = gan_id and gan_id == p2.get("id")
            seed1 = p1.get("seed") or 0
            seed2 = p2.get("seed") or 0

            # Cajas
            _dibujar_caja(c, x_col, y1, n1, seed1, es_gan1,
                         marc if es_gan1 else "", w=col_w - 5)
            _dibujar_caja(c, x_col, y2, n2, seed2, es_gan2,
                         marc if es_gan2 else "", w=col_w - 5)

            # Guardar coords para conectar con siguiente ronda
            x_right = x_col + col_w - 5
            y_mid = (y1 + BOX_H/2 + y2 + BOX_H/2) / 2
            coords_por_ronda[fase].append((x_right, y1 + BOX_H/2, y2 + BOX_H/2))

        # ── Líneas conectoras hacia siguiente ronda ──
        if r_idx < n_rondas - 1:
            fase_sig = fases[r_idx + 1]
            matches_sig = matches_por_ronda[fase_sig]
            x_col_sig = MARGIN_LEFT + (r_idx + 1) * (col_w + COL_GAP)

            c.setStrokeColor(C_LINE)
            c.setLineWidth(0.5)

            for i in range(0, len(matches), 2):
                if i + 1 >= len(matches):
                    break
                # Par de matches que se conectan al siguiente
                _, ya1, ya2 = coords_por_ronda[fase][i]
                _, yb1, yb2 = coords_por_ronda[fase][i + 1]
                x_right = MARGIN_LEFT + r_idx * (col_w + COL_GAP) + col_w - 5
                x_next  = x_col_sig

                ya_mid = (ya1 + ya2) / 2
                yb_mid = (yb1 + yb2) / 2
                y_join = (ya_mid + yb_mid) / 2

                x_mid = x_right + COL_GAP / 2

                # Línea horizontal desde match A
                c.line(x_right, ya_mid, x_mid, ya_mid)
                # Línea horizontal desde match B
                c.line(x_right, yb_mid, x_mid, yb_mid)
                # Línea vertical uniendo ambas
                c.line(x_mid, ya_mid, x_mid, yb_mid)
                # Línea horizontal hacia siguiente ronda
                c.line(x_mid, y_join, x_next, y_join)

    # ── Trofeo en la final ──
    x_final = MARGIN_LEFT + (n_rondas - 1) * (col_w + COL_GAP) + col_w
    c.setFillColor(C_YELLOW)
    c.setFont("Helvetica-Bold", 16)
    fase_final = fases[-1]
    matches_final = matches_por_ronda[fase_final]
    if matches_final:
        n_total = len(matches_final)
        y_trofeo = get_match_y(n_rondas - 1, 0, n_total)
        c.drawCentredString(x_final + 15, y_trofeo, "🏆")

    # ── Footer ──
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 6)
    c.drawCentredString(page_w/2, 8, f"Costa Sport · Tennis Club · {datetime.now().year}")

    c.save()
    return buf.getvalue()
