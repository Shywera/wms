from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.skladiste import config as cfg
from app.modules.skladiste import service as svc
from app.modules.skladiste import pdf as pdfgen
from app.modules.skladiste.adapter import get_adapter
from app.modules.skladiste.models import Paleta, Prijem

router = APIRouter(prefix="/skladiste", tags=["skladiste"])
templates = Jinja2Templates(directory="app/templates")

# Hrvatski format brojeva: 1503 -> "1.503"
templates.env.filters["fmtn"] = lambda n: f"{int(n):,}".replace(",", ".") if n is not None else "—"


def _broj_aktivnih(db: Session, *uvjeti) -> int:
    stmt = select(func.count(Paleta.id)).where(Paleta.datum_out.is_(None), *uvjeti)
    return db.scalar(stmt) or 0


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    ukupno = cfg.UKUPNO_MJESTA
    zauzeto = _broj_aktivnih(db)
    slobodno = ukupno - zauzeto

    granica = date.today() + timedelta(days=30)
    istice = _broj_aktivnih(
        db, Paleta.rok_trajanja.is_not(None), Paleta.rok_trajanja <= granica
    )

    zone = []
    for z in cfg.ZONE:
        kapacitet = cfg.kapacitet_zone(z)
        zz = _broj_aktivnih(db, Paleta.pozicija.like(f"{z}%"))
        zone.append({
            "zona": z,
            "zauzeto": zz,
            "kapacitet": kapacitet,
            "postotak": round(zz / kapacitet * 100) if kapacitet else 0,
        })

    return templates.TemplateResponse(request, "skladiste/dashboard.html", {
        "zauzeto": zauzeto,
        "slobodno": slobodno,
        "ukupno": ukupno,
        "istice": istice,
        "postotak_ukupno": round(zauzeto / ukupno * 100) if ukupno else 0,
        "zone": zone,
    })


# ─── ERP lookup (skener barkoda -> ERP/mock) ─────────────────────────────────

@router.get("/lookup", response_class=HTMLResponse)
def lookup(request: Request, barkod: str = ""):
    """Pozove se na skeniranje barkoda; vrati HTML karticu artikla (iz ERP-a/mocka)."""
    artikl = get_adapter().lookup_barcode(barkod)
    return templates.TemplateResponse(request, "skladiste/_artikl.html", {
        "artikl": artikl,
        "barkod": barkod.strip(),
    })


def _to_float(v):
    try:
        return float(str(v).replace(",", ".")) if str(v).strip() else None
    except Exception:
        return None


def _to_date(v):
    try:
        return date.fromisoformat(str(v).strip()) if str(v).strip() else None
    except Exception:
        return None


# ─── Zaprimanje (glavno = više paleta, plan) ──────────────────────────────────

@router.get("/zaprimanje", response_class=HTMLResponse)
def zaprimanje(request: Request):
    return templates.TemplateResponse(request, "skladiste/zaprimanje.html", {})


@router.get("/zaprimanje/artikl", response_class=HTMLResponse)
def zaprimanje_artikl(request: Request, barkod: str = ""):
    """Skeniran barkod → kartica artikla + forma (broj paleta + zona) za generiranje plana."""
    barkod = (barkod or "").strip()
    artikl = get_adapter().lookup_barcode(barkod) if barkod else None
    return templates.TemplateResponse(request, "skladiste/_zaprimi_plan_forma.html", {
        "barkod": barkod, "artikl": artikl, "zone": cfg.ZONE,
    })


@router.post("/zaprimanje/plan", response_class=RedirectResponse)
def zaprimanje_plan(request: Request, barkod: str = Form(""), broj_paleta: int = Form(1),
                    zona: str = Form(""), db: Session = Depends(get_db)):
    barkod = barkod.strip()
    artikl = get_adapter().lookup_barcode(barkod) if barkod else None
    if artikl is None:
        return RedirectResponse("/skladiste/zaprimanje", status_code=303)
    broj_paleta = max(1, min(broj_paleta, 200))
    prijem = svc.kreiraj_plan(db, artikl.sifra, broj_paleta, zona=(zona.strip() or None))
    return RedirectResponse(f"/skladiste/zaprimanje/plan/{prijem.id}", status_code=303)


@router.get("/zaprimanje/plan/{pid}", response_class=HTMLResponse)
def zaprimanje_plan_view(request: Request, pid: int, db: Session = Depends(get_db)):
    prijem = db.get(Prijem, pid)
    if prijem is None:
        return RedirectResponse("/skladiste/zaprimanje", status_code=303)
    artikl = get_adapter().lookup_barcode(prijem.sifra)
    return templates.TemplateResponse(request, "skladiste/zaprimanje_plan.html", {
        "prijem": prijem, "stavke": prijem.stavke, "artikl": artikl,
    })


@router.get("/zaprimanje/plan/{pid}/pdf")
def zaprimanje_plan_pdf(pid: int, db: Session = Depends(get_db)):
    buf = pdfgen.pdf_plan(db, pid)
    if buf is None:
        return RedirectResponse("/skladiste/zaprimanje", status_code=303)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="plan-zaprimanja-{pid}.pdf"'})


@router.post("/zaprimanje/plan/{pid}/potvrdi", response_class=HTMLResponse)
def zaprimanje_plan_potvrdi(request: Request, pid: int, barkod: str = Form(""),
                            pozicija: str = Form(""), db: Session = Depends(get_db)):
    _, _, greska, upozorenje = svc.potvrdi_stavku(db, pid, barkod, pozicija)
    prijem = db.get(Prijem, pid)
    return templates.TemplateResponse(request, "skladiste/_plan_stavke.html", {
        "prijem": prijem, "stavke": prijem.stavke if prijem else [],
        "zadnja_greska": greska, "zadnja_upozorenje": upozorenje,
    })


@router.post("/zaprimanje/plan/{pid}/stavka/{sid}/vrati", response_class=HTMLResponse)
def zaprimanje_plan_vrati(request: Request, pid: int, sid: int, db: Session = Depends(get_db)):
    svc.vrati_stavku(db, pid, sid)
    prijem = db.get(Prijem, pid)
    return templates.TemplateResponse(request, "skladiste/_plan_stavke.html", {
        "prijem": prijem, "stavke": prijem.stavke if prijem else [],
        "zadnja_greska": None, "zadnja_upozorenje": None,
    })


@router.post("/zaprimanje/plan/{pid}/odustani", response_class=RedirectResponse)
def zaprimanje_plan_odustani(request: Request, pid: int, izbrisi: str = Form(""),
                             db: Session = Depends(get_db)):
    svc.odustani_plan(db, pid, izbrisi_palete=bool(izbrisi.strip()))
    return RedirectResponse("/skladiste/zaprimanje", status_code=303)


# ─── Zaprimanje jedne palete (pod-opcija) ─────────────────────────────────────

@router.get("/zaprimanje/jedna", response_class=HTMLResponse)
def zaprimanje_jedna(request: Request):
    return templates.TemplateResponse(request, "skladiste/zaprimanje_jedna.html", {})


@router.get("/zaprimanje/jedna/artikl", response_class=HTMLResponse)
def zaprimanje_jedna_artikl(request: Request, barkod: str = "", db: Session = Depends(get_db)):
    barkod = (barkod or "").strip()
    artikl = get_adapter().lookup_barcode(barkod) if barkod else None
    sifra = artikl.sifra if artikl else None
    prijedlozi = svc.predlozi_mjesta(db, 1, sifra=sifra)
    predlozeno = prijedlozi[0] if prijedlozi else ""
    return templates.TemplateResponse(request, "skladiste/_zaprimi_forma.html", {
        "barkod": barkod, "artikl": artikl, "predlozeno": predlozeno,
        "nema_mjesta": not prijedlozi,
    })


@router.post("/zaprimanje/jedna/zaprimi", response_class=HTMLResponse)
def zaprimanje_jedna_zaprimi(
    request: Request,
    barkod: str = Form(""), pozicija: str = Form(""),
    sifra: str = Form(""), naziv: str = Form(""), kolicina: str = Form(""),
    jedinica: str = Form(""), rok_trajanja: str = Form(""), lot: str = Form(""),
    db: Session = Depends(get_db),
):
    barkod = barkod.strip()
    artikl = get_adapter().lookup_barcode(barkod) if barkod else None
    if artikl:
        paleta, greska = svc.zaprimi_paletu(
            db, qr_raw=barkod, pozicija=pozicija, sifra=artikl.sifra, naziv=artikl.naziv,
            kolicina=artikl.kolicina, jedinica=artikl.jedinica,
            rok_trajanja=artikl.rok_trajanja, datum_ulaza=artikl.datum, lot=artikl.lot,
            izvor="erp",
        )
    else:
        paleta, greska = svc.zaprimi_paletu(
            db, qr_raw=barkod, pozicija=pozicija, sifra=(sifra or None),
            naziv=(naziv or None), kolicina=_to_float(kolicina), jedinica=(jedinica or None),
            rok_trajanja=_to_date(rok_trajanja), lot=(lot or None), izvor="rucno",
        )
    return templates.TemplateResponse(request, "skladiste/_zaprimi_rezultat.html", {
        "paleta": paleta, "greska": greska,
    })


# ─── Izdavanje (glavno = po količini araka) ───────────────────────────────────

@router.get("/izdaj", response_class=HTMLResponse)
def izdaj(request: Request):
    return templates.TemplateResponse(request, "skladiste/izdaj.html", {})


@router.post("/izdaj/predlozi", response_class=HTMLResponse)
def izdaj_predlozi(request: Request, sifra: str = Form(""), araka: str = Form(""),
                   metoda: str = Form("fifo"), db: Session = Depends(get_db)):
    sifra = sifra.strip()
    a = _to_float(araka) or 0
    if not sifra or a <= 0:
        return templates.TemplateResponse(request, "skladiste/_izdaj_predlog.html",
                                          {"p": None, "greska": "Upiši šifru i broj araka (> 0)."})
    p = svc.predlozi_izdavanje(db, sifra, a, metoda if metoda in ("fifo", "fefo") else "fifo")
    return templates.TemplateResponse(request, "skladiste/_izdaj_predlog.html", {"p": p, "greska": None})


@router.post("/izdaj/izvrsi", response_class=HTMLResponse)
def izdaj_izvrsi(request: Request, ids: str = Form(""), db: Session = Depends(get_db)):
    paleta_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    n = svc.izvrsi_izdavanje(db, paleta_ids)
    return templates.TemplateResponse(request, "skladiste/_izdaj_gotovo.html", {"n": n})


# ─── Izdavanje jedne palete (pod-opcija, skener) ──────────────────────────────

@router.get("/izdaj/jedna", response_class=HTMLResponse)
def izdaj_jedna(request: Request):
    return templates.TemplateResponse(request, "skladiste/izdaj_jedna.html", {})


@router.get("/izdaj/jedna/skeniraj", response_class=HTMLResponse)
def izdaj_jedna_skeniraj(request: Request, barkod: str = "", db: Session = Depends(get_db)):
    barkod = (barkod or "").strip()
    palete = svc.aktivne_za_barkod(db, barkod) if barkod else []
    return templates.TemplateResponse(request, "skladiste/_izdaj_forma.html", {
        "barkod": barkod, "palete": palete,
    })


@router.post("/izdaj/jedna/{paleta_id}", response_class=HTMLResponse)
def izdaj_jedna_potvrdi(request: Request, paleta_id: int, db: Session = Depends(get_db)):
    paleta, poruka = svc.izdaj_paletu(db, paleta_id)
    return templates.TemplateResponse(request, "skladiste/_izdaj_rezultat.html", {
        "paleta": paleta, "poruka": poruka,
    })


# ─── Inventura ────────────────────────────────────────────────────────────────

@router.get("/inventura", response_class=HTMLResponse)
def inventura(request: Request, db: Session = Depends(get_db)):
    inv = svc.aktivna_inventura(db)
    skenirano = 0
    if inv:
        from app.modules.skladiste.models import InventuraStavka
        skenirano = db.scalar(
            select(func.count(InventuraStavka.id)).where(InventuraStavka.inventura_id == inv.id)
        ) or 0
    return templates.TemplateResponse(request, "skladiste/inventura.html", {
        "inv": inv, "skenirano": skenirano, "izvjestaj": None,
    })


@router.post("/inventura/start")
def inventura_start(request: Request, db: Session = Depends(get_db)):
    svc.pokreni_inventuru(db)
    return RedirectResponse("/skladiste/inventura", status_code=303)


@router.post("/inventura/skeniraj", response_class=HTMLResponse)
def inventura_skeniraj(request: Request, barkod: str = Form(""), pozicija: str = Form(""),
                       db: Session = Depends(get_db)):
    broj, greska = svc.skeniraj_inventuru(db, barkod, pozicija)
    return templates.TemplateResponse(request, "skladiste/_inventura_scan.html", {
        "broj": broj, "greska": greska, "zadnji": barkod.strip(),
    })


@router.post("/inventura/zatvori", response_class=HTMLResponse)
def inventura_zatvori(request: Request, db: Session = Depends(get_db)):
    izvjestaj = svc.zatvori_inventuru(db)
    return templates.TemplateResponse(request, "skladiste/inventura.html", {
        "inv": None, "skenirano": 0, "izvjestaj": izvjestaj,
    })


@router.post("/inventura/ponisti")
def inventura_ponisti(request: Request, db: Session = Depends(get_db)):
    svc.ponisti_inventuru(db)
    return RedirectResponse("/skladiste/inventura", status_code=303)


# ─── Popis svih paleta ────────────────────────────────────────────────────────

@router.get("/palete", response_class=HTMLResponse)
def palete(request: Request):
    return templates.TemplateResponse(request, "skladiste/palete.html", {})


@router.get("/palete/search", response_class=HTMLResponse)
def palete_search(request: Request, q: str = "", sve: str = "", db: Session = Depends(get_db)):
    stmt = select(Paleta)
    if not sve:
        stmt = stmt.where(Paleta.datum_out.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Paleta.sifra.ilike(like), Paleta.naziv.ilike(like), Paleta.qr_raw.ilike(like),
            Paleta.pozicija.ilike(like), Paleta.lot.ilike(like),
        ))
    stmt = stmt.order_by(Paleta.datum_out.is_(None).desc(), Paleta.datum_in.desc())
    palete = db.scalars(stmt).all()
    return templates.TemplateResponse(request, "skladiste/_palete_tablica.html",
                                      {"palete": palete, "q": q, "sve": sve})


# ─── Karta skladišta ──────────────────────────────────────────────────────────

@router.get("/mapa", response_class=HTMLResponse)
def mapa(request: Request, db: Session = Depends(get_db)):
    zone = []
    for z in cfg.ZONE:
        kapacitet = cfg.kapacitet_zone(z)
        zz = _broj_aktivnih(db, Paleta.pozicija.like(f"{z}%"))
        zone.append({
            "zona": z, "zauzeto": zz, "kapacitet": kapacitet,
            "postotak": round(zz / kapacitet * 100) if kapacitet else 0,
        })
    return templates.TemplateResponse(request, "skladiste/mapa.html", {
        "tlocrt": svc.mapa_tlocrt(db), "zone": zone,
    })


@router.get("/stanje/pdf")
def stanje_pdf(db: Session = Depends(get_db)):
    buf = pdfgen.pdf_stanje(db)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="stanje-skladista-{date.today().isoformat()}.pdf"'})


@router.get("/mapa/{zona}", response_class=HTMLResponse)
def mapa_zona(request: Request, zona: str, db: Session = Depends(get_db)):
    zona = zona.upper()
    if zona not in cfg.ZONE:
        return RedirectResponse("/skladiste/mapa", status_code=303)
    regali = svc.mapa_zone(db, zona)
    zauzeto = _broj_aktivnih(db, Paleta.pozicija.like(f"{zona}%"))
    return templates.TemplateResponse(request, "skladiste/mapa_zona.html", {
        "zona": zona, "regali": regali,
        "zauzeto": zauzeto, "kapacitet": cfg.kapacitet_zone(zona),
    })


# ─── Prioriteti (pravila smještaja po šifri) ──────────────────────────────────

MODOVI = {
    "blize_ulazu": "Bliže ulazu (zadano)",
    "blize_kraju": "Bliže kraju",
    "popuni_zapocete": "Popuni započete regale",
}


@router.get("/prioriteti", response_class=HTMLResponse)
def prioriteti(request: Request, db: Session = Depends(get_db)):
    from app.modules.skladiste.models import Prioritet
    pravila = db.scalars(select(Prioritet).order_by(Prioritet.sifra)).all()
    return templates.TemplateResponse(request, "skladiste/prioriteti.html", {
        "pravila": pravila, "modovi": MODOVI,
        "regali": [r.naziv for r in cfg.REGALI],
    })


@router.post("/prioriteti", response_class=RedirectResponse)
def prioriteti_dodaj(
    request: Request,
    sifra: str = Form(""), mod: str = Form("standardno"),
    rack_ids: str = Form(""), napomena: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.modules.skladiste.models import Prioritet
    sifra = sifra.strip()
    if sifra:
        # normaliziraj regale (velika slova, samo postojeći)
        valjani = {r.naziv for r in cfg.REGALI}
        regali = ",".join(
            x.strip().upper() for x in rack_ids.split(",")
            if x.strip().upper() in valjani
        )
        db.add(Prioritet(
            sifra=sifra, mod=(mod if mod in MODOVI else "blize_ulazu"),
            rack_ids=(regali or None), napomena=(napomena.strip() or None), aktivan=True,
        ))
        db.commit()
    return RedirectResponse("/skladiste/prioriteti", status_code=303)


@router.post("/prioriteti/{pid}/toggle", response_class=RedirectResponse)
def prioriteti_toggle(request: Request, pid: int, db: Session = Depends(get_db)):
    from app.modules.skladiste.models import Prioritet
    p = db.get(Prioritet, pid)
    if p:
        p.aktivan = not p.aktivan
        db.commit()
    return RedirectResponse("/skladiste/prioriteti", status_code=303)


@router.post("/prioriteti/{pid}/obrisi", response_class=RedirectResponse)
def prioriteti_obrisi(request: Request, pid: int, db: Session = Depends(get_db)):
    from app.modules.skladiste.models import Prioritet
    p = db.get(Prioritet, pid)
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/skladiste/prioriteti", status_code=303)
