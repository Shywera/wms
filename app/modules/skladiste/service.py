"""Skladište — servisna logika (placement, zaprimanje, izdavanje, inventura).

Drži poslovnu logiku izvan ruta. Sve funkcije primaju `Session`.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.skladiste import config as cfg
from app.modules.skladiste.adapter import get_adapter
from app.modules.skladiste.models import (
    Inventura, InventuraStavka, Paleta, Prijem, PrijemStavka, Prioritet, SkladisteEvent,
)


# ─── Pozicije / placement ─────────────────────────────────────────────────────

def zauzete_pozicije(db: Session) -> set[str]:
    return set(db.scalars(select(Paleta.pozicija).where(Paleta.datum_out.is_(None))).all())


def dohvati_prioritet(db: Session, sifra: str | None) -> Prioritet | None:
    if not sifra:
        return None
    return db.scalar(
        select(Prioritet).where(Prioritet.sifra == sifra, Prioritet.aktivan == True)  # noqa: E712
    )


def predlozi_mjesta(db: Session, n: int = 1, sifra: str | None = None,
                    zona: str | None = None) -> list[str]:
    """Predloži do `n` slobodnih, validnih pozicija prema prioritetnim pravilima za šifru.
    Port iz legacy WMS-a: uvijek prvo klasteriranje uz istu šifru, pa mod smještaja
    (standardno / puni_rupe / lijevi / strogo_lijevo) unutar dozvoljenih regala.
    `zona` (A-D) dodatno ograničava smještaj na tu zonu (korisnik bira gdje zaprima).
    MOŽE vratiti manje od `n` (nestašica) — pozivatelj MORA provjeriti duljinu (bug B9).

    Napomena: 'lijevi'/'strogo_lijevo' koriste redoslijed regala u `REGALI` kao zamjenu
    za X-os dok ne uvedemo koordinate karte (Faza karte).
    """
    zauzete = zauzete_pozicije(db)
    pravilo = dohvati_prioritet(db, sifra)
    mod = pravilo.mod if pravilo else "standardno"
    dozvoljeni = None
    if pravilo and pravilo.rack_ids:
        dozvoljeni = [r.strip().upper() for r in pravilo.rack_ids.split(",") if r.strip()]

    zona = (zona or "").strip().upper() or None
    svi = [r for r in cfg.REGALI if not zona or r.zona == zona]  # univerzum (po zoni)
    rack_x = {r.naziv: i for i, r in enumerate(cfg.REGALI)}  # zamjena za X-os

    def pozicije(rack):  # redoslijed punjenja: V1 prvo, pa pozicije
        for v in range(1, rack.broj_visina + 1):
            for p in range(1, rack.broj_pozicija + 1):
                yield f"{rack.naziv}P{p}V{v}"

    def fill(rack):
        puno = sum(1 for poz in pozicije(rack) if poz in zauzete)
        return puno / rack.kapacitet if rack.kapacitet else 0

    def _uzastopne(racks, br):
        for rack in racks:
            for v in range(1, rack.broj_visina + 1):
                run = []
                for p in range(1, rack.broj_pozicija + 1):
                    poz = f"{rack.naziv}P{p}V{v}"
                    if poz not in zauzete:
                        run.append(poz)
                        if len(run) == br:
                            return run
                    else:
                        run = []
        return []

    def _bilo_koje(racks, br):
        free = []
        for rack in racks:
            for poz in pozicije(rack):
                if poz not in zauzete:
                    free.append(poz)
                    if len(free) == br:
                        return free
        return free

    def _trazi(racks, br):
        r = _uzastopne(racks, br)
        return r if len(r) == br else _bilo_koje(racks, br)

    base = [r for r in svi if not dozvoljeni or r.naziv in dozvoljeni]

    # 1) Uvijek prvo: pokraj iste šifre (klasteriranje)
    if sifra:
        aktivne = db.scalars(
            select(Paleta.pozicija).where(Paleta.datum_out.is_(None), Paleta.sifra == sifra)
        ).all()
        regali_iste = {p.regal for p in (cfg.parse_pozicija(x) for x in aktivne) if p}
        same = [r for r in base if r.naziv in regali_iste]
        if same:
            res = _trazi(same, n)
            if len(res) == n:
                return res

    # 2) Po modu (prostorno — ulaz je gore lijevo, A1/P1 = najbliže ulazu)
    if mod == "popuni_zapocete":
        partial = sorted([r for r in base if 0 < fill(r) < 1], key=fill, reverse=True)
        empty = [r for r in base if fill(r) == 0]
        res = _trazi(partial + empty, n)
        if len(res) == n or dozvoljeni:
            return res
        ap = sorted([r for r in svi if 0 < fill(r) < 1], key=fill, reverse=True)
        ae = [r for r in svi if fill(r) == 0]
        return _trazi(ap + ae, n)

    if mod == "blize_kraju":
        # najdalje od ulaza prvo = obrnuti redoslijed punjenja, unutar base regala
        dozv = {r.naziv for r in base}
        kand = [p for p in reversed(cfg.sve_pozicije())
                if p not in zauzete and cfg.parse_pozicija(p).regal in dozv]
        return kand[:n]

    # "bliže ulazu" (zadano) — prvo slobodno u redoslijedu punjenja (A1/P1 prvo)
    res = _trazi(base, n)
    if len(res) == n or dozvoljeni:
        return res
    return _trazi(list(svi), n)


# ─── Zaprimanje ───────────────────────────────────────────────────────────────

def zaprimi_paletu(
    db: Session, *, qr_raw: str, pozicija: str,
    sifra: str | None = None, naziv: str | None = None,
    kolicina: float | None = None, jedinica: str | None = None,
    rok_trajanja: date | None = None, datum_ulaza: date | None = None,
    lot: str | None = None, izvor: str = "erp",
) -> tuple[Paleta | None, str | None]:
    """Spremi paletu na poziciju. Vrati (paleta, None) ili (None, greska)."""
    poz = cfg.parse_pozicija(pozicija)
    if poz is None:
        return None, f"Nevaljana pozicija: {pozicija}"
    if poz.kod in zauzete_pozicije(db):
        return None, f"Pozicija {poz.kod} je već zauzeta."

    p = Paleta(
        qr_raw=(qr_raw or "").strip(), pozicija=poz.kod,
        sifra=sifra, naziv=naziv, kolicina=kolicina, jedinica=jedinica,
        rok_trajanja=rok_trajanja, datum_ulaza=datum_ulaza or date.today(),
        lot=lot, izvor=izvor,
    )
    db.add(p)
    db.add(SkladisteEvent(tip="zaprimanje", poruka=f"Zaprimljena paleta na {poz.kod}",
                          detalji=f"barkod={qr_raw} sifra={sifra} kol={kolicina}"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None, f"Pozicija {poz.kod} je upravo zauzeta — pokušaj drugu."
    db.refresh(p)
    return p, None


# ─── Zaprimanje — plan (više paleta) ──────────────────────────────────────────

def kreiraj_plan(db: Session, sifra: str, broj_paleta: int, zona: str | None = None) -> Prijem:
    """Generiraj plan zaprimanja: predloži pozicije (po prioritetima + zoni) i kreiraj
    Prijem + PrijemStavka stavke. `len(prijem.stavke)` može biti < broj_paleta (nestašica)."""
    pozicije = predlozi_mjesta(db, broj_paleta, sifra=sifra, zona=zona)
    prijem = Prijem(sifra=sifra, broj_paleta=broj_paleta, datum_plan=date.today(), status="aktivan")
    db.add(prijem)
    db.flush()
    for i, poz in enumerate(pozicije, 1):
        db.add(PrijemStavka(prijem_id=prijem.id, redni_broj=i, pozicija=poz))
    db.add(SkladisteEvent(
        tip="plan_zaprimanja",
        poruka=f"Plan #{prijem.id}: {len(pozicije)}/{broj_paleta} mjesta · šifra {sifra} · zona {zona or 'auto'}",
    ))
    db.commit()
    db.refresh(prijem)
    return prijem


def potvrdi_stavku(db: Session, prijem_id: int, barkod: str,
                   pozicija_override: str | None = None):
    """Potvrdi sljedeću nepotvrđenu stavku plana: spremi paletu na njenu (ili override)
    poziciju. Vrati (paleta, stavka, greska, upozorenje)."""
    prijem = db.get(Prijem, prijem_id)
    if prijem is None:
        return None, None, "Plan nije pronađen.", None
    stavka = db.scalar(
        select(PrijemStavka).where(
            PrijemStavka.prijem_id == prijem_id, PrijemStavka.datum_potvrda.is_(None)
        ).order_by(PrijemStavka.redni_broj)
    )
    if stavka is None:
        return None, None, "Sve palete su već potvrđene.", None

    if not (barkod or "").strip():
        return None, stavka, "Skeniraj barkod palete prije potvrde.", None

    predlozeno = stavka.pozicija
    rucna = (pozicija_override or "").strip()
    # Ručno upisana pozicija MORA biti valjana (postojeći regal + pozicija/visina u granicama).
    if rucna:
        poz = cfg.parse_pozicija(rucna)
        if poz is None:
            return None, stavka, (
                f"Nevaljana pozicija: '{rucna}'. "
                "Format je npr. A2P5V3 (zona+regal · P pozicija · V visina)."), None
        pozicija = poz.kod
    else:
        pozicija = predlozeno
    # Identitet (naziv/rok) iz šifre plana; količina+lot po paleti iz skeniranog barkoda
    a_id = get_adapter().lookup_barcode(prijem.sifra)
    a_pal = get_adapter().lookup_barcode(barkod) if barkod else None
    paleta, greska = zaprimi_paletu(
        db, qr_raw=barkod, pozicija=pozicija, sifra=prijem.sifra,
        naziv=(a_id.naziv if a_id else None),
        kolicina=((a_pal.kolicina if a_pal else None) or (a_id.kolicina if a_id else None)),
        jedinica=(a_id.jedinica if a_id else None),
        rok_trajanja=(a_id.rok_trajanja if a_id else None),
        datum_ulaza=(a_id.datum if a_id else None),
        lot=((a_pal.lot if a_pal else None) or (a_id.lot if a_id else None)),
        izvor="erp",
    )
    if greska:
        return None, stavka, greska, None

    # Upozorenje: spremljeno na drugu poziciju nego što je algoritam predložio (ali valjanu).
    upozorenje = None
    if rucna and pozicija != predlozeno:
        upozorenje = (f"Paleta spremljena na {pozicija} — to NIJE predložena pozicija "
                      f"({predlozeno}).")

    stavka.qr_raw = (barkod or "").strip()
    stavka.datum_potvrda = datetime.now()
    stavka.pozicija = pozicija
    db.flush()  # sesija je autoflush=False — flush da count vidi ovu potvrdu
    preostalo = db.scalar(
        select(func.count(PrijemStavka.id)).where(
            PrijemStavka.prijem_id == prijem_id, PrijemStavka.datum_potvrda.is_(None)
        )
    )
    if preostalo == 0:
        prijem.status = "zavrsen"
    db.commit()
    return paleta, stavka, None, upozorenje


def vrati_stavku(db: Session, prijem_id: int, stavka_id: int) -> bool:
    """Poništi potvrdu jedne stavke: obriši njenu paletu i otvori je za ponovno skeniranje
    (povratak na prethodnu / ručna korekcija)."""
    s = db.get(PrijemStavka, stavka_id)
    if s is None or s.prijem_id != prijem_id or s.datum_potvrda is None:
        return False
    pal = db.scalar(select(Paleta).where(
        Paleta.datum_out.is_(None), Paleta.pozicija == s.pozicija, Paleta.qr_raw == s.qr_raw
    ))
    if pal is not None:
        db.delete(pal)
    s.qr_raw = None
    s.datum_potvrda = None
    prijem = db.get(Prijem, prijem_id)
    if prijem is not None and prijem.status == "zavrsen":
        prijem.status = "aktivan"
    db.add(SkladisteEvent(tip="plan_zaprimanja", poruka=f"Plan #{prijem_id}: vraćena stavka {s.pozicija}"))
    db.commit()
    return True


def odustani_plan(db: Session, prijem_id: int, izbrisi_palete: bool = False) -> bool:
    prijem = db.get(Prijem, prijem_id)
    if prijem is None or prijem.status == "odustao":
        return False
    obrisano = 0
    if izbrisi_palete:
        # obriši palete koje je OVAJ plan stvorio (po potvrđenim stavkama: pozicija + qr_raw)
        potvrdjene = db.scalars(
            select(PrijemStavka).where(
                PrijemStavka.prijem_id == prijem_id, PrijemStavka.datum_potvrda.is_not(None)
            )
        ).all()
        for s in potvrdjene:
            pal = db.scalar(select(Paleta).where(
                Paleta.datum_out.is_(None), Paleta.pozicija == s.pozicija, Paleta.qr_raw == s.qr_raw
            ))
            if pal is not None:
                db.delete(pal)
                obrisano += 1
    prijem.status = "odustao"
    poruka = f"izbrisano {obrisano} paleta" if izbrisi_palete else "palete zadržane"
    db.add(SkladisteEvent(tip="plan_zaprimanja", poruka=f"Plan #{prijem_id} otkazan ({poruka})"))
    db.commit()
    return True


# ─── Izdavanje (FIFO/FEFO) ────────────────────────────────────────────────────

def aktivne_za_sifru(db: Session, sifra: str, metoda: str = "fifo") -> list[Paleta]:
    stmt = select(Paleta).where(Paleta.datum_out.is_(None), Paleta.sifra == sifra)
    if metoda == "fefo":
        stmt = stmt.order_by(Paleta.rok_trajanja.is_(None), Paleta.rok_trajanja, Paleta.datum_in)
    else:  # fifo
        stmt = stmt.order_by(Paleta.datum_ulaza.is_(None), Paleta.datum_ulaza, Paleta.datum_in)
    return list(db.scalars(stmt).all())


def aktivne_za_barkod(db: Session, barkod: str) -> list[Paleta]:
    """Aktivne palete s tim barkodom, FIFO redom (najstarija prva)."""
    stmt = (
        select(Paleta)
        .where(Paleta.datum_out.is_(None), Paleta.qr_raw == (barkod or "").strip())
        .order_by(Paleta.datum_ulaza.is_(None), Paleta.datum_ulaza, Paleta.datum_in)
    )
    return list(db.scalars(stmt).all())


def predlozi_izdavanje(db: Session, sifra: str, araka: float, metoda: str = "fifo") -> dict:
    """Po količini araka: FIFO/FEFO odaberi CIJELE palete dok zbroj ne pokrije `araka`.
    Zadnja paleta može premašiti — `zadnja_ostatak` = koliko araka ostaje (vraća se kao
    nova paleta). Vrati i `dovoljno` (ima li dovoljno na stanju)."""
    palete = aktivne_za_sifru(db, sifra, metoda)
    odabrane = []
    kumulativ = 0.0
    for p in palete:
        kol = float(p.kolicina or 0)
        prije = kumulativ
        odabrane.append({
            "paleta": p, "kolicina": kol,
            "doprinos": min(kol, max(0.0, araka - prije)),
        })
        kumulativ += kol
        if kumulativ >= araka:
            break
    dovoljno = kumulativ >= araka
    return {
        "sifra": sifra, "metoda": metoda, "trazeno": araka,
        "palete": odabrane, "ukupno": kumulativ, "dovoljno": dovoljno,
        "zadnja_ostatak": (kumulativ - araka) if (dovoljno and odabrane) else 0.0,
        "na_stanju": len(palete),
    }


def izvrsi_izdavanje(db: Session, paleta_ids: list[int]) -> int:
    """Izdaj (soft-delete) navedene palete. Vrati broj izdanih."""
    n = 0
    for pid in paleta_ids:
        p = db.get(Paleta, pid)
        if p is not None and p.datum_out is None:
            p.datum_out = datetime.now()
            n += 1
            db.add(SkladisteEvent(tip="izdavanje",
                                  poruka=f"Izdana paleta s {p.pozicija} (po količini)",
                                  detalji=f"sifra={p.sifra} kol={p.kolicina}"))
    db.commit()
    return n


def izdaj_paletu(db: Session, paleta_id: int) -> tuple[Paleta | None, str | None]:
    """Izdaj paletu (soft-delete: datum_out). Vrati (paleta, upozorenje|None) ili (None, greska)."""
    p = db.get(Paleta, paleta_id)
    if p is None or p.datum_out is not None:
        return None, "Paleta nije pronađena ili je već izdana."

    upozorenje = None
    if p.sifra:
        fifo = aktivne_za_sifru(db, p.sifra, "fifo")
        if fifo and fifo[0].id != p.id:
            s = fifo[0]
            upozorenje = f"FIFO: postoji starija paleta iste šifre na {s.pozicija}."

    p.datum_out = datetime.now()
    db.add(SkladisteEvent(tip="izdavanje", poruka=f"Izdana paleta s {p.pozicija}",
                          detalji=f"barkod={p.qr_raw} sifra={p.sifra}"))
    db.commit()
    return p, upozorenje


# ─── Inventura ────────────────────────────────────────────────────────────────

def aktivna_inventura(db: Session) -> Inventura | None:
    return db.scalar(select(Inventura).where(Inventura.status == "aktivan"))


def pokreni_inventuru(db: Session) -> Inventura:
    inv = aktivna_inventura(db)
    if inv:
        return inv
    inv = Inventura(status="aktivan")
    db.add(inv)
    db.add(SkladisteEvent(tip="inventura", poruka="Pokrenuta inventura"))
    db.commit()
    db.refresh(inv)
    return inv


def skeniraj_inventuru(db: Session, barkod: str, pozicija: str | None = None) -> tuple[int, str | None]:
    """Zabilježi skeniranu paletu u aktivnu inventuru. Vrati (broj_skeniranih, greska|None)."""
    inv = aktivna_inventura(db)
    if inv is None:
        return 0, "Nema aktivne inventure."
    db.add(InventuraStavka(inventura_id=inv.id, qr_raw=(barkod or "").strip(),
                           pozicija_skenirana=(pozicija or None)))
    db.commit()
    broj = db.scalar(
        select(func.count(InventuraStavka.id)).where(InventuraStavka.inventura_id == inv.id)
    ) or 0
    return broj, None


def zatvori_inventuru(db: Session) -> dict | None:
    """Zatvori aktivnu inventuru i izračunaj razlike. Vrati izvještaj ili None."""
    inv = aktivna_inventura(db)
    if inv is None:
        return None

    skenirani = set(db.scalars(
        select(InventuraStavka.qr_raw).where(InventuraStavka.inventura_id == inv.id)
    ).all())
    aktivne = list(db.scalars(select(Paleta).where(Paleta.datum_out.is_(None))).all())
    aktivni_barkodovi = {p.qr_raw for p in aktivne}

    nedostaju = [p for p in aktivne if p.qr_raw not in skenirani]       # u bazi, nije skenirano
    neocekivane = [b for b in skenirani if b not in aktivni_barkodovi]  # skenirano, nije u bazi

    inv.status = "zavrsen"
    inv.datum_kraja = datetime.now()
    db.add(SkladisteEvent(
        tip="inventura",
        poruka=f"Zatvorena inventura: {len(nedostaju)} nedostaje, {len(neocekivane)} neočekivano",
    ))
    db.commit()
    return {
        "inventura": inv,
        "skenirano": len(skenirani),
        "nedostaju": nedostaju,
        "neocekivane": neocekivane,
    }


def ponisti_inventuru(db: Session) -> bool:
    inv = aktivna_inventura(db)
    if inv is None:
        return False
    inv.status = "ponistena"
    inv.datum_kraja = datetime.now()
    db.add(SkladisteEvent(tip="inventura", poruka="Poništena inventura"))
    db.commit()
    return True


# ─── Karta skladišta ──────────────────────────────────────────────────────────

_WORST = {0: "slobodno", 1: "zauzeto", 2: "istice", 3: "isteklo"}


def _pozicije_regala(rack, po_poz, np_slot, danas, granica) -> list[dict]:
    """Za jedan regal: po poziciji (tlocrt) agregiraj sve visine u jedan status."""
    out = []
    for p in range(1, rack.broj_pozicija + 1):
        occ = 0
        worst = 0
        nepotpuna = False
        for v in range(1, rack.broj_visina + 1):
            kod = f"{rack.naziv}P{p}V{v}"
            pal = po_poz.get(kod)
            if pal is not None:
                occ += 1
                if kod in np_slot:
                    nepotpuna = True
                s = 1
                if pal.rok_trajanja:
                    if pal.rok_trajanja < danas:
                        s = 3
                    elif pal.rok_trajanja <= granica:
                        s = 2
                worst = max(worst, s)
        out.append({
            "pozicija": p, "kod": f"{rack.naziv}P{p}",
            "occ": occ, "total": rack.broj_visina, "status": _WORST[worst],
            "nepotpuna": nepotpuna,
        })
    return out


def mapa_tlocrt(db: Session) -> dict:
    """Podaci za tlocrt skladišta: Zapad (C1) lijevo okomito, Istok (D1) desno,
    Sredina A (A1–A13) i Sredina B (B1–B5) vodoravno u sredini. Po poziciji se
    agregiraju visine (occ/total + najgori status). Ulaz = gore lijevo."""
    from datetime import timedelta
    danas = date.today()
    granica = danas + timedelta(days=30)
    po_poz = {}
    np_slot: set[str] = set()
    for p in db.scalars(select(Paleta).where(Paleta.datum_out.is_(None))).all():
        po_poz[p.pozicija] = p              # za status (zadnja na slotu)
        if p.nepotpuna:
            np_slot.add(p.pozicija)         # bilo koja nepotpuna na slotu

    # P1 je UVIJEK na istoj strani (bliže ulazu / lijevo) — bez zrcaljenja.
    def red(rack):
        return {"naziv": rack.naziv,
                "pozicije": _pozicije_regala(rack, po_poz, np_slot, danas, granica)}

    return {
        "zapad": red(cfg.REGALI_PO_NAZIVU["C1"]),
        "istok": red(cfg.REGALI_PO_NAZIVU["D1"]),
        "sredina_a": [red(r) for r in cfg.regali_zone("A")],
        "sredina_b": [red(r) for r in cfg.regali_zone("B")],
    }


def mapa_zone(db: Session, zona: str) -> list[dict]:
    """Podaci za kartu jedne zone: po regalu, redovi visina (Vn gore → V1 dolje),
    svaka ćelija = pozicija + status (slobodno/zauzeto/istice/isteklo) + paleta."""
    from datetime import timedelta

    danas = date.today()
    granica = danas + timedelta(days=30)
    palete = db.scalars(
        select(Paleta).where(Paleta.datum_out.is_(None), Paleta.pozicija.like(f"{zona}%"))
    ).all()
    po_poz = {p.pozicija: p for p in palete}
    np_slot = {p.pozicija for p in palete if p.nepotpuna}

    regali = []
    for r in cfg.regali_zone(zona):
        redovi = []
        for v in range(r.broj_visina, 0, -1):  # od najviše prema V1
            celije = []
            for p in range(1, r.broj_pozicija + 1):
                kod = f"{r.naziv}P{p}V{v}"
                pal = po_poz.get(kod)
                status = "slobodno"
                if pal is not None:
                    status = "zauzeto"
                    if pal.rok_trajanja:
                        if pal.rok_trajanja < danas:
                            status = "isteklo"
                        elif pal.rok_trajanja <= granica:
                            status = "istice"
                celije.append({"kod": kod, "pozicija": p, "paleta": pal, "status": status,
                               "nepotpuna": kod in np_slot})
            redovi.append({"visina": v, "celije": celije})
        zauzeto = sum(1 for kod in po_poz if cfg.parse_pozicija(kod) and cfg.parse_pozicija(kod).regal == r.naziv)
        regali.append({
            "naziv": r.naziv, "redovi": redovi,
            "broj_pozicija": r.broj_pozicija, "zauzeto": zauzeto, "kapacitet": r.kapacitet,
        })
    return regali
