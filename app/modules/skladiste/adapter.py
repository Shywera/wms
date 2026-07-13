"""ERP adapter — dohvat artikla po barkodu.

Jezgra skladišta zove SAMO `get_adapter().lookup_barcode(barkod)`. Implementacije:
- `MockAdapter`: lokalni lažni ERP za razvoj/testove (ZADANI).
- `LegacyErpAdapter`: REST + HTTP Basic na legacy ERP (uključi se preko `.env`).

Prebacivanje preko env varijable:
    ERP_ADAPTER = mock | erp           (zadano: mock)
    ERP_API_URL  = https://erp.interno
    ERP_API_USER = ...
    ERP_API_PASS = ...

Ugovor s legacy ERP-om: GET {base}/api/skladiste/artikl?barkod=...  (Basic auth)
  -> { sifra, naziv, jedinica, kolicina (broj), rok_trajanja (ISO), lot, datum (ISO) }
Datumi MORAJU biti ISO i kolicina broj — to drži FIFO ispravnim (legacy bug B7).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from dataclasses import asdict, dataclass
from datetime import date, timedelta


@dataclass
class ArtiklInfo:
    sifra: str
    naziv: str | None = None
    jedinica: str | None = None
    kolicina: float | None = None       # araka po paleti
    rok_trajanja: date | None = None    # ISO
    lot: str | None = None
    datum: date | None = None           # datum ulaza / proizvodnje
    gramatura: int | None = None
    duljina: int | None = None          # mm
    sirina: int | None = None           # mm

    @property
    def format(self) -> str:
        if self.duljina and self.sirina:
            g = f" g{self.gramatura}" if self.gramatura else ""
            return f"{self.duljina}×{self.sirina}{g}"
        return ""

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("rok_trajanja", "datum"):
            if isinstance(d[k], date):
                d[k] = d[k].isoformat()
        return d


class ErpAdapter:
    def lookup_barcode(self, barkod: str) -> ArtiklInfo | None:
        raise NotImplementedError


_PAPIRI = json.loads(
    (pathlib.Path(__file__).parent / "_mock_papiri.json").read_text(encoding="utf-8")
)
_PAPIRI_PO_SIFRI = {p["sifra"]: p for p in _PAPIRI}


class MockAdapter(ErpAdapter):
    """Determinističan lažni ERP koji koristi DEMO papire iz tablice
    (`_mock_papiri.json`, 165 papira). Isti barkod uvijek vraća isti papir; ako je
    barkod jednak nekoj šifri iz tablice, vraća točno taj papir. Količina araka po
    paleti, lot i rok generiraju se determinističko po barkodu."""

    def lookup_barcode(self, barkod: str) -> ArtiklInfo | None:
        barkod = (barkod or "").strip()
        if len(barkod) < 3 or not _PAPIRI:
            return None
        h = int(hashlib.sha1(barkod.encode()).hexdigest(), 16)
        pap = _PAPIRI_PO_SIFRI.get(barkod) or _PAPIRI[h % len(_PAPIRI)]
        return ArtiklInfo(
            sifra=pap["sifra"],
            naziv=pap.get("naziv"),
            jedinica=pap.get("jedinica", "arak"),
            kolicina=float(1000 + h % 9000),                       # araka po paleti
            rok_trajanja=date.today() + timedelta(days=180 + h % 700),
            lot=f"L{date.today().year}-{1000 + h % 9000}",
            datum=date.today(),
            gramatura=pap.get("gramatura"),
            duljina=pap.get("duljina"),
            sirina=pap.get("sirina"),
        )


class LegacyErpAdapter(ErpAdapter):
    """REST + HTTP Basic na legacy ERP. `httpx` se uvozi lijeno (nije nužan dok se
    LegacyErpAdapter stvarno ne koristi). `verify=False` jer je ERP interni https na LAN-u."""

    def __init__(self, base_url: str, user: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (user, password)

    def lookup_barcode(self, barkod: str) -> ArtiklInfo | None:
        import httpx

        def _d(v):
            return date.fromisoformat(v) if v else None

        try:
            r = httpx.get(
                f"{self.base_url}/api/skladiste/artikl",
                params={"barkod": barkod}, auth=self.auth, timeout=5.0, verify=False,
            )
        except Exception:
            return None
        if r.status_code != 200:
            return None
        def _i(v):
            try:
                return int(v) if v is not None and str(v) != "" else None
            except Exception:
                return None

        d = r.json()
        return ArtiklInfo(
            sifra=str(d.get("sifra") or ""),
            naziv=d.get("naziv"),
            jedinica=d.get("jedinica"),
            kolicina=float(d["kolicina"]) if d.get("kolicina") is not None else None,
            rok_trajanja=_d(d.get("rok_trajanja")),
            lot=d.get("lot"),
            datum=_d(d.get("datum")),
            gramatura=_i(d.get("gramatura")),
            duljina=_i(d.get("duljina")),
            sirina=_i(d.get("sirina")),
        )


_adapter: ErpAdapter | None = None


def get_adapter() -> ErpAdapter:
    """Vrati aktivni adapter (singleton). Bira se preko ERP_ADAPTER env var (zadano mock)."""
    global _adapter
    if _adapter is None:
        kind = os.getenv("ERP_ADAPTER", "mock").lower()
        if kind in ("erp", "pauk"):  # "pauk" = stari alias
            _adapter = LegacyErpAdapter(
                os.getenv("ERP_API_URL", "https://erp.interno"),
                os.getenv("ERP_API_USER", ""),
                os.getenv("ERP_API_PASS", ""),
            )
        else:
            _adapter = MockAdapter()
    return _adapter
