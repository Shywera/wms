# Skladište — WMS (samostalni app)

Samostalna verzija skladišnog modula (warehouse / pallet management) za tiskaru
samoljepljivih etiketa. **Isti kod** kao WMS modul u ERP/MES/WMS sustavu
(`app/modules/skladiste`), ali vrti se zasebno: vlastita baza, server i izbornik.

## Funkcionalnost

- **Zaprimanje** — multi-paletni plan (šifra → broj paleta → zona → lista pozicija →
  skeniraj paletu+poziciju) + zaprimanje jedne palete (pod-opcija).
- **Izdavanje** — po količini araka (FIFO/FEFO alokacija cijelih paleta + ostatak) +
  izdavanje jedne palete (pod-opcija).
- **Inventura** — skeniranje stanja (nedostaje / neočekivano).
- **Prioriteti** — pravila smještaja po šifri + prostorni modovi.
- **Karta skladišta** — tlocrt (pogled odozgo) + detalji po zonama/visinama.
- **Sve palete** — lista svih aktivnih paleta s pretragom.
- **PDF ispisi** — stanje skladišta (tlocrt) i lista pozicija za zaprimanje.

## Pokretanje

```bat
dev-wifi.bat     REM za rad na WiFi/LAN-u (Zebra PDA) — ispiše mrežni URL
run.bat          REM jednostavno lokalno/LAN pokretanje
```

`dev-wifi.bat` prvi put napravi `.venv`, instalira ovisnosti, **ispiše lokalni i mrežni
URL** (npr. `http://192.168.1.8:8600`) koji upišeš na Zebra PDA / mobitelu, i digne server
na `0.0.0.0:8600`. Ako drugi uređaj ne može pristupiti, jednom kao Admin otvori port:
`netsh advfirewall firewall add rule name="WMS dev 8600" dir=in action=allow protocol=TCP localport=8600`.
(Port 8600 ≠ ERP 8000, pa oba mogu raditi istovremeno.)

Ručno:

```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --port 8600 --reload
```

## Rad od doma (GitHub)

Kod je na `https://github.com/Shywera/wms`. Prvo kloniranje na drugom računalu:

```bat
git clone https://github.com/Shywera/wms.git
cd wms
run.bat
```

Za dohvat zadnjih promjena: dvoklik na **`update.bat`** (`git pull` + osvježavanje ovisnosti).

> **Važno:** baza (`wms.db`) i `.env` se **ne** sinkroniziraju preko GitHuba (namjerno —
> sadrže podatke i tajne). Sinkronizira se samo **kod**. Svako računalo ima vlastitu bazu;
> `run.bat` na novom računalu generira novi `.env` i praznu bazu (admin/admin). Za iste
> podatke na više mjesta kopiraj `wms.db` ručno ili podesi zajedničku bazu.

## Konfiguracija (`.env`)

`run.bat` na **prvom pokretanju sam kreira `.env`** s nasumičnim `SECRET_KEY` (za potpis
session cookieja) i `ADMIN_PASSWORD=admin`. Možeš ga urediti:

- `DATABASE_URL` — zadano `sqlite:///./wms.db` (lokalni SQLite). Tablice se kreiraju
  automatski na startu (`create_all`).
- `SECRET_KEY` — tajni ključ (auto-generiran; ne dijeli).
- `ADMIN_PASSWORD` — lozinka početnog admina (vrijedi samo dok je baza prazna).
- `ERP_ADAPTER` — `mock` (zadano; 165 demo papira iz `_mock_papiri.json`) ili
  `erp` (REST + Basic na legacy ERP, **read-only**) uz `ERP_API_URL/USER/PASS`.

## Backup baze
- **Automatski:** svaki start napravi kopiju u `backup\wms_<datum_vrijeme>.db` (zadnjih 20).
- **Ručno:** dvoklik na **`backup.bat`**.
- **Iz appa:** sidebar (admin) → **⤓ Backup baze (.db)** preuzme trenutnu bazu.
- Glavna baza je `wms.db` — pri selidbi **kopiraj tu datoteku**.

## Prijava, korisnici i dozvole

Aplikacija ima **prijavu** (bcrypt lozinke, potpisani httpOnly session cookie) i
**granularne dozvole** po korisniku:

| Dozvola | Što omogućuje |
|---------|----------------|
| `zaprimanje` | Zaprimanje paleta |
| `izdavanje` | Izdavanje paleta |
| `inventura` | Inventura |
| `prioriteti` | Uređivanje pravila smještaja |
| `admin` | Administracija (korisnici + log) — **admin ima sve** |

Pregled (nadzorna ploča, karta, sve palete) ima svaki prijavljeni korisnik.
Sidebar i pristup prilagođavaju se dozvolama; nedozvoljena radnja vraća 403.

**Prva prijava:** pri praznoj bazi automatski se kreira admin —
korisnik `admin`, lozinka iz `ADMIN_PASSWORD` (zadano `admin`). **Promijeni je odmah**
u `Administracija → Korisnici`.

**Audit log** (`Administracija → Log aktivnosti`): bilježi se svaka promjena
(tko, kad, koja akcija) — zaprimanja, izdavanja, inventure, izmjene korisnika, prijave/odjave.

## Hardver

Ciljani uređaj: **Zebra PDA** (hardverski keyboard-wedge skener — skenira tekst + Enter
u fokusirano polje). Sva polja za skeniranje su velika, Enter potvrđuje, fokus se vraća.

## Struktura

```
app/
  main.py                 # FastAPI app, create_all, seed admin, auth/audit middleware
  core/                   # config (secret_key, db) + database (vlastiti, samostalni)
  modules/
    skladiste/            # ISTI kod kao u ERP-u (config/models/adapter/service/routes/pdf) — NETAKNUT
    auth/                 # NOVO: security (dozvole/bcrypt) + models (korisnik/audit_log) + routes (login/admin)
  templates/
    base.html             # WMS-only izbornik, gated po dozvolama + user box
    auth/                 # login, korisnici (admin), log, 403
    skladiste/            # ISTI templati kao u ERP-u
```

> Prijava/dozvole/audit dodani su kroz **middleware + `auth` modul**, BEZ diranja
> `skladiste` koda — pa skladišni modul ostaje 1:1 s ERP verzijom.

> Modul je kopija iz ERP/MES/WMS projekta. Promjene u logici po potrebi sinkronizirati
> s `app/modules/skladiste` u ERP-u (i obrnuto).
