"""Skladište — fiksni raspored regala + validacija pozicija.

Regali se NE mijenjaju kroz aplikaciju (poslovna odluka): ovaj modul je jedini
izvor istine. Ako se fizički raspored ikad promijeni, mijenja se OVDJE u kodu.

Format pozicije (nepadano, točno kao na QR-u): <ZONA><REGAL#>P<POZICIJA>V<VISINA>
  npr. A13P15V5 = zona A, regal 13, pozicija 15, visina 5

Brojevi su promjenjive širine (P1 i P15), pa se pozicije UVIJEK sortiraju po
parsiranim brojevima (`Pozicija.sort_key`), nikad po sirovom stringu.
"""
import re
from dataclasses import dataclass

# (naziv, zona, broj_pozicija, broj_visina) — iz tlocrta + tablice stanja (Žitnjak):
#   Ulaz = DOLJE DESNO. Zona A = "Sredina A" (R1): A1 = 9 poz (kraći red, ODMAH do ulaza),
#     A2–A13 po 15 poz, visina 5 → 945. P1 svake pozicije je bliže ulazu (desno).
#   Zona B = "Sredina B" (R2): 5 redova × 15 poz × 4 → 300
#   Zona C = "Zapad" (R3): 1 dugi regal × 30 poz × 4 → 120
#   Zona D = "Istok" (R3): 1 dugi regal × 27 poz × 4 → 108     (ukupno 1473)
_DEF = (
    [("A1", "A", 9, 5)]                              # A1 (9 poz, kraći, do ulaza)
    + [(f"A{i}", "A", 15, 5) for i in range(2, 14)]  # A2..A13 (15 poz)
    + [(f"B{i}", "B", 15, 4) for i in range(1, 6)]    # B1..B5
    + [("C1", "C", 30, 4)]                            # Zapad
    + [("D1", "D", 27, 4)]                            # Istok
)


@dataclass(frozen=True)
class Regal:
    naziv: str
    zona: str
    broj_pozicija: int
    broj_visina: int

    @property
    def kapacitet(self) -> int:
        return self.broj_pozicija * self.broj_visina


REGALI: tuple[Regal, ...] = tuple(Regal(*r) for r in _DEF)
REGALI_PO_NAZIVU: dict[str, Regal] = {r.naziv: r for r in REGALI}
ZONE: tuple[str, ...] = ("A", "B", "C", "D")
UKUPNO_MJESTA: int = sum(r.kapacitet for r in REGALI)  # 1503


def regali_zone(zona: str) -> list[Regal]:
    return [r for r in REGALI if r.zona == zona]


def kapacitet_zone(zona: str) -> int:
    return sum(r.kapacitet for r in regali_zone(zona))


# ─── Validacija / parsiranje pozicije ─────────────────────────────────────────

_POZ_RE = re.compile(r"^([A-D])(\d{1,2})P(\d{1,2})V(\d)$")


@dataclass(frozen=True)
class Pozicija:
    regal: str          # npr. "A13"
    zona: str           # "A".."D"
    regal_broj: int
    pozicija: int
    visina: int

    @property
    def kod(self) -> str:
        return f"{self.regal}P{self.pozicija}V{self.visina}"

    @property
    def sort_key(self) -> tuple[str, int, int, int]:
        return (self.zona, self.regal_broj, self.pozicija, self.visina)


def parse_pozicija(kod: str | None) -> Pozicija | None:
    """Parsiraj i VALIDIRAJ kod pozicije. Vrati `Pozicija` ili `None` ako nije valjan
    (ne postoji takav regal, ili pozicija/visina izvan granica regala)."""
    if not kod:
        return None
    m = _POZ_RE.match(kod.strip().upper())
    if not m:
        return None
    zona, regal_broj, pozicija, visina = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    naziv = f"{zona}{regal_broj}"
    regal = REGALI_PO_NAZIVU.get(naziv)
    if regal is None:
        return None
    if not (1 <= pozicija <= regal.broj_pozicija):
        return None
    if not (1 <= visina <= regal.broj_visina):
        return None
    return Pozicija(regal=naziv, zona=zona, regal_broj=regal_broj, pozicija=pozicija, visina=visina)


def je_validna_pozicija(kod: str | None) -> bool:
    return parse_pozicija(kod) is not None


def sve_pozicije() -> list[str]:
    """Svi kodovi pozicija u redoslijedu punjenja: po zonama/regalima (A1..D1), niže
    visine prvo (V1 → Vn), pa pozicije (P1 → Pn). Niže visine prve = bolji FIFO dohvat."""
    out: list[str] = []
    for r in REGALI:
        for v in range(1, r.broj_visina + 1):
            for p in range(1, r.broj_pozicija + 1):
                out.append(f"{r.naziv}P{p}V{v}")
    return out
