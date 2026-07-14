"""CI smoke testovi — boot, prijava, ključne stranice, zaprimi/izdaj tok, PDF."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.modules.skladiste import config as cfg


def _client():
    c = TestClient(app)
    r = c.post("/login", data={"username": "admin", "lozinka": "admin"},
               follow_redirects=False)
    assert r.status_code == 303, "prijava admin/admin nije uspjela"
    return c


def test_bez_prijave_redirect_na_login():
    c = TestClient(app)
    r = c.get("/skladiste", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_kljucne_stranice():
    c = _client()
    for u in ["/skladiste", "/skladiste/mapa", "/skladiste/palete",
              "/lokacija/zaprimi", "/lokacija/izdaj", "/zahtjevnica"]:
        assert c.get(u).status_code == 200, u


def test_zaprimi_pa_izdaj():
    c = _client()
    poz = cfg.sve_pozicije()[0]
    r = c.post("/lokacija/postavi", data={"barkod": "CI-TEST-1", "pozicija": poz})
    assert r.status_code == 200 and "CI-TEST-1" in r.text
    r = c.get("/lokacija/izdaj/skeniraj", params={"barkod": "CI-TEST-1"})
    assert "CI-TEST-1" in r.text


def test_pdf_stanja():
    c = _client()
    r = c.get("/skladiste/stanje/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
