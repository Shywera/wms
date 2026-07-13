# CLAUDE.md

Kontekst za Claude Code. Ovo je **jedini kontekst koji putuje između računala** (kuća/posao)
kroz git — Claudova lokalna memorija se NE sinkronizira. Na kraju sesije ažuriraj sekciju
"Trenutno stanje" i pokreni `spremi.bat`.

## Što je ovo
Samostalna **WMS** (skladište) web-aplikacija za tiskaru samoljepljivih etiketa —
upravljanje paletama, QR ↔ pozicija. FastAPI + SQLAlchemy 2.0 + SQLite + Jinja2 + HTMX +
Alpine + Tailwind (CDN). Isti skladišni kod kao WMS modul u većem ERP/MES/WMS projektu
(`app/modules/skladiste` je kopiran **1:1** i ne smije divergirati).

## Pokretanje i alati (Windows, .bat)
- `run.bat` — lokalno, port **8600**; prvi put gradi `.venv` + generira `.env`.
- `dev-wifi.bat` — isto ali na `0.0.0.0` + ispiše mrežni URL (za Zebra MC3400 / mobitel).
- `backup.bat` — ručni backup baze. `update.bat` — `git pull` + osvježi deps.
- `spremi.bat` — `git add`+`commit`+`pull`+`push` (sinkronizacija na GitHub).
- Ručni test: `.venv\Scripts\python.exe` + FastAPI `TestClient` (za to je `httpx` instaliran
  lokalno u venv, ali **NIJE** u `requirements.txt`).

## Arhitektura
```
app/main.py            FastAPI: create_all, idempotentne ALTER migracije, _seed_admin,
                       auth_audit middleware (prijava+dozvole+audit), SessionMiddleware, /backup
app/core/              config (pydantic-settings, .env) + database (samostalni SQLite) + backup
app/modules/skladiste/ ISTI kod kao ERP (config/models/adapter/service/routes/pdf) — NE dirati logiku
app/modules/lokacija/  jednostavan QR↔pozicija tok (zaprimi/izdaj jedne palete)
app/modules/auth/      security (dozvole/bcrypt) + models (korisnik/audit_log) + routes (login/admin)
app/templates/         base.html (izbornik gated po dozvolama) + auth/ + skladiste/ + lokacija/
```

## Konvencije i zamke (naučeno)
- **Standalone namespace `app.`** — moduli se kopiraju 1:1 iz ERP-a bez mijenjanja importa.
- **Migracije:** `create_all` + idempotentni `ALTER TABLE` preko `sa_inspect(engine).get_columns()`
  (create_all NE mijenja postojeće tablice). SQLite URL: `sqlite:///./wms.db`.
- **.bat MORA biti CRLF** (Write tool daje LF → cmd se instant zatvori). Konverzija:
  `awk '{sub(/\r$/,""); printf "%s\r\n",$0}'`. Provjera: `od -c`. Zagrade u `echo` unutar
  `if(...)` bloka lome parsiranje → koristi `goto`. `ipconfig ^| findstr` samostalno →
  obični `|`.
- **Python 3.14 (cp314) venv nije prenosiv** → `run.bat` je self-healing (provjeri
  `import fastapi,uvicorn` → ako padne, obriši `.venv` i ponovo gradi). Ne shipati `.venv`.
- **pydantic-settings:** da bi `.env` varijabla proradila, mora postojati polje u `Settings`
  (npr. `admin_password`, `secret_key`).
- **Dozvole:** `zaprimanje/izdavanje/inventura/prioriteti/admin` (admin=sve); pregled ima svaki
  prijavljeni. Finalna verzija: `LOCKED_PREFIXES` je PRAZAN (sve aktivno, gated po dozvoli);
  mehanizam zaključavanja zadržan za buduće.
- **Portovi:** ERP=8000, **WMS-app=8600**, Reklamacije-app=8601.
- **NIKAD ne commitati:** `.env`, `*.db`, `.venv`, `__pycache__` (u `.gitignore`).

## VAŽNO — legacy ERP (READ-ONLY)
`ERP_ADAPTER=erp` spaja se na legacy ERP (REST + Basic auth) i **mora ostati
isključivo za čitanje** — nikad ne pisati/mijenjati podatke u ERP-u. Kredencijali
(`ERP_API_URL/USER/PASS`) idu **samo u `.env`**, nikad u kod/repo. Zadano je `mock` adapter.

## Sinkronizacija kuća/posao
Sinkronizira se **samo kod + ovaj CLAUDE.md**. Baza (`wms.db`) i `.env` su lokalni po
računalu — svako ima svoje podatke i admin/admin na praznoj bazi. Tijek: `spremi.bat` na
jednom → `update.bat` na drugom.

## Trenutno stanje (ažuriraj na kraju sesije)
- 2026-07: WMS samostalna app; prijava + dozvole + audit; `lokacija` (QR↔pozicija) aktivan.
  Na GitHubu (`Shywera/wms`). Deploy na Windows Server: `install-servis.bat` (NSSM) + `SERVER.md`.
- **FINALNA VERZIJA (2026-07-10):**
  - **Otključano RADNO → aktivno:** `LOCKED_PREFIXES=()` u `security.py`; base.html sekcija
    "Napredno" (zaprimanje-plan / izdavanje-količina / inventura / prioriteti) gated po dozvoli.
  - **`lokacija/zaprimi` sada puni šifru:** `/postavi` zove `get_adapter().lookup_barcode(barkod)`
    i sprema sifra/naziv/kolicina/jedinica/rok/lot (best-effort). Mock radi odmah; **legacy ERP se uključuje kasnije** (samo `ERP_ADAPTER=erp` + `.env`).
  - **NOVI modul `app/modules/zahtjevnica/`** (models/parser/service/routes + templates): uvoz
    zahtjevnice (**.xlsx/.csv/.pdf**; pdfplumber čita i PDF tablicu), filtar papir vs boje
    (`jedinica=='arak'` ili šifra `50101050…`), **grupiranje po šifri (zbroj količina + spoj RN)**,
    prijedlog paleta (FIFO, cijele palete — reuse `skladiste.service.predlozi_izdavanje`),
    potvrda **skenom** (barkod mora biti među predloženima) → `izvrsi_izdavanje`. Provjere:
    dupli uvoz (`sadrzaj_hash`), dvostruko izdavanje stavke, izdavanje krive/neaktivne palete.
    Rute pod `/zahtjevnica` (dozvola `izdavanje`); nav "Izdavanje po zahtjevnici". Testirano na
    stvarnom PDF-u (40 redaka → 3 papirne + 23 kg; PROMET grupiran 159000). requirements +=
    openpyxl, pdfplumber. Nove tablice preko create_all; stupac `ukljucena` preko ALTER u main.py.
  - **Ručno uključivanje ostalih stavki:** ako boja/lak (kg) sa zahtjevnice IPAK ima stanje u ovom
    skladištu (aktivne palete te šifre), detalj pokaže žuto upozorenje + gumb "Dodaj u izdavanje
    (N pal.)" → `ZahtjevnicaStavka.ukljucena=True` → ulazi u popis za izdavanje (badge "ručno
    dodano" + "makni"; makni/uključi blokirani na izdanoj stavci). Rute `/stavka/{sid}/ukljuci|iskljuci`.
  - **UX pojednostavljenja (bankomat):** dashboard = 3 velike kartice prve (zaprimanje/izdavanje/
    zahtjevnica, gated po dozvoli); sidebar "Napredno" samo admin; uvoz auto-submit na odabir
    datoteke; detalj default "samo arci"; sken-polje auto-fokus (script, HTMX ne poštuje autofocus);
    potvrda bez skena traži JS confirm.
  - **Sljedeće:** kad bude dostupan ERP API — uključiti `ERP_ADAPTER=erp` (šifra/arci iz stvarnog ERP-a pri zaprimanju i lookupu). Po želji: djelomično izdavanje araka (umanjenje palete),
    izdavanje po skeniranju bez prijedloga, izvoz izdanog natrag prema ERP-u (ako se dogovori, inače ERP ostaje READ-ONLY).
