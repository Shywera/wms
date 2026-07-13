"""Rute za izdavanje po zahtjevnici (bankomat-jednostavan tok).

Tok: uvezi datoteku → popis papirnih stavki → klik "Izdaj" na stavci → software predloži
palete (FIFO) → skeniraj paletu za potvrdu → izdano ✓ → sljedeća stavka.
"""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.modules.auth.models import AuditLog
from app.modules.zahtjevnica import parser, service as zsvc
from app.modules.zahtjevnica.models import Zahtjevnica, ZahtjevnicaStavka

router = APIRouter(prefix="/zahtjevnica", tags=["zahtjevnica"])
templates = Jinja2Templates(directory="app/templates")


def _fmtn(n):
    """Hrvatski format broja: tisućice točkom, decimale zarezom (5.600 ; 2,5)."""
    if n is None:
        return "—"
    n = float(n)
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}".replace(",", ".")
    cijeli, dec = f"{n:,.2f}".split(".")
    dec = dec.rstrip("0")
    cijeli = cijeli.replace(",", ".")
    return f"{cijeli},{dec}" if dec else cijeli


templates.env.filters["fmtn"] = _fmtn


def _audit(db: Session, request: Request, akcija: str, detalji: str) -> None:
    u = getattr(request.state, "user", None)
    db.add(AuditLog(user_id=getattr(u, "id", None), username=getattr(u, "username", None),
                    metoda=request.method, putanja=request.url.path, akcija=akcija, detalji=detalji))


def _load(db: Session, id: int) -> Zahtjevnica | None:
    return db.scalar(select(Zahtjevnica).where(Zahtjevnica.id == id)
                     .options(selectinload(Zahtjevnica.stavke)))


def _row(request, stavka, mode="init", predlog=None, greska=None, oob=False):
    return templates.TemplateResponse(request, "zahtjevnica/_stavka.html", {
        "s": stavka, "z": stavka.zahtjevnica, "mode": mode,
        "predlog": predlog, "greska": greska, "oob": oob,
    })


# ─── Popis + uvoz ─────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def popis(request: Request, dup: int = 0, db: Session = Depends(get_db)):
    zahtjevnice = db.scalars(select(Zahtjevnica).order_by(Zahtjevnica.id.desc()).limit(30)).all()
    return templates.TemplateResponse(request, "zahtjevnica/popis.html", {
        "zahtjevnice": zahtjevnice,
        "greska": request.query_params.get("greska"),
        "dup_id": dup or None,
    })


@router.post("/uvoz", response_class=HTMLResponse)
async def uvoz(request: Request, datoteka: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await datoteka.read()
    redci, greska = parser.parsiraj(datoteka.filename or "", data)
    if greska:
        return RedirectResponse(f"/zahtjevnica?greska={greska}", status_code=303)
    z, dup = zsvc.kreiraj(db, datoteka.filename or "", redci)
    _audit(db, request, "Uvoz zahtjevnice",
           f"#{z.id} {z.oznaka} · {z.broj_papir} papirnih / {len(z.stavke)} stavki")
    db.commit()
    url = f"/zahtjevnica/{z.id}"
    if dup is not None:
        url += f"?dup={dup.id}"
    return RedirectResponse(url, status_code=303)


# ─── Detalj (ATM ekran) ───────────────────────────────────────────────────────

def _stanje_ostalih(db: Session, z: Zahtjevnica) -> dict:
    """Za NE-papirne stavke: ima li te šifre ipak na stanju ovog skladišta?
    Vrati {sifra: {"n": broj_paleta, "kol": ukupna_kolicina}}."""
    from sqlalchemy import func as sqlfunc
    from app.modules.skladiste.models import Paleta
    sifre = [s.sifra for s in z.ostale_stavke if s.sifra]
    if not sifre:
        return {}
    rows = db.execute(
        select(Paleta.sifra, sqlfunc.count(Paleta.id), sqlfunc.coalesce(sqlfunc.sum(Paleta.kolicina), 0))
        .where(Paleta.datum_out.is_(None), Paleta.sifra.in_(sifre))
        .group_by(Paleta.sifra)
    ).all()
    return {s: {"n": n, "kol": float(k or 0)} for s, n, k in rows}


@router.get("/{id}", response_class=HTMLResponse)
def detalj(request: Request, id: int, db: Session = Depends(get_db)):
    z = _load(db, id)
    if not z:
        return RedirectResponse("/zahtjevnica", status_code=303)
    return templates.TemplateResponse(request, "zahtjevnica/detalj.html", {
        "z": z, "dup_id": request.query_params.get("dup"),
        "stanje_ostalih": _stanje_ostalih(db, z)})


@router.post("/{id}/obrisi", response_class=RedirectResponse)
def obrisi(request: Request, id: int, db: Session = Depends(get_db)):
    z = db.get(Zahtjevnica, id)
    if z:
        db.delete(z); db.commit()
    return RedirectResponse("/zahtjevnica", status_code=303)


# ─── Izdavanje stavke (HTMX) ──────────────────────────────────────────────────

def _stavka(db: Session, id: int, sid: int) -> ZahtjevnicaStavka | None:
    s = db.get(ZahtjevnicaStavka, sid)
    return s if (s and s.zahtjevnica_id == id) else None


@router.get("/{id}/stavka/{sid}", response_class=HTMLResponse)
def stavka_red(request: Request, id: int, sid: int, db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if not s:
        return HTMLResponse("", status_code=404)
    return _row(request, s, "init")


@router.post("/{id}/stavka/{sid}/predlozi", response_class=HTMLResponse)
def stavka_predlozi(request: Request, id: int, sid: int, db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if not s:
        return HTMLResponse("", status_code=404)
    if not s.sifra:
        return _row(request, s, "init", greska="Stavka nema šifru — ne može se izdati.")
    predlog = zsvc.predlozi(db, s)
    return _row(request, s, "predlog", predlog=predlog)


@router.post("/{id}/stavka/{sid}/izdaj", response_class=HTMLResponse)
def stavka_izdaj(request: Request, id: int, sid: int, paleta_ids: str = Form(""),
                 barkod: str = Form(""), db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if not s:
        return HTMLResponse("", status_code=404)
    ids = [int(x) for x in paleta_ids.split(",") if x.strip().isdigit()]
    # Provjera skenom: ako je barkod upisan, mora odgovarati jednoj od predloženih paleta.
    barkod = (barkod or "").strip()
    if barkod:
        aktivne = {p.id: p for p in zsvc.svc.aktivne_za_sifru(db, s.sifra, "fifo")}
        if not any((aktivne.get(pid) and aktivne[pid].qr_raw == barkod) for pid in ids):
            predlog = zsvc.predlozi(db, s)
            return _row(request, s, "predlog", predlog=predlog,
                        greska=f"Skenirana paleta ({barkod}) nije među predloženima. Skeniraj jednu od prikazanih.")
    n, greska = zsvc.izdaj_stavku(db, s, ids)
    if greska:
        predlog = zsvc.predlozi(db, s)
        return _row(request, s, "predlog", predlog=predlog, greska=greska)
    _audit(db, request, "Izdavanje po zahtjevnici",
           f"#{id} · {s.sifra} · {n} paleta ({', '.join(map(str, ids))})")
    db.commit()
    return _row(request, s, "init", oob=True)


@router.post("/{id}/stavka/{sid}/ponisti", response_class=HTMLResponse)
def stavka_ponisti(request: Request, id: int, sid: int, db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if not s:
        return HTMLResponse("", status_code=404)
    zsvc.ponisti_izdavanje(db, s)
    return _row(request, s, "init", oob=True)


# ─── Ručno uključivanje ostalih stavki (npr. boja koja je ipak na stanju) ─────

@router.post("/{id}/stavka/{sid}/ukljuci", response_class=RedirectResponse)
def stavka_ukljuci(request: Request, id: int, sid: int, db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if s and not s.je_papir and not s.izdano:
        s.ukljucena = True
        _audit(db, request, "Zahtjevnica: stavka dodana u izdavanje",
               f"#{id} · {s.sifra} · {s.naziv or ''}")
        db.commit()
    return RedirectResponse(f"/zahtjevnica/{id}", status_code=303)


@router.post("/{id}/stavka/{sid}/iskljuci", response_class=RedirectResponse)
def stavka_iskljuci(request: Request, id: int, sid: int, db: Session = Depends(get_db)):
    s = _stavka(db, id, sid)
    if s and s.ukljucena and not s.izdano:
        s.ukljucena = False
        db.commit()
    return RedirectResponse(f"/zahtjevnica/{id}", status_code=303)
