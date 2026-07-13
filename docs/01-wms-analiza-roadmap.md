# WMS — analiza, usporedba s WMS standardom i roadmap

> Istraživanje (web, lipanj 2026.) + analiza koda. Referenca za buduća proširenja.
> **Trenutni smjer:** bez API-ja, ručno povezivanje **QR palete ↔ pozicija**, jedna
> paleta po jedna, skladištar sam bira mjesto (skenira poziciju ili je odabere na
> karti). Napredne funkcije (plan-zaprimanje, izdavanje po količini, FIFO/FEFO,
> prioriteti, inventura) su **zaključane kao "RADNO"** — kod ostaje, ne koristi se.

> **Napravljeno (lipanj 2026.):** jednostavni QR↔pozicija tok (`/lokacija`), zaključavanje
> naprednog ("RADNO"), prijava+dozvole+audit, **detaljni audit** (koja paleta gdje, tko), te
> **reslovi** — više paleta na istu poziciju uz potvrdu, označene zasebnom (ljubičastom) bojom
> na karti. TODO (s API-jem): izračun stane li još reslova iz **broja araka × debljine papira**.

## 1. Što app već ima
Zaprimanje (multi-plan + jedna) · izdavanje po količini + FIFO/FEFO + ostatak ·
inventura · prioriteti (prostorni modovi) · karta = tlocrt sa statusima ·
sve-palete + pretraga · PDF (stanje + lista) · ERP adapter (mock/legacy read-only) ·
fiksni REGALI (1473, unique aktivna pozicija) · prijava + granularne dozvole + audit log.

## 2. Gap vs. "table-stakes" WMS (generičko)

| Sposobnost | Stanje | Komentar |
|---|---|---|
| Lot/batch sljedivost (genealogija) | djelom. | `lot` postoji, nema prikaza lanca (recall). |
| Quarantine / QC-hold koji blokira izdavanje | nema | Tiskara ima česte QC blokade → pravi jaz. |
| Multi-UOM (kom/arak/role/kg/m) | nema | Samo "arak". Ključno za papir (vidi §3). |
| Cycle counting (ABC, kontinuirano) | djelom. | Samo puna inventura. |
| KPI / izvještaji (dock-to-stock, točnost, obrtaj, starenje) | djelom. | Imaš popunjenost; fali KPI + exception. |
| GS1/SSCC license-plate + standard naljepnica | nema | Sirovi QR; razmotriti GS1-128/SSCC + 2D lokacije. |
| Replenishment / dinamičko slotting | N/P | Fiksni regali → nije primjenjivo. |

## 3. Papir / karton / etikete — specifično (najveća vrijednost)

| Tema | Prijedlog | Zašto za tebe |
|---|---|---|
| Role (reel) uz arke | tip jedinice rola/arak; širina, ø, jezgra, **preostala dužina (m)** + **kg** | Samoljepljivi za etikete dolazi u rolama. |
| Multi-UOM (kg↔m↔arak) | zaliha u sve tri; konverzija gramatura×širina | Mlin prodaje kg, preša troši m. |
| Djelomične role / ostaci | povrat s ažuriranom dužinom + oznaka ostatak; zadrži reel ID+lot | Proširenje postojeće "ostatak" logike. |
| Rok PSA ljepila → FEFO | datum proizvodnje + rok po ljepilu → istek; akril ~1–2 g, guma ~6–12 mj, silikon kratko | Papir ne stari, **ljepilo da** — najjasniji label-jaz. |
| Aklimatizacija (hold 24–72 h) | tempirani karantenski status prije tiska | Papir ne smije kamion→preša. |
| Klima-zona | 20–22 °C / 45–55 % RH, opc. senzor + alarm | Papir je higroskopan. |
| Konstrukcija | lice (bijeli/metalizirani)+ljepilo+liner; smjer vlakana MD/CD; gsm | Vlakna lome registar; ljepilo nosi rok. |
| FSC/PEFC | claim + šifra certifikata po lotu + segregacija | Ako prodajete certificirane etikete. |
| Skeniraj dobavljačku reel-naljepnicu | mapiraj CEPI/CCB barkod role u zapis | Brže zaprimanje. |
| Otpad / matrica / offcut | utrošeno vs otpad → pomirenje prinosa | Konvertiranje normalno radi otpad. |

## 4. UI/UX (Zebra PDA + supervizor)

**PDA:** multi-senzorni feedback na skan (beep+vibracija+boja; OK vs greška) · auto-fokus
skener-polja + auto-advance · blokiraj (ne samo upozori) krivu lokaciju/količinu/isteklo ·
veliki targeti 56–64 dp za primarne, jedan-zadatak-po-ekranu, veliki brojevi, font koji
razlikuje 0/O · wizard progress · kiosk/lock-task · offline queue (PWA, napredno).

**Supervizor:** KPI ploča (dock-to-stock, točnost, obrtaj, starenje, zauzeće) ·
exception panel (isteklo/blizu roka/QC-hold/neslaganja, klikabilno) · heatmap zauzeća na
tlocrtu · globalna pretraga (šifra/QR/lokacija/lot/korisnik).

## 5. Roadmap po prioritetu

**Tier 1 (visoka vrijednost, razuman trošak):** status palete + QC-hold (blokira izdavanje) ·
rok iz datuma proizvodnje + tip ljepila → FEFO alarmi · skener feedback (zvuk/vibracija/boja) ·
supervizor KPI + exception panel.

**Tier 2:** role + multi-UOM (kg/m/arak) + djelomične role · aklimatizacijski hold + klima-zona ·
lot sljedivost + cycle counting (ABC).

**Tier 3 (napredno):** GS1/SSCC license-plate + 2D lokacijske naljepnice · FSC/PEFC + segregacija ·
offline PWA, IoT senzori, heatmap analitika.

## Izvori (web istraživanje)
- GS1 Logistic Label Guideline (GS1-128, SSCC, AI); GS1 US SSCC.
- Avery Dennison — Storage Conditions for Pressure-Sensitive Materials (rok PSA, temp/RH).
- PaperIndex — parent roll receiving controls (atributi role, karantena, vlaga).
- Konecranes / Turck Vilant — WMS za role papira (reel ID, ø/jezgra/kg, RFID).
- FSC Chain of Custody (FSC-STD-40-004); FSC vs PEFC claims.
- NN/g Touch Target Size; W3C WCAG 2.2 SC 2.5.8; MS Dynamics 365 warehouse haptic feedback.
- Logistics Viewpoints, Hopstack, SG Systems, Made4net — WMS feature/KPI pregledi.
