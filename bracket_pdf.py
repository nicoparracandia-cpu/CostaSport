"""
bracket_pdf.py — Costa Sport
Bracket visual tipo ATP: dos mitades espejadas, BYEs para seeds, final al centro.
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
C_LINE   = HexColor("#33B9F3")   # líneas azul tenue
C_LINEG  = HexColor("#2A2F3E")   # líneas gris
C_YELLOW = HexColor("#FFD700")
C_WHITE  = HexColor("#FFFFFF")
C_BYE    = HexColor("#0E1117")   # BYE = mismo fondo, invisible

NOMBRES_FASE = {
    1:"FINAL", 2:"SEMIFINAL", 4:"CUARTOS",
    8:"OCTAVOS", 16:"16AVOS", 32:"32AVOS", 64:"64AVOS"
}

def _cortar(nombre, mx=15):
    if not nombre or nombre.strip() == "":
        return ""
    if nombre in ("BYE","Por definir"):
        return ""
    p = nombre.strip().split()
    s = f"{p[0][0]}. {' '.join(p[1:])}" if len(p)>=2 else nombre
    return s[:mx]

def _caja(c, x, y, w, h, nombre, seed, ganador, es_bye=False):
    if es_bye:
        c.setFillColor(C_BYE)
        c.setStrokeColor(C_LINEG)
    else:
        c.setFillColor(C_WIN if ganador else C_CARD)
        c.setStrokeColor(C_LINE if ganador else C_LINEG)
    c.setLineWidth(0.3)
    c.roundRect(x, y, w, h, 2, fill=1, stroke=1)
    if es_bye:
        return
    ty = y + h/2 - 2.5
    nombre_corto = _cortar(nombre)
    if nombre_corto:
        if seed and seed <= 8:
            c.setFillColor(C_YELLOW)
            c.setFont("Helvetica-Bold", 5.5)
            c.drawString(x+2, ty, f"[{seed}]")
            nx = x + 13
        else:
            nx = x + 3
        c.setFillColor(C_BLUE if ganador else C_WHITE)
        c.setFont("Helvetica-Bold" if ganador else "Helvetica", 6.5)
        c.drawString(nx, ty, nombre_corto)


def _construir_bracket_con_byes(participantes, size):
    """
    Construye bracket de size slots con participantes ordenados por seed.
    Slots vacíos = BYE (cabezas de serie no juegan primera ronda).
    Retorna lista de size elementos: dict o None(BYE).
    """
    bracket = [None] * size
    # Ordenar por seed: seeded primero, luego el resto
    seeded   = sorted([p for p in participantes if (p.get("seed") or 0) > 0], key=lambda x: x["seed"])
    unseeded = [p for p in participantes if not (p.get("seed") or 0) > 0]

    # Posiciones ATP estándar para los primeros 8 seeds
    seed_pos = {}
    if size >= 2:
        seed_pos[1] = 0
        seed_pos[2] = size - 1
    if size >= 4:
        import random
        pos34 = [size//2 - 1, size//2]
        random.shuffle(pos34)
        seed_pos[3] = pos34[0]
        seed_pos[4] = pos34[1]
    if size >= 8:
        import random
        pos58 = [size//4-1, size//4, 3*size//4-1, 3*size//4]
        random.shuffle(pos58)
        for i, s in enumerate(range(5,9)):
            seed_pos[s] = pos58[i]

    # Colocar seeds en sus posiciones
    for p in seeded:
        pos = seed_pos.get(p["seed"])
        if pos is not None and bracket[pos] is None:
            bracket[pos] = p

    # Rellenar resto con no-seeds
    import random
    pool = [p for p in seeded if p not in bracket] + unseeded
    random.shuffle(pool)
    for i in range(size):
        if bracket[i] is None and pool:
            bracket[i] = pool.pop(0)

    return bracket


def generar_pdf_bracket_visual(
    partidos: list[dict],
    titulo: str,
    subtitulo: str,
    tipo: str = "singles",
    logo_path: str = "assets/logo.png",
    participantes: list[dict] | None = None,
    config: dict | None = None,
) -> bytes:

    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))

    # Calcular tamaño del bracket
    n = len(participantes) if participantes else 16
    n = max(n, 4)
    config = config or {}
    tam_bracket = config.get("tam_bracket", 0)
    if tam_bracket and tam_bracket >= 4:
        size = tam_bracket
    else:
        size = 2 ** math.ceil(math.log2(n))
    n_rondas = int(math.log2(size))

    # Construir bracket si tenemos participantes
    if participantes:
        bracket = _construir_bracket_con_byes(participantes, size)
    else:
        bracket = [None] * size

    # Indexar partidos reales por fase y orden
    pxf = {}
    for p in partidos:
        f = p.get("fase","")
        pxf.setdefault(f, {})
        pxf[f][p.get("orden",0)] = p

    # ── Layout ──
    HEADER  = 40
    FOOTER  = 12
    PAD_X   = 8
    area_h  = page_h - HEADER - FOOTER - 4
    area_w  = page_w - PAD_X * 2

    # Mitad izquierda y derecha
    half_w  = area_w / 2 - 4
    BOX_H   = max(8, min(14, area_h / (size/2) - 2))
    BOX_W   = min(95, half_w / n_rondas - 6)
    COL_W   = BOX_W + 6
    MATCH_H = BOX_H * 2 + 3   # dos cajas + gap

    # ── Fondo ──
    c.setFillColor(C_DARK)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # ── Header ──
    c.setFillColor(C_CARD)
    c.rect(0, page_h-HEADER, page_w, HEADER, fill=1, stroke=0)
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(0.8)
    c.line(0, page_h-HEADER, page_w, page_h-HEADER)

    logo = Path(logo_path)
    if not logo.exists(): logo = Path("assets/logo.png")
    if logo.exists():
        try:
            c.drawImage(ImageReader(str(logo)), 6, page_h-HEADER+4,
                       width=28, height=28, mask="auto", preserveAspectRatio=True)
        except: pass

    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(page_w/2, page_h-16, titulo)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(page_w/2, page_h-27, subtitulo)
    c.setFont("Helvetica", 6)
    c.drawRightString(page_w-6, page_h-16, "Costa Sport · Tennis Club")
    c.drawRightString(page_w-6, page_h-25, datetime.now().strftime("%d/%m/%Y"))

    # ── Función para dibujar una mitad del bracket ──
    def draw_half(bracket_half, start_x_fn, ronda_dir, y_offset_base):
        """
        Dibuja n_rondas columnas.
        bracket_half: lista de jugadores para esta mitad (size/2 elementos)
        start_x_fn(r_idx): retorna x inicial de la columna r_idx
        ronda_dir: 1 = izquierda→derecha, -1 = derecha→izquierda
        """
        half_size = len(bracket_half)
        half_rondas = int(math.log2(half_size)) + 1 if half_size > 1 else 1

        for r_idx in range(half_rondas):
            n_matches = max(1, half_size // (2**r_idx))
            # Nombre de fase para esta columna
            n_matches_global = max(1, size // (2**(r_idx+1)))
            label = NOMBRES_FASE.get(n_matches_global, f"R{size//(2**r_idx)}")

            x = start_x_fn(r_idx)
            sp = area_h / n_matches

            # Etiqueta
            c.setFillColor(C_BLUE)
            c.setFont("Helvetica-Bold", 5)
            c.drawCentredString(x + BOX_W/2, page_h - HEADER - 7, label)

            # Nombre de fase para lookup en partidos
            fase_nombre_lookup = {v:k for k,v in NOMBRES_FASE.items()}.get(label)
            # Alternativamente buscar por número de matches
            fase_str = None
            for k,v in NOMBRES_FASE.items():
                if k == n_matches_global:
                    fase_str = v.lower().replace("avos","avos")
                    break
            # Mapear al nombre real usado en BD
            fase_map = {
                "final":"final","semifinal":"semifinal","cuartos":"cuartos",
                "octavos":"octavos","16avos":"dieciseisavos",
                "32avos":"treintaidosavos","64avos":"sesentaicuatroavos"
            }
            fase_real = fase_map.get(label.lower(), f"ronda_{size//(2**r_idx)}")
            pts_ronda = pxf.get(fase_real, {})

            for m_idx in range(n_matches):
                yc = FOOTER + 5 + sp * (m_idx + 0.5)
                y1 = yc + 1.5
                y2 = yc - BOX_H - 1.5

                # Primera ronda: tomar del bracket
                if r_idx == 0:
                    idx1 = m_idx * 2
                    idx2 = m_idx * 2 + 1
                    p1_data = bracket_half[idx1] if idx1 < len(bracket_half) else None
                    p2_data = bracket_half[idx2] if idx2 < len(bracket_half) else None
                    n1 = p1_data.get("jugador1_nombre","") if p1_data else "BYE"
                    n2 = p2_data.get("jugador1_nombre","") if p2_data else "BYE"
                    s1 = (p1_data.get("seed") or 0) if p1_data else 0
                    s2 = (p2_data.get("seed") or 0) if p2_data else 0
                    bye1 = not p1_data
                    bye2 = not p2_data
                    g1 = g2 = False
                    marc = ""
                else:
                    # Rondas siguientes: buscar en partidos reales
                    match = pts_ronda.get(m_idx+1)
                    if match:
                        mp1 = match.get("participante1") or {}
                        mp2 = match.get("participante2") or {}
                        gan_id = match.get("ganador_id")
                        sets = (match.get("resultado") or {}).get("sets",[])
                        n1 = mp1.get("jugador1_nombre","") or ""
                        n2 = mp2.get("jugador1_nombre","") or ""
                        s1 = mp1.get("seed") or 0
                        s2 = mp2.get("seed") or 0
                        g1 = bool(gan_id and gan_id==mp1.get("id"))
                        g2 = bool(gan_id and gan_id==mp2.get("id"))
                        marc = "  ".join(f"{s['games_1']}-{s['games_2']}" for s in sets) if sets else ""
                    else:
                        # Sin partido aún — caja vacía
                        n1=n2=""; s1=s2=0; g1=g2=False; marc=""
                    bye1=bye2=False

                _caja(c, x, y1, BOX_W, BOX_H, n1, s1, g1, bye1)
                _caja(c, x, y2, BOX_W, BOX_H, n2, s2, g2, bye2)

                # Conector →
                if r_idx < half_rondas - 1:
                    xr = x + BOX_W if ronda_dir > 0 else x
                    xm = xr + (4 if ronda_dir > 0 else -4)
                    ym1 = y1 + BOX_H/2
                    ym2 = y2 + BOX_H/2
                    ymc = (ym1+ym2)/2
                    c.setStrokeColor(C_LINEG)
                    c.setLineWidth(0.35)
                    if ronda_dir > 0:
                        c.line(xr, ym1, xm, ym1)
                        c.line(xr, ym2, xm, ym2)
                        c.line(xm, ym2, xm, ym1)
                        c.line(xm, ymc, xm+4, ymc)
                    else:
                        c.line(x, ym1, xm, ym1)
                        c.line(x, ym2, xm, ym2)
                        c.line(xm, ym2, xm, ym1)
                        c.line(xm, ymc, xm-4, ymc)

    # Dividir bracket en dos mitades
    half = size // 2
    bracket_izq = bracket[:half]
    bracket_der = bracket[half:]

    half_rondas = n_rondas  # cada mitad tiene n_rondas-1 columnas + semifinal

    # Mitad izquierda: columnas de izq a der
    def x_izq(r_idx):
        return PAD_X + r_idx * COL_W

    # Mitad derecha: columnas de der a izq (espejado)
    def x_der(r_idx):
        return page_w - PAD_X - BOX_W - r_idx * COL_W

    draw_half(bracket_izq, x_izq, 1, 0)
    draw_half(list(reversed(bracket_der)), x_der, -1, 0)

    # ── Final en el centro ──
    x_fin_izq = PAD_X + (n_rondas-1) * COL_W + BOX_W + 6
    x_fin_der = page_w - PAD_X - (n_rondas-1)*COL_W - BOX_W - 6 - BOX_W
    x_fin = (x_fin_izq + x_fin_der) / 2 - BOX_W/2
    y_fin_c = FOOTER + 5 + area_h/2

    # Caja finalistas y final
    fase_real_sf = "semifinal"
    pts_sf = pxf.get(fase_real_sf,{})
    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x_fin + BOX_W/2, page_h - HEADER - 7, "FINAL")

    # Partido final
    match_final = pxf.get("final",{}).get(1)
    if match_final:
        mp1 = match_final.get("participante1") or {}
        mp2 = match_final.get("participante2") or {}
        gan_id = match_final.get("ganador_id")
        nf1 = mp1.get("jugador1_nombre","Por definir")
        nf2 = mp2.get("jugador1_nombre","Por definir")
        sf1 = mp1.get("seed") or 0
        sf2 = mp2.get("seed") or 0
        gf1 = bool(gan_id and gan_id==mp1.get("id"))
        gf2 = bool(gan_id and gan_id==mp2.get("id"))
    else:
        nf1=nf2="Por definir"; sf1=sf2=0; gf1=gf2=False

    _caja(c, x_fin, y_fin_c+2, BOX_W, BOX_H, nf1, sf1, gf1)
    _caja(c, x_fin, y_fin_c-BOX_H-2, BOX_W, BOX_H, nf2, sf2, gf2)

    # Trofeo
    c.setFillColor(C_YELLOW)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(x_fin + BOX_W/2, y_fin_c + BOX_H + 8, "🏆")

    # Footer
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(page_w/2, 5, f"Costa Sport · Tennis Club · {datetime.now().year}")

    c.save()
    return buf.getvalue()
