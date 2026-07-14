"""PDF ispisi za Skladište.

Dva dokumenta:
  * `pdf_stanje(db)`     — stanje skladišta nacrtano kao TLOCRT (karta odozgo),
                           ista orijentacija kao web karta: ulaz dolje-desno,
                           A1 do ulaza, P1 uvijek desno, Zapad lijevo / Istok desno.
  * `pdf_plan(db, pid)`  — lista predloženih pozicija za jedan plan zaprimanja
                           (za radnika: redom skenira palete na te pozicije).
"""
import io
from datetime import date, datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.skladiste import config as cfg
from app.modules.skladiste import service as svc
from app.modules.skladiste.adapter import get_adapter
from app.modules.skladiste.models import Paleta, Prijem

# ── Font (hrvatski znakovi) — isti pristup kao reklamacije/utils.py ─────────────
def _font_datoteka(win_naziv, dejavu_naziv):
    """Prva postojeća font-datoteka: Windows Arial ili DejaVu (Linux/Docker)."""
    import os
    for p in (f"C:/Windows/Fonts/{win_naziv}",
              f"/usr/share/fonts/truetype/dejavu/{dejavu_naziv}"):
        if os.path.exists(p):
            return p
    return f"C:/Windows/Fonts/{win_naziv}"


try:
    pdfmetrics.registerFont(TTFont("F",  _font_datoteka("arial.ttf",   "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("FB", _font_datoteka("arialbd.ttf", "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("F", normal="F", bold="FB", italic="F", boldItalic="FB")
    _FONT, _FONTB = "F", "FB"
except Exception:
    _FONT, _FONTB = "Helvetica", "Helvetica-Bold"

# ── Boje (usklađeno s web kartom) ───────────────────────────────────────────────
_TAMNO  = colors.HexColor("#0F172A")
_SIVA   = colors.HexColor("#475569")
_LINIJA = colors.HexColor("#CBD5E1")

_BOJA = {
    "slobodno": colors.HexColor("#E5E7EB"),
    "zauzeto":  colors.HexColor("#3B82F6"),
    "istice":   colors.HexColor("#F59E0B"),
    "isteklo":  colors.HexColor("#EF4444"),
}
_RUB = {
    "slobodno": colors.HexColor("#9CA3AF"),
    "zauzeto":  colors.HexColor("#2563EB"),
    "istice":   colors.HexColor("#D97706"),
    "isteklo":  colors.HexColor("#DC2626"),
}


def _x(v) -> str:
    if v is None or v == "":
        return "—"
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _zone_brojevi(db: Session) -> tuple[int, dict[str, int]]:
    zauz_uk = db.scalar(select(func.count(Paleta.id)).where(Paleta.datum_out.is_(None))) or 0
    po_zoni = {}
    for z in cfg.ZONE:
        po_zoni[z] = db.scalar(
            select(func.count(Paleta.id)).where(
                Paleta.datum_out.is_(None), Paleta.pozicija.like(f"{z}%"))
        ) or 0
    return zauz_uk, po_zoni


# ── Karta (tlocrt) ──────────────────────────────────────────────────────────────

def _cell(c: Canvas, x, y, w, h, status, dot=False):
    c.setFillColor(_BOJA.get(status, _BOJA["slobodno"]))
    c.setStrokeColor(_RUB.get(status, _LINIJA))
    c.setLineWidth(0.4)
    c.rect(x, y, w, h, fill=1, stroke=1)
    if dot:
        c.setFillColor(_TAMNO)
        c.circle(x + w / 2, y + h / 2, min(w, h) * 0.14, fill=1, stroke=0)


def pdf_stanje(db: Session) -> io.BytesIO:
    t = svc.mapa_tlocrt(db)
    buf = io.BytesIO()
    W, H = landscape(A4)                       # 842 x 595 pt
    c = Canvas(buf, pagesize=(W, H))

    # Zaglavlje
    c.setFillColor(_TAMNO); c.setFont(_FONTB, 16)
    c.drawString(15 * mm, H - 15 * mm, "Stanje skladišta — tlocrt")
    c.setFillColor(_SIVA); c.setFont(_FONT, 9)
    c.drawRightString(W - 15 * mm, H - 13 * mm, datetime.now().strftime("%d.%m.%Y  %H:%M"))

    # Sažetak po zonama
    ukupno = cfg.UKUPNO_MJESTA
    zauz_uk, po_zoni = _zone_brojevi(db)
    pct = round(zauz_uk / ukupno * 100) if ukupno else 0
    dijelovi = [f"Ukupno {zauz_uk}/{ukupno} ({pct}%)"]
    for z in cfg.ZONE:
        dijelovi.append(f"{z}: {po_zoni[z]}/{cfg.kapacitet_zone(z)}")
    c.setFont(_FONT, 9); c.setFillColor(_SIVA)
    c.drawString(15 * mm, H - 21 * mm, "      ".join(dijelovi))

    # ── Geometrija tlocrta ──
    y_top = H - 30 * mm
    y_bot = 22 * mm
    x_left = 12 * mm
    zap_w = ist_w = 10 * mm
    x_zap = x_left
    x_ist = W - 14 * mm - ist_w
    x_mid_right = x_ist - 5 * mm               # desni rub srednjih ćelija (P1 ide ovdje)

    rows_b = list(reversed(t["sredina_b"]))    # B5..B1 (B gore)
    rows_a = list(reversed(t["sredina_a"]))    # A13..A1 (A1 dolje, do ulaza)
    n_rows = len(rows_b) + len(rows_a)
    sep_gap = 4 * mm
    gap = 1.2 * mm
    row_step = ((y_top - y_bot) - sep_gap) / n_rows
    cellh = row_step - gap
    max_pos = 15
    avail_w = x_mid_right - (x_left + zap_w + 14 * mm)
    cellw = min(13 * mm, avail_w / max_pos)
    step_x = cellw + gap
    x_label = x_mid_right - max_pos * step_x - 1 * mm

    def draw_row(row, y):
        c.setFont(_FONT, 6.5); c.setFillColor(_SIVA)
        c.drawRightString(x_label, y - cellh * 0.72, row["naziv"])
        for ci in row["pozicije"]:
            k = ci["pozicija"]                 # 1..n; P1 desno
            x = (x_mid_right - (k - 1) * step_x) - cellw
            _cell(c, x, y - cellh, cellw, cellh, ci["status"], dot=(k == 1))

    y = y_top
    for row in rows_b:
        draw_row(row, y); y -= row_step
    # razdjelnik B / A
    c.setStrokeColor(_LINIJA); c.setLineWidth(0.6); c.setDash(3, 3)
    c.line(x_zap, y - sep_gap / 2, x_ist + ist_w, y - sep_gap / 2); c.setDash()
    y -= sep_gap
    for row in rows_a:
        draw_row(row, y); y -= row_step

    # Zapad (C1) — lijevi okomiti regal, P1 dolje (do ulaza)
    side_h = y_top - y_bot
    c.setFont(_FONTB, 7.5); c.setFillColor(_TAMNO)
    c.drawCentredString(x_zap + zap_w / 2, y_top + 2.5 * mm, "Zapad C1")
    zap = t["zapad"]["pozicije"]; zh = side_h / max(len(zap), 1)
    for ci in zap:
        k = ci["pozicija"]
        _cell(c, x_zap, y_bot + (k - 1) * zh, zap_w, zh - 0.6, ci["status"], dot=(k == 1))

    # Istok (D1) — desni okomiti regal, P1 dolje (do ulaza)
    c.setFont(_FONTB, 7.5); c.setFillColor(_TAMNO)
    c.drawCentredString(x_ist + ist_w / 2, y_top + 2.5 * mm, "Istok D1")
    ist = t["istok"]["pozicije"]; ih = side_h / max(len(ist), 1)
    for ci in ist:
        k = ci["pozicija"]
        _cell(c, x_ist, y_bot + (k - 1) * ih, ist_w, ih - 0.6, ci["status"], dot=(k == 1))

    # ULAZ — dolje desno
    c.setFont(_FONTB, 11); c.setFillColor(colors.HexColor("#1D4ED8"))
    c.drawRightString(x_ist + ist_w, y_bot - 6.5 * mm, "U L A Z")

    # Legenda (donji lijevi rub)
    lx, ly = 15 * mm, 11 * mm
    for status, label in [("slobodno", "slobodno"), ("zauzeto", "zauzeto"),
                          ("istice", "ističe (<30 dana)"), ("isteklo", "isteklo")]:
        _cell(c, lx, ly, 4 * mm, 4 * mm, status)
        c.setFillColor(_SIVA); c.setFont(_FONT, 8)
        c.drawString(lx + 5.5 * mm, ly + 0.7 * mm, label)
        lx += 40 * mm
    c.setFillColor(_TAMNO); c.circle(lx + 2 * mm, ly + 2 * mm, 1.3 * mm, fill=1, stroke=0)
    c.setFillColor(_SIVA); c.setFont(_FONT, 8)
    c.drawString(lx + 5.5 * mm, ly + 0.7 * mm, "P1 (do ulaza)")

    c.setFont(_FONT, 7); c.setFillColor(_SIVA)
    c.drawString(15 * mm, 5 * mm,
                 "ERP Skladište · pogled odozgo · ćelija = pozicija (sve visine zajedno)")
    c.showPage(); c.save(); buf.seek(0)
    return buf


# ── Lista pozicija za zaprimanje ─────────────────────────────────────────────────

def pdf_plan(db: Session, prijem_id: int) -> io.BytesIO | None:
    prijem = db.get(Prijem, prijem_id)
    if prijem is None:
        return None
    artikl = get_adapter().lookup_barcode(prijem.sifra)

    buf = io.BytesIO()
    PAGE_W, _ = A4
    ML = MR = 1.8 * cm
    CW = PAGE_W - ML - MR
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=ML, rightMargin=MR)

    H1  = ParagraphStyle("H1",  fontName=_FONTB, fontSize=15, textColor=_TAMNO, leading=18, spaceAfter=3)
    SUB = ParagraphStyle("SUB", fontName=_FONT,  fontSize=10, textColor=_SIVA,  leading=14, spaceAfter=12)
    TH  = ParagraphStyle("TH",  fontName=_FONTB, fontSize=9,  textColor=colors.white, leading=11)
    TD  = ParagraphStyle("TD",  fontName=_FONT,  fontSize=10.5, textColor=_TAMNO, leading=13)
    TDP = ParagraphStyle("TDP", fontName=_FONTB, fontSize=11, textColor=_TAMNO, leading=13)

    naziv = _x((artikl.naziv if artikl else None) or prijem.sifra)
    fmt = f" · {_x(artikl.format)}" if (artikl and artikl.format) else ""
    datum = (prijem.datum_plan or date.today()).strftime("%d.%m.%Y")

    story = [
        Paragraph(f"Lista zaprimanja — plan #{prijem.id}", H1),
        Paragraph(f"{naziv} · šifra <b>{_x(prijem.sifra)}</b>{fmt} · "
                  f"<b>{prijem.broj_paleta}</b> paleta · {datum}", SUB),
    ]

    data = [[Paragraph("Rb.", TH), Paragraph("Predložena pozicija", TH),
             Paragraph("Status", TH), Paragraph("Skenirani barkod palete", TH)]]
    for i, s in enumerate(prijem.stavke, 1):
        potvrdjeno = s.datum_potvrda is not None
        data.append([
            Paragraph(str(s.redni_broj or i), TD),
            Paragraph(_x(s.pozicija), TDP),
            Paragraph('<font color="#16A34A"><b>potvrđeno</b></font>' if potvrdjeno
                      else '<font color="#94A3B8">za skeniranje</font>', TD),
            Paragraph(_x(s.qr_raw) if s.qr_raw else
                      '<font color="#CBD5E1">______________________________</font>', TD),
        ])

    tbl = Table(data, colWidths=[1.4 * cm, 5.2 * cm, 3.6 * cm, CW - 10.2 * cm], repeatRows=1)
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), _TAMNO),
        ("BOX", (0, 0), (-1, -1), 0.6, _LINIJA),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, _LINIJA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, s in enumerate(prijem.stavke, 1):
        if s.datum_potvrda is not None:
            ts.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F0FDF4")))
    tbl.setStyle(TableStyle(ts))
    story.append(tbl)

    story.append(Spacer(1, 0.5 * cm))
    nap = ParagraphStyle("NAP", fontName=_FONT, fontSize=8.5, textColor=_SIVA, leading=12)
    story.append(Paragraph(
        "Uputa: skeniraj barkod palete pa skeniraj predloženu poziciju (ili upiši svoju). "
        "Pozicije su predložene algoritmom smještaja (prioriteti po šifri).", nap))
    story.append(Spacer(1, 0.8 * cm))
    pot = ParagraphStyle("POT", fontName=_FONT, fontSize=9, textColor=_SIVA, leading=22)
    half = CW / 2
    pt = Table([[Paragraph("Zaprimio: ____________________", pot),
                 Paragraph(f"Datum: {date.today().strftime('%d.%m.%Y')}  ·  Potpis: ____________________", pot)]],
               colWidths=[half, half])
    pt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    story.append(pt)

    doc.build(story)
    buf.seek(0)
    return buf
