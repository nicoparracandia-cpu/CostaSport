"""
bracket_pdf.py — Costa Sport
----------------------------
Genera PDF con bracket visual estilo ATP usando reportlab canvas.
Calcula TODAS las rondas desde el número de participantes.
"""
from __future__ import annotations
import io, math
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

C_DARK   = HexColor("#0E1117")
C_CARD   = HexColor("#1A1F2E")
C_WIN    = HexColor("#1A2744")
C_BLUE   = HexColor("#33B9F3")
C_MUTED  = HexColor("#8B9CC8")
C_LINE   = HexColor("#2A2F3E")
C_YELLOW = HexColor("#FFD700")
C_WHITE  = HexColor("#FFFFFF")
C_GRAY   = HexColor("#131720")

NOMBRES_FASE = {
    1:"final", 2:"semifinal", 4:"cuartos",
    8:"octavos", 16:"dieciseisavos",
    32:"treintaidosavos", 64:"sesentaicuatroavos"
}

def _cortar(nombre, max_c=14):
    if not nombre: return "—"
    p = nombre.strip().split()
    s = f"{p[0][0]}. {' '.join(p[1:])}" if len(p)>=2 else nombre
    return s[:max_c]

def _marc(sets):
    if not sets: return ""
    return " ".join(f"{s['games_1']}-{s['games_2']}" for s in sets)

def _caja(c, x, y, w, h, nombre, seed, ganador, marc=""):
    bg = C_WIN if ganador else C_CARD
    c.setFillColor(bg)
    c.setStrokeColor(C_LINE)
    c.setLineWidth(0.3)
    c.roundRect(x, y, w, h, 2, fill=1, stroke=1)
    ty = y + h/2 - 3
    if seed and seed <= 8:
        c.setFillColor(C_YELLOW)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x+2, ty, f"[{seed}]")
        nx = x + 14
    else:
        nx = x + 3
    c.setFillColor(C_BLUE if ganador else C_WHITE)
    c.setFont("Helvetica-Bold" if ganador else "Helvetica", 7)
    c.drawString(nx, ty, _cortar(nombre))
    if marc and ganador:
        c.setFillColor(C_BLUE)
        c.setFont("Helvetica", 6)
        c.drawRightString(x + w - 2, ty, marc)

def generar_pdf_bracket_visual(
    partidos: list[dict],
    titulo: str,
    subtitulo: str,
    tipo: str = "singles",
    logo_path: str = "assets/logo.png",
    participantes: list[dict] | None = None,
) -> bytes:

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))

    # Calcular bracket desde participantes o desde partidos
    if participantes:
        n = len(participantes)
    else:
        nombres_vistos = set()
        for p in partidos:
            for key in ["participante1","participante2"]:
                jug = p.get(key) or {}
                n = jug.get("jugador1_nombre","")
                if n: nombres_vistos.add(n)
        n = len(nombres_vistos) if nombres_vistos else 16

    size = 2 ** math.ceil(math.log2(max(n,2)))
    n_rondas = int(math.log2(size))

    # Indexar partidos por fase
    pxf = {}
    for p in partidos:
        f = p.get("fase","")
        pxf.setdefault(f, [])
        pxf[f].append(p)
    for f in pxf:
        pxf[f].sort(key=lambda x: x.get("orden") or 0)

    # Dimensiones
    HEADER_H = 45
    FOOTER_H = 15
    area_w = page_w - 20
    area_h = page_h - HEADER_H - FOOTER_H - 10

    BOX_W = min(110, (area_w - (n_rondas-1)*8) / n_rondas - 2)
    BOX_H = 13
    GAP   = 4
    COL_W = BOX_W + 8

    n_matches_r1 = size // 2
    slot_h = area_h / n_matches_r1

    def get_ys(r_idx):
        """Y centro de cada match en la ronda r_idx."""
        n_m = max(1, n_matches_r1 // (2**r_idx))
        sp = area_h / n_m
        return [FOOTER_H + 5 + sp*(i+0.5) for i in range(n_m)]

    # ── Fondo ──
    c.setFillColor(C_DARK)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── Header ──
    c.setFillColor(C_CARD)
    c.rect(0, page_h - HEADER_H, page_w, HEADER_H, fill=1, stroke=0)
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(1)
    c.line(0, page_h - HEADER_H, page_w, page_h - HEADER_H)

    logo = Path(logo_path)
    if not logo.exists(): logo = Path("assets/logo.png")
    if logo.exists():
        try:
            c.drawImage(ImageReader(str(logo)), 8, page_h-HEADER_H+4,
                       width=32, height=32, mask="auto", preserveAspectRatio=True)
        except: pass

    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(page_w/2, page_h-18, titulo)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(page_w/2, page_h-30, subtitulo)
    c.setFont("Helvetica", 7)
    c.drawRightString(page_w-8, page_h-18, "Costa Sport · Tennis Club")
    c.drawRightString(page_w-8, page_h-28, datetime.now().strftime("%d/%m/%Y"))

    # ── Bracket ──
    for r_idx in range(n_rondas):
        n_matches = max(1, size // (2**(r_idx+1)))
        fase_nombre = NOMBRES_FASE.get(n_matches, f"ronda_{size//(2**r_idx)}")
        pts_fase = pxf.get(fase_nombre, [])

        x = 10 + r_idx * COL_W
        positions = get_ys(r_idx)

        # Etiqueta ronda
        label = "FINAL" if r_idx==n_rondas-1 else fase_nombre.replace("_"," ").upper()[:12]
        c.setFillColor(C_BLUE)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(x + BOX_W/2, page_h - HEADER_H - 8, label)

        for m_idx, yc in enumerate(positions):
            y1 = yc + GAP/2
            y2 = yc - BOX_H - GAP/2
            match = pts_fase[m_idx] if m_idx < len(pts_fase) else None

            if match:
                p1 = match.get("participante1") or {}
                p2 = match.get("participante2") or {}
                gan_id = match.get("ganador_id")
                sets = (match.get("resultado") or {}).get("sets",[])
                if tipo=="dobles":
                    n1 = f"{p1.get('jugador1_nombre','')} / {p1.get('jugador2_nombre','')}"
                    n2 = f"{p2.get('jugador1_nombre','')} / {p2.get('jugador2_nombre','')}"
                else:
                    n1 = p1.get("jugador1_nombre","Por definir")
                    n2 = p2.get("jugador1_nombre","Por definir")
                s1 = p1.get("seed") or 0
                s2 = p2.get("seed") or 0
                g1 = bool(gan_id and gan_id==p1.get("id"))
                g2 = bool(gan_id and gan_id==p2.get("id"))
                marc = _marc(sets)
            else:
                n1=n2="Por definir"; s1=s2=0; g1=g2=False; marc=""

            _caja(c, x, y1, BOX_W, BOX_H, n1, s1, g1, marc if g1 else "")
            _caja(c, x, y2, BOX_W, BOX_H, n2, s2, g2, marc if g2 else "")

            # Conector hacia siguiente ronda
            if r_idx < n_rondas - 1:
                xr = x + BOX_W
                xm = xr + 4
                ym1 = y1 + BOX_H/2
                ym2 = y2 + BOX_H/2
                ymc = (ym1 + ym2) / 2

                c.setStrokeColor(C_LINE)
                c.setLineWidth(0.4)
                c.line(xr, ym1, xm, ym1)
                c.line(xr, ym2, xm, ym2)
                c.line(xm, ym2, xm, ym1)
                c.line(xm, ymc, xm+4, ymc)

    # Trofeo final
    x_fin = 10 + (n_rondas-1)*COL_W + BOX_W + 6
    y_fin = FOOTER_H + 5 + area_h/2
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(C_YELLOW)
    c.drawString(x_fin, y_fin-5, "🏆")

    # Footer
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 6)
    c.drawCentredString(page_w/2, 6, f"Costa Sport · Tennis Club · {datetime.now().year}")

    c.save()
    return buf.getvalue()
