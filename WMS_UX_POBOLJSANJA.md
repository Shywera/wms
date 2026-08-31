# WMS UX poboljšanja — Linearan tok, jasnija putanja

## Problem
Trenutni WMS je **funkcijski kompletan**, ali nije optimiziran za **brzo, pogrešno-otporno korištenje** u skladištu:

- ❌ Nakon što radiš Zaprimanje, nije jasno gdje nastaviti
- ❌ Sidebar ima previše opcija za radnika (Napredno, Administracija)
- ❌ Ima dupliciranih operacija (`/lokacija/zaprimi` vs `/skladiste/zaprimanje`)
- ❌ Nema jasnog "završio sam" feedback-a — što dalje?
- ❌ Emojis i vizualni prijedlozi nisu dovoljno jasni (⬇ ⬆ ☰)

**Rezultat:** Radnika je zbunjuće, može slučajno otić na pogrešnu stranicu, ne zna je li nešto uspjelo.

---

## Cilj: "Bankomat" UX
Kao bankomat — jednostavno, linearno, bez mogućnosti greške. Radnik ne razmišlja, samo slijedi.

```
┌─────────────┐
│   Login     │
└──────┬──────┘
       │
┌──────▼──────────────────────────────┐
│     DASHBOARD (3 velike kartice)    │
│  Zaprimanje | Izdavanje | Zahtjevnica│
│      + Karta + Palete (mali)        │
└──────┬───────────────────────────────┘
       │
       ├──→ Zaprimanje: Skeniraj → Mjesto → OK
       │
       ├──→ Izdavanje: Skeniraj → Potvrdi → OK
       │
       └──→ Zahtjevnica: Uvezi → Sken → OK
       
       (U svakom: Clear "← Nazad na Dashboard")
```

---

## Konkretna poboljšanja

### 1. **Dashboard — samo 3 kartice za radnike** ✅ (GOTOVO — samo refinement)

**Sada:** Ok, ali mali tekst i emojis nisu dovoljno jasni.

**Trebalo bi:**
```html
<!-- Veće, jasnije kartice s ikonama (SVG, ne emoji) -->
<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
  <!-- Zaprimanje -->
  <a href="/zaprimi" class="bg-blue-600 hover:bg-blue-700 text-white rounded-2xl p-8 text-center">
    <svg class="w-12 h-12 mx-auto mb-3"><!-- strelica dolje --></svg>
    <div class="text-2xl font-bold">ZAPRIMANJE</div>
    <div class="text-sm mt-2">Skeniraj paletu → odaberi mjesto</div>
  </a>
  
  <!-- Izdavanje -->
  <a href="/izdaj" class="bg-red-600 hover:bg-red-700 text-white rounded-2xl p-8 text-center">
    <svg class="w-12 h-12 mx-auto mb-3"><!-- strelica gore --></svg>
    <div class="text-2xl font-bold">IZDAVANJE</div>
    <div class="text-sm mt-2">Skeniraj paletu → potvrdi</div>
  </a>
  
  <!-- Zahtjevnica -->
  <a href="/zahtjevnica" class="bg-green-600 hover:bg-green-700 text-white rounded-2xl p-8 text-center">
    <svg class="w-12 h-12 mx-auto mb-3"><!-- lista --></svg>
    <div class="text-2xl font-bold">ZAHTJEVNICA</div>
    <div class="text-sm mt-2">Uvezi datoteku → izdaj</div>
  </a>
</div>
```

### 2. **Ujedinti putanje — jedan Zaprimanje, jedan Izdavanje** ✅ GOTOVO (zaprimanje, 2026-08-31)

**Bilo:**
- `/lokacija/zaprimi` (jednostavna, skener)
- `/skladiste/zaprimanje` (plan, više stavki, admin-only u sidebaru)
- `/skladiste/zaprimanje/jedna` (skoro identična `/lokacija/zaprimi`)

**Napravljeno — ali DRUGAČIJE nego što je ovdje bilo zamišljeno:** korisnik je eksplicitno
tražio da bulk-plan NE bude posebna "samo za admin" stranica nego da bude na ISTOM mjestu
kao jednostavan sken, s objašnjenjima, "princip kalkulatora" (zadano brzo/lagano, dodatna
moć vidljiva ali ne nametnuta). Rezultat: `/skladiste/zaprimanje/jedna` uklonjen (pravi
duplikat), a `/skladiste/zaprimanje` (plan) NIJE ostao kao odvojena admin stranica — umjesto
toga, njegov ulaz (broj paleta) je sad sklopivi blok unutar `/lokacija/zaprimi` nakon skena
("📦 Stiže li više paleta odjednom?"), koji vodi na isti (nepromijenjeni) plan-tok. Jedan URL,
jedan ulaz, oba slučaja (1 paleta i bulk) pokrivena — vidi CLAUDE.md "Trenutno stanje".

Izdavanje NIJE dirano u ovom koraku (`/skladiste/izdaj` po količini ostaje zaseban admin alat
u "Napredno" — korisnik je zatražio samo zaprimanje; isti pristup se može primijeniti na
izdavanje ako se zatraži).

### 3. **Jasna navigacija — nema "Napredno" u sidebaru za radnike**

**Sada:**
```
Sidebar:
  Nadzorna ploča
  Operacije
    Zaprimanje
    Izdavanje (skener)
    Zahtjevnica
  Pregled
    Karta
    Palete
  [Napredno] — samo admin
  [Admin]
```

**Trebalo bi:**
```
Radnik vidi:
  Nadzorna ploča
  Karta skladišta
  [Sve palete]
  Moj profil / Odjava

Admin vidi:
  Nadzorna ploča
  Karta skladišta
  Sve palete
  ──────────
  Zaprimanje (plan)
  Izdavanje (količina)
  Inventura
  Prioriteti
  ──────────
  Korisnici
  Log
  Backup
```

### 4. **Після svaке operacije — jasno "šta je sljedeće"** 

**Sada:** Nakon što radiš Zaprimanje, preusmjeriš na što? Nije jasno je li uspjelo.

**Trebalo bi — tri tipa završnog ekrana:**

**A) Zaprimanje OK**
```
┌────────────────────────────┐
│  ✅ ZAPRIMLJENO            │
│  Šifra:  50101050A03       │
│  Naziv:  Papir A4 80g      │
│  Količina: 5000 araka      │
│  Mjesto:  R1A-P05-V2       │
│  Vrijeme: 13:45:22         │
│                            │
│ [← Nazad na nadzornu ploču]│
│ [Zaprimanje encore]        │
└────────────────────────────┘
```

**B) Izdavanje OK**
```
┌────────────────────────────┐
│  ✅ IZDANO                 │
│  Šifra:  50101050A03       │
│  Naziv:  Papir A4 80g      │
│  Količina: 5000 araka      │
│  Vrijeme: 13:46:15         │
│                            │
│ [← Nazad na nadzornu ploču]│
│ [Dalje — još paleta]       │
└────────────────────────────┘
```

**C) Greška — jasna**
```
┌────────────────────────────┐
│  ⚠️ GREŠKA                 │
│  "Paleta nije pronađena"   │
│  Barkod: 000000000         │
│                            │
│  Što učiniti:              │
│  1. Provjeri QR kod        │
│  2. Skenira ponovno        │
│  3. Unesi ručno (ako je... │
│                            │
│ [← Nazad na nadzornu ploču]│
│ [Pokušaj ponovno]          │
└────────────────────────────┘
```

### 5. **Sken-polje — auto-fokus i Enter-submit** ✅ (GOTOVO)

Trebalo bi da se fokus **automatski** vrati na sken-polje nakon potvrde, bez klika.

```html
<input type="text" id="sken" placeholder="Skeniraj QR kod..." autofocus>
<script>
  document.getElementById('sken').addEventListener('keypress', e => {
    if (e.key === 'Enter') {
      // Submit i auto-fokus natrag na polje
      fetch(...).then(() => {
        document.getElementById('sken').value = '';
        document.getElementById('sken').focus();  // ← KEY
      });
    }
  });
</script>
```

### 6. **Metrike — samo važne**

**Sada:** 4 kartice (zauzeto, slobodno, ukupno, ističe) + popunjenost po zonama.

**Trebalo bi:**
- Zauzeto (%) — glavna
- Slobodno — ako je <10% → crveno upozorenje "Nema mjesta!"
- Ističe za 30 dana — ako >5 → crveno upozorenje "Uskoro istječu palete"

Ostalo u posebnom "Admin view" ili klikom.

### 7. **Karta — samo pregled, ne u glavnom toku**

Sada je na Dashboardu kao link. OK je — ostaje, ali:
- Karta se učitava samo na zahtjev (lazy-load)
- Na mobilnom, karta je responsivna

### 8. **Zahtjevnica — jasniji tok**

**Sada:** Popis → Detalj → Skeniranje → Izdaj

**Trebalo bi jasnije:**
```
Dashboard
  ↓
Zahtjevnica: Odaberi datoteku (.xlsx/.pdf)
  ↓
Pregled stavki (koliko papira, koliko kg)
  ↓
Skeniranje paleta (FIFO, barkod mora biti među predloženima)
  ↓
Rezultat (OK ili greška — što nije skenirirano?)
  ↓
[← Nazad na Dashboard] [Dalje — sljedeća zahtjevnica]
```

---

## Implementacijski redoslijed (priority)

### Faza 1 — Brz win (1-2 sata)
- [x] Ujedini putanja: `/lokacija/zaprimi` i `/lokacija/izdaj` — **jedini ulazni bodovi za radnike**
      (2026-08-31: `/skladiste/zaprimanje/jedna*` i `/skladiste/izdaj/jedna*` uklonjeni, sve
      "jedna paleta" poveznice sad vode na `/lokacija/*`; predloženo mjesto iz starog toka
      preneseno u `/lokacija/zaprimi` kao zeleni gumb)
- [x] Dodaj "← Nazad na Dashboard" gumb na **SVAKU** operaciju (završi ili greška)
- [x] Auto-fokus + Enter u sken-polje
- [x] Jasan "OK" ekran nakon uspješne operacije
- [x] Ukloni Napredno/Admin iz sidebara za radnike (provjeravaj dozvole)

### Faza 2 — Refinement (2-3 sata)
- [ ] Veće, jasniji kartice na Dashboardu (SVG ikoname umjesto emoji)
- [ ] Greške s jasnim "Što učiniti" uputorama
- [ ] Metrike samo važne (zauzeto + upozorenja)
- [ ] Karta lazy-load (samo na zahtjev)

### Faza 3 — Opciono (ako ima vremena)
- [ ] Zahtjevnica UX refinement
- [ ] Mobitel optimizacija (karta fullscreen ako je mali ekran)
- [ ] Print lista stavki (za fizički rad)

---

## Rezultat nakon poboljšanja

```
Radnik s dozvolom "zaprimanje":
  Login → Dashboard
    ↓
  Klikne "ZAPRIMANJE"
    ↓
  Skeniraj paletu (auto-focus, unos, Enter)
    ↓
  Prikaz podataka + "Odaberi mjesto"
    ↓
  Klikne potvrdu
    ↓
  ✅ "ZAPRIMLJENO" (jasno, sa svim podacima)
    ↓
  [Nazad na Dashboard] ili [Zaprimanje još]
    ↓
  Slijedi Izdavanje...
```

---

## Napomene za dev

- **Dozvole:** Radnici vide samo `/zaprimi` i `/izdaj`, admin vidi sve
- **URL strukture:** Čuva se `/lokacija` (modularna), ali frontend ima `/zaprimi` kao alias
- **Sidebar:** Gated po dozvoli u base.html (već je tako, samo refinement)
- **Greške:** HTTP 40x vraća JSON s `{"greska": "..."}` — frontend prikazuje u modul
- **Refresh:** Kad radnik završi operaciju, `<form method="post">` ili `fetch()` + JS `window.location = '/skladiste'`
