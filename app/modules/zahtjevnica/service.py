"""Poslovna logika zahtjevnice: filtriraj papir, grupiraj po šifri, obogati preko
adaptera, detektiraj dupli uvoz, predloži palete (FIFO) i izdaj.

Oslanja se na `skladiste.service` (predlozi_izdavanje / izvrsi_izdavanje) — ne duplicira
logiku izdavanja i ne dira skladišni modul.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.skladiste import service as svc
from app.modules.skladiste.adapter import get_adapter
from app.modules.zahtjevnica.models import Zahtjevnica, ZahtjevnicaStavka

PAPIR_PREFIKS = "50101050"          # papirna klasa šifri
PAPIR_JEDINICA = "arak"


def je_papir(sifra: str | None, jedinica: str | None) -> bool:
    """Papir (za OVO skladište) = jedinica 'arak' ILI šifra iz papirne klase.
    Boje/lakovi/puder su 'kg' i nisu za ovo skladište."""
    if (jedinica or "").strip().lower() == PAPIR_JEDINICA:
        return True
    return bool(sifra) and str(sifra).startswith(PAPIR_PREFIKS)


def grupiraj(redci: list[dict]) -> list[dict]:
    """Grupiraj po šifri: zbroji tražene količine, spoji RN-ove. Jedan redak po papiru."""
    grupe: dict[str, dict] = {}
    for r in redci:
        sifra = r["sifra"]
        g = grupe.get(sifra)
        if g is None:
            g = grupe[sifra] = {
                "sifra": sifra, "naziv": r.get("naziv"),
                "jedinica": r.get("jedinica"), "kolicina": 0.0, "rn": set(),
            }
        g["kolicina"] += float(r.get("kolicina") or 0)
        if not g["naziv"] and r.get("naziv"):
            g["naziv"] = r["naziv"]
        if r.get("rn"):
            g["rn"].add(r["rn"])
    # papir prvo, pa po nazivu
    out = list(grupe.values())
    out.sort(key=lambda g: (not je_papir(g["sifra"], g["jedinica"]), (g["naziv"] or "").lower()))
    return out


def _hash(grupe: list[dict]) -> str:
    osnova = ";".join(f"{g['sifra']}:{round(float(g['kolicina']), 3)}"
                      for g in sorted(grupe, key=lambda g: g["sifra"]))
    return hashlib.sha1(osnova.encode("utf-8")).hexdigest()


def provjeri_duplikat(db: Session, h: str) -> Zahtjevnica | None:
    return db.scalar(
        select(Zahtjevnica).where(Zahtjevnica.sadrzaj_hash == h)
        .order_by(Zahtjevnica.id.desc())
    )


def kreiraj(db: Session, filename: str, redci: list[dict]) -> tuple[Zahtjevnica, Zahtjevnica | None]:
    """Napravi zahtjevnicu iz parsiranih redaka. Vrati (zahtjevnica, duplikat|None).
    Duplikat = ranije uvezena zahtjevnica istog sadržaja (poziva se prije spremanja radi
    upozorenja; spremanje se svejedno provede jer korisnik može svjesno ponoviti)."""
    grupe = grupiraj(redci)
    h = _hash(grupe)
    dup = provjeri_duplikat(db, h)

    rn_svi = sorted({rn for g in grupe for rn in g["rn"]})
    oznaka = ("RN " + ", ".join(rn_svi)) if rn_svi else (filename or "Zahtjevnica")
    z = Zahtjevnica(oznaka=oznaka[:250], rn_popis=", ".join(rn_svi)[:300] or None,
                    izvor_naziv=(filename or None), sadrzaj_hash=h, status="uvezena")
    db.add(z)
    db.flush()

    adapter = get_adapter()
    for g in grupe:
        papir = je_papir(g["sifra"], g["jedinica"])
        naziv = g["naziv"]
        jed = g["jedinica"]
        if papir:        # za papir uzmi ČIST naziv/jedinicu iz adaptera (parsani zna biti zbrkan)
            try:
                info = adapter.lookup_barcode(g["sifra"])
            except Exception:
                info = None
            if info:
                naziv = info.naziv or naziv
                jed = info.jedinica or jed
        db.add(ZahtjevnicaStavka(
            zahtjevnica_id=z.id, sifra=g["sifra"], naziv=naziv,
            jedinica=jed, trazena_kolicina=round(float(g["kolicina"]), 3),
            rn_popis=", ".join(sorted(g["rn"]))[:300] or None, je_papir=papir,
        ))
    db.commit()
    db.refresh(z)
    return z, dup


# ── Izdavanje ────────────────────────────────────────────────────────────────

def predlozi(db: Session, stavka: ZahtjevnicaStavka) -> dict:
    """Predloži palete (FIFO, cijele palete do tražene količine) za ovu stavku."""
    return svc.predlozi_izdavanje(db, stavka.sifra, float(stavka.trazena_kolicina or 0), "fifo")


def izdaj_stavku(db: Session, stavka: ZahtjevnicaStavka,
                 paleta_ids: list[int]) -> tuple[int, str | None]:
    """Izdaj odabrane palete za stavku. Vrati (broj_izdanih, greska|None).
    Provjere: stavka nije već izdana; palete pripadaju toj šifri i još su aktivne."""
    if stavka.izdano:
        return 0, "Ova stavka je već izdana."
    if not paleta_ids:
        return 0, "Nije odabrana nijedna paleta."
    # provjeri da su sve palete te šifre i aktivne (spriječi krivu/dvostruku)
    aktivne = {p.id: p for p in svc.aktivne_za_sifru(db, stavka.sifra, "fifo")}
    for pid in paleta_ids:
        p = aktivne.get(pid)
        if p is None:
            return 0, f"Paleta #{pid} nije aktivna ili nije te šifre — osvježi prijedlog."
    n = svc.izvrsi_izdavanje(db, paleta_ids)
    izdano_kol = sum(float(aktivne[pid].kolicina or 0) for pid in paleta_ids if pid in aktivne)
    stavka.izdano = True
    stavka.izdano_kolicina = round(izdano_kol, 3)
    stavka.izdano_paleta_ids = ",".join(str(p) for p in paleta_ids)
    z = stavka.zahtjevnica
    if z.status == "uvezena":
        z.status = "u_tijeku"
    if z.gotovo:
        z.status = "zavrsena"
    db.commit()
    return n, None


def ponisti_izdavanje(db: Session, stavka: ZahtjevnicaStavka) -> None:
    """Vrati oznaku 'izdano' (ne vraća palete — to je fizička radnja); samo dopušta ponovni pokušaj."""
    stavka.izdano = False
    stavka.izdano_kolicina = 0.0
    stavka.izdano_paleta_ids = None
    if stavka.zahtjevnica.status == "zavrsena":
        stavka.zahtjevnica.status = "u_tijeku"
    db.commit()
