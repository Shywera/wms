# WMS — Sustav upravljanja skladištem

[![CI](https://github.com/Shywera/wms/actions/workflows/ci.yml/badge.svg)](https://github.com/Shywera/wms/actions/workflows/ci.yml)

Web aplikacija za upravljanje paletnim skladištem u tiskarskoj proizvodnji.
Dizajnirana za rad sa **ručnim barkod skenerima** (Zebra i sl.) — velika polja,
potvrda Enterom, minimalan broj koraka po operaciji.

## Mogućnosti

- **Zaprimanje paleta** — skeniraj paletu → odaberi mjesto na karti ili skeniraj QR pozicije
- **Izdavanje paleta** — pojedinačno skenerom ili **po zahtjevnici**: uvoz Excel/CSV/PDF
  zahtjevnice, automatski prijedlog paleta (FIFO), potvrda skeniranjem
- **Karta skladišta** — tlocrt sa zauzećem po zonama, regalima i visinama
- **Multi-paletni plan zaprimanja**, izdavanje po količini (FIFO/FEFO), inventura, pravila smještaja
- **Prijava i granularne dozvole** po korisniku (zaprimanje / izdavanje / inventura / admin)
- **Audit log** — tko je, kada i što napravio
- **PDF izvještaji** — stanje skladišta (tlocrt) i liste za zaprimanje
- **Automatski backup** baze pri svakom pokretanju

## Tehnologije

FastAPI · SQLAlchemy 2.0 · SQLite · Jinja2 · HTMX · Alpine.js · Tailwind CSS · reportlab

## Brzi start (Windows)

1. Instalirajte [Python 3](https://python.org) (uključite *Add Python to PATH*)
2. Pokrenite **`run.bat`** — prvi put izgradi okruženje i generira `.env`
3. Otvorite **http://localhost:8600** — prijava `admin` / `admin` (odmah promijenite lozinku)

Za rad na lokalnoj mreži (skeneri, tableti): **`dev-wifi.bat`** ispiše mrežnu adresu.
Za trajni rad na serveru kao Windows servis: vidi **[SERVER.md](SERVER.md)**.

## Konfiguracija (`.env`)

| Varijabla | Opis |
|---|---|
| `ADMIN_PASSWORD` | lozinka početnog administratora (vrijedi dok je baza prazna) |
| `SECRET_KEY` | potpis session cookieja (auto-generiran) |
| `ERP_ADAPTER` | `mock` (demo podaci, zadano) ili `erp` (REST veza na legacy ERP, read-only) |
| `DATABASE_URL` | zadano SQLite; podržan i PostgreSQL |

## Napomena

Repozitorij koristi **demo šifrarnik materijala** — u produkciji se podaci o artiklima
dohvaćaju iz ERP-a preko adaptera (isključivo za čitanje). Baza i tajne (`.env`) nisu
dio repozitorija.

## Povezani projekti

[ERP/MES/WMS](https://github.com/Shywera/erp) ·
[Reklamacije/QMS](https://github.com/Shywera/reklamacije) ·
[Ponude](https://github.com/Shywera/Ponude) ·
[Normativi i montaža](https://github.com/Shywera/normativ-montaza) ·
[Alati](https://github.com/Shywera/tools)
