# Pokretanje WMS-a na serveru (Windows Server)

Cilj: WMS radi **isto kao sad** (uvicorn, port 8600, LAN, Zebra skener), ali se vrti na
serveru i **uvijek je upaljen** — ne ovisi o ničijem računalu. Baza je na serveru, pa svi
rade nad **istim podacima**.

## Preduvjeti (na serveru, jednom)
- **Python 3** (python.org, uključi *Add Python to PATH*) i **Git**.
- Server ima **statičku LAN IP** (npr. `192.168.1.50`) — da se adresa ne mijenja.
- Administratorski pristup (servis se instalira kao Administrator).

## Postavljanje (5 koraka)
1. **Kloniraj kod** na server (npr. u `C:\apps\wms`):
   ```
   git clone https://github.com/Shywera/wms.git C:\apps\wms
   ```
2. **Izgradi okruženje**: u toj mapi dvoklik na **`run.bat`** (napravi `.venv` + `.env`).
   Kad se digne server, zatvori prozor (`CTRL+C`).
3. U **`.env`** postavi jaku lozinku: `ADMIN_PASSWORD=nekaJakaLozinka` (pa obriši `wms.db`
   ako je već stvoren s admin/admin, da se admin ponovo seed-a s novom lozinkom).
4. **Instaliraj servis**: desni klik na **`install-servis.bat`** → *Run as administrator*.
   - Skripta skine NSSM, napravi servis **„WMS Skladiste"** (auto-start na boot, auto-restart
     nakon pada), otvori firewall port 8600 i pokrene ga.
5. **Provjeri**: s bilo kojeg računala/Zebre u mreži otvori `http://IP-SERVERA:8600`.
   (IP servera vidiš naredbom `ipconfig`.)

Gotovo — od sad se WMS diže sam kad se server upali.

## Svakodnevni rad
- **Svi korisnici i Zebra MC3400** idu na `http://IP-SERVERA:8600`. Jedna zajednička baza
  (`wms.db`) na serveru — nema više „svako računalo svoja baza".
- **Ažuriranje koda**: na serveru pokreni **`update.bat`** (git pull), pa restartaj servis:
  ```
  nssm restart WMS
  ```
  (ili u `services.msc` → „WMS Skladiste" → Restart).
- **Backup**: podesi Windows Task Scheduler da dnevno kopira `C:\apps\wms\wms.db` na drugi
  disk / mrežni share / oblak. (App uz to radi auto-backup u mapu `backup\`, ali tu kopiju
  drži **izvan** servera.)

## Upravljanje servisom
```
nssm start WMS           REM pokreni
nssm stop WMS            REM zaustavi
nssm restart WMS         REM restart (nakon update.bat)
nssm remove WMS confirm  REM ukloni servis
```
Log servera je u `servis.log` (pored aplikacije).

## Napomene
- Ako se poslije nadogradi Python na serveru, `.venv` može puknuti → pokreni `run.bat`
  jednom (ponovo izgradi okruženje) pa `nssm restart WMS`.
- **HTTPS** (za sigurnije lozinke na mreži) je opcionalan — najlakše preko **Caddy** reverse
  proxyja ispred porta 8600. Za Zebra keyboard-wedge skeniranje HTTPS nije nužan.
- **Pristup od doma**: instaliraj **Tailscale** na server (i kućno računalo) → siguran pristup
  bez otvaranja porta na internet. Reci Claudeu ako želiš detaljne upute.
