"""Autentikacija i autorizacija — čiste funkcije (bez DB/route ovisnosti).

- Lozinke: bcrypt (nikad plain/SHA).
- Dozvole: granularne, po korisniku (CSV ključeva u `User.dozvole`). `admin` = sve.
- `required_perm(path)` mapira URL na potrebnu dozvolu (koristi middleware).
- `akcija_label(method, path)` daje čitljiv naziv akcije za audit log.
"""
from __future__ import annotations

import re

# ── Katalog dozvola (ključ -> opis za UI) ───────────────────────────────────────
PERMISSIONS: dict[str, str] = {
    "zaprimanje": "Zaprimanje paleta",
    "izdavanje":  "Izdavanje paleta",
    "inventura":  "Inventura",
    "prioriteti": "Uređivanje prioriteta (pravila smještaja)",
    "admin":      "Administracija (korisnici + log)",
}

# Pregled (nadzorna ploča, karta, sve palete, lookup, PDF stanja) — ima svaki
# prijavljeni korisnik; ne treba zasebnu dozvolu.

# URL prefiks -> potrebna dozvola. Sve ostalo pod /skladiste = samo prijava (pregled).
_PERM_MAP: list[tuple[str, str]] = [
    ("/lokacija/zaprimi",     "zaprimanje"),
    ("/lokacija/postavi",     "zaprimanje"),
    ("/lokacija/izdaj",       "izdavanje"),
    ("/zahtjevnica",          "izdavanje"),
    ("/skladiste/zaprimanje", "zaprimanje"),
    ("/skladiste/izdaj",      "izdavanje"),
    ("/skladiste/inventura",  "inventura"),
    ("/skladiste/prioriteti", "prioriteti"),
    ("/admin",                "admin"),
]

# RADNO — mehanizam zaključavanja (zadržan za buduće nedovršene funkcije).
# Finalna verzija: sve skladišne funkcije su AKTIVNE (prazan popis). Pristup se i dalje
# kontrolira granularnim dozvolama (_PERM_MAP niže), pa nezaključano ≠ svima dostupno.
LOCKED_PREFIXES: tuple[str, ...] = ()


def is_locked(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path == p for p in LOCKED_PREFIXES)

# Putanje dostupne BEZ prijave.
PUBLIC_PATHS = {"/login", "/logout", "/api-docs", "/openapi.json", "/favicon.ico"}

# POST-ovi koji ništa ne mijenjaju (samo prikažu prijedlog) — ne idu u audit.
_AUDIT_SKIP = {"/skladiste/izdaj/predlozi"}

# Rute koje SAME pišu detaljan audit (s QR-om i pozicijom) — middleware ih preskače
# da ne bude dvostrukog zapisa.
_SELF_AUDIT_PREFIXES = ("/lokacija/postavi", "/lokacija/izdaj/")


def perms_set(dozvole: str | None) -> set[str]:
    return {p for p in (dozvole or "").split(",") if p}


def has_perm(dozvole: str | None, perm: str) -> bool:
    p = perms_set(dozvole)
    return "admin" in p or perm in p


def required_perm(path: str) -> str | None:
    """Koja je dozvola potrebna za danu putanju (ili None = dovoljna prijava)."""
    for prefix, perm in _PERM_MAP:
        if path == prefix or path.startswith(prefix + "/"):
            return perm
    return None


def should_audit(method: str, path: str, status: int) -> bool:
    if path in _AUDIT_SKIP or path.startswith(_SELF_AUDIT_PREFIXES):
        return False
    return method in ("POST", "PUT", "DELETE", "PATCH") and status < 400


# ── Lozinke (bcrypt) ────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    import bcrypt
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── Audit oznake ────────────────────────────────────────────────────────────────

_AKCIJE: list[tuple[str, str]] = [
    (r"^/login$",                                          "Prijava"),
    (r"^/logout$",                                         "Odjava"),
    (r"^/lokacija/postavi$",                               "Postavljanje palete na poziciju"),
    (r"^/lokacija/izdaj/\d+$",                             "Izdavanje palete"),
    (r"^/skladiste/zaprimanje/plan$",                      "Kreiran plan zaprimanja"),
    (r"^/skladiste/zaprimanje/plan/\d+/potvrdi$",          "Potvrda palete u planu"),
    (r"^/skladiste/zaprimanje/plan/\d+/stavka/\d+/vrati$", "Vraćanje palete (korekcija)"),
    (r"^/skladiste/zaprimanje/plan/\d+/odustani$",         "Odustajanje od plana"),
    (r"^/skladiste/izdaj/izvrsi$",                         "Izdavanje paleta"),
    (r"^/skladiste/inventura/start$",                      "Pokretanje inventure"),
    (r"^/skladiste/inventura/skeniraj$",                   "Inventura: skeniranje"),
    (r"^/skladiste/inventura/zatvori$",                    "Zatvaranje inventure"),
    (r"^/skladiste/inventura/ponisti$",                    "Poništavanje inventure"),
    (r"^/skladiste/prioriteti$",                           "Spremanje prioriteta"),
    (r"^/skladiste/prioriteti/\d+/toggle$",                "Prioritet: uklj/isklj"),
    (r"^/skladiste/prioriteti/\d+/obrisi$",                "Brisanje prioriteta"),
    (r"^/admin/korisnici$",                                "Kreiranje korisnika"),
    (r"^/admin/korisnici/\d+/uredi$",                      "Uređivanje korisnika"),
    (r"^/admin/korisnici/\d+/lozinka$",                    "Promjena lozinke"),
    (r"^/admin/korisnici/\d+/obrisi$",                     "Brisanje korisnika"),
]


def akcija_label(method: str, path: str) -> str:
    for pat, lbl in _AKCIJE:
        if re.match(pat, path):
            return lbl
    return f"{method} {path}"
