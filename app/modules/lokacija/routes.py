"""Jednostavni tok BEZ API-ja: poveži QR palete s pozicijom, jedna po jedna.

Zaprimanje: skeniraj paletu -> odaberi poziciju na karti ILI skeniraj QR pozicije.
  - Više paleta na istu poziciju je DOZVOLJENO (reslovi/ostaci) uz potvrdu.
Izdavanje:  skeniraj paletu -> potvrdi (jedna po jedna).
Audit: ove rute SAME pišu detaljan zapis (koja paleta, gdje, tko).
"""
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.models import AuditLog
from app.modules.skladiste import config as cfg
from app.modules.skladiste import service as svc
from app.modules.skladiste.adapter import get_adapter
from app.modules.skladiste.models import Paleta, SkladisteEvent

router = APIRouter(prefix="/lokacija", tags=["lokacija"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fmtn"] = lambda n: f"{int(n):,}".replace(",", ".") if n is not None else "—"


def _audit(db: Session, request: Request, akcija: str, detalji: str) -> None:
    u = getattr(request.state, "user", None)
    db.add(AuditLog(user_id=getattr(u, "id", None), username=getattr(u, "username", None),
                    metoda=request.method, putanja=request.url.path, akcija=akcija, detalji=detalji))


def _na_poziciji(db: Session, poz: str) -> list[Paleta]:
    return list(db.scalars(
        select(Paleta).where(Paleta.pozicija == poz, Paleta.datum_out.is_(None))
        .order_by(Paleta.datum_in)).all())


def _stanje_po_poziciji(db: Session, zona: str) -> dict[str, dict]:
    """Po poziciji: broj aktivnih paleta + ima li koju nepotpunu (za boju karte)."""
    pals = db.scalars(select(Paleta).where(
        Paleta.datum_out.is_(None), Paleta.pozicija.like(f"{zona}%"))).all()
    out: dict[str, dict] = {}
    for p in pals:
        s = out.setdefault(p.pozicija, {"n": 0, "np": False})
        s["n"] += 1
        if p.nepotpuna:
            s["np"] = True
    return out


# ─── Zaprimanje (jedna paleta) ────────────────────────────────────────────────

@router.get("/zaprimi", response_class=HTMLResponse)
def zaprimi(request: Request):
    return templates.TemplateResponse(request, "lokacija/zaprimi.html", {})


@router.get("/zaprimi/skeniraj", response_class=HTMLResponse)
def zaprimi_skeniraj(request: Request, barkod: str = "", db: Session = Depends(get_db)):
    barkod = (barkod or "").strip()
    if not barkod:
        return templates.TemplateResponse(request, "lokacija/_odabir.html", {
            "barkod": "", "zone": cfg.ZONE, "vec": None, "predlozeno": None, "greska": "Skeniraj barkod palete."})
    postojece = svc.aktivne_za_barkod(db, barkod)
    predlozeno = None
    if not postojece:
        try:
            info = get_adapter().lookup_barcode(barkod)
        except Exception:
            info = None
        if info and info.sifra:
            prijedlozi = svc.predlozi_mjesta(db, 1, sifra=info.sifra)
            predlozeno = prijedlozi[0] if prijedlozi else None
    return templates.TemplateResponse(request, "lokacija/_odabir.html", {
        "barkod": barkod, "zone": cfg.ZONE, "predlozeno": predlozeno,
        "vec": postojece[0] if postojece else None, "greska": None})


@router.get("/zaprimi/karta/{zona}", response_class=HTMLResponse)
def zaprimi_karta(request: Request, zona: str, barkod: str = "", nepotpuna: str = "",
                  db: Session = Depends(get_db)):
    zona = (zona or "").upper()
    if zona not in cfg.ZONE:
        zona = cfg.ZONE[0]
    return templates.TemplateResponse(request, "lokacija/_karta.html", {
        "barkod": (barkod or "").strip(), "zona": zona, "zone": cfg.ZONE,
        "regali": svc.mapa_zone(db, zona), "stanje": _stanje_po_poziciji(db, zona),
        "nepotpuna": nepotpuna in ("1", "on", "true")})


@router.post("/postavi", response_class=HTMLResponse)
def postavi(request: Request, barkod: str = Form(""), pozicija: str = Form(""),
            potvrdi: str = Form(""), nepotpuna: str = Form(""), db: Session = Depends(get_db)):
    barkod = (barkod or "").strip()
    poz = cfg.parse_pozicija((pozicija or "").strip().upper())
    np = nepotpuna in ("1", "on", "true")
    ctx = {"barkod": barkod, "zone": cfg.ZONE, "vec": None}
    if not barkod:
        return templates.TemplateResponse(request, "lokacija/_odabir.html",
                                          {**ctx, "greska": "Nema barkoda palete — skeniraj ponovo."})
    if poz is None:
        return templates.TemplateResponse(request, "lokacija/_odabir.html",
                                          {**ctx, "greska": f"Nevaljana pozicija: '{pozicija}'. Format npr. A2P5V3."})

    # ista paleta već negdje aktivna? (ne dupliciraj fizičku paletu)
    vec = svc.aktivne_za_barkod(db, barkod)
    if vec:
        return templates.TemplateResponse(request, "lokacija/_odabir.html",
                                          {**ctx, "vec": vec[0], "greska": None})

    postojece = _na_poziciji(db, poz.kod)
    # zauzeto + nije potvrđeno -> traži potvrdu za slaganje
    if postojece and potvrdi != "1":
        return templates.TemplateResponse(request, "lokacija/_potvrdi.html", {
            "barkod": barkod, "pozicija": poz.kod, "postojece": postojece, "nepotpuna": np,
            "ima_nepotpunu": any(x.nepotpuna for x in postojece)})

    # Ako se slaže na zauzetu poziciju -> i nova i POSTOJEĆE su nepotpune (jer stane još).
    slaganje = bool(postojece)
    np_final = np or slaganje
    if slaganje:
        for x in postojece:
            x.nepotpuna = True

    # Dohvati identitet palete (šifra/naziv/broj araka) preko ERP adaptera.
    # Mock radi odmah; s legacy ERP-om (ERP_ADAPTER=erp) daje stvarne podatke. Best-effort:
    # ako lookup ne uspije, paleta se svejedno sprema (samo bez šifre → ne može po zahtjevnici).
    try:
        info = get_adapter().lookup_barcode(barkod)
    except Exception:
        info = None
    p = Paleta(qr_raw=barkod, pozicija=poz.kod,
               izvor=("erp" if info else "rucno"),
               datum_ulaza=(info.datum if (info and info.datum) else date.today()),
               nepotpuna=np_final,
               sifra=(info.sifra if info else None),
               naziv=(info.naziv if info else None),
               kolicina=(info.kolicina if info else None),
               jedinica=(info.jedinica if info else None),
               rok_trajanja=(info.rok_trajanja if info else None),
               lot=(info.lot if info else None))
    db.add(p)
    n = len(postojece) + 1
    oznake = (["nepotpuna"] if np_final else []) + ([f"{n}. na poziciji"] if n > 1 else [])
    db.add(SkladisteEvent(tip="zaprimanje", poruka=f"Paleta {barkod} na {poz.kod}",
                          detalji=", ".join(oznake) or "puna paleta"))
    db.commit(); db.refresh(p)
    _audit(db, request, "Zaprimanje palete",
           f"{barkod} → {poz.kod}" + (f" ({', '.join(oznake)})" if oznake else ""))
    db.commit()
    return templates.TemplateResponse(request, "lokacija/_ok.html",
                                      {"paleta": p, "broj": n, "nepotpuna": np_final})


# ─── Izdavanje (jedna paleta) ─────────────────────────────────────────────────

@router.get("/izdaj", response_class=HTMLResponse)
def izdaj(request: Request):
    return templates.TemplateResponse(request, "lokacija/izdaj.html", {})


@router.get("/izdaj/skeniraj", response_class=HTMLResponse)
def izdaj_skeniraj(request: Request, barkod: str = "", db: Session = Depends(get_db)):
    barkod = (barkod or "").strip()
    palete = svc.aktivne_za_barkod(db, barkod) if barkod else []
    return templates.TemplateResponse(request, "lokacija/_izdaj.html", {
        "barkod": barkod, "palete": palete})


@router.post("/izdaj/{paleta_id}", response_class=HTMLResponse)
def izdaj_potvrdi(request: Request, paleta_id: int, db: Session = Depends(get_db)):
    paleta, poruka = svc.izdaj_paletu(db, paleta_id)
    if paleta is not None:
        _audit(db, request, "Izdavanje palete", f"{paleta.qr_raw} ← {paleta.pozicija}")
        db.commit()
    return templates.TemplateResponse(request, "lokacija/_izdaj_ok.html", {
        "paleta": paleta, "greska": None if paleta else poruka,
        "upozorenje": poruka if paleta else None})
