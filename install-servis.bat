@echo off
REM ===== WMS kao Windows servis (uvijek upaljen, auto-start na boot) =====
REM Pokreni kao ADMINISTRATOR (desni klik -> Run as administrator).
setlocal
cd /d "%~dp0"

set "SERVIS=WMS"
set "PORT=8600"
set "PYW=%~dp0.venv\Scripts\python.exe"

REM --- Administratorske ovlasti? ---
net session >nul 2>&1
if errorlevel 1 goto noadmin

REM --- Postoji li okruzenje (.venv)? ---
if not exist "%PYW%" goto novenv

REM --- Pronadji nssm.exe (pored skripte ili u PATH-u) ---
set "NSSM="
if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if not defined NSSM for %%i in (nssm.exe) do if exist "%%~$PATH:i" set "NSSM=%%~$PATH:i"
if not defined NSSM goto getnssm

:install
echo [WMS] Uklanjam stari servis ako postoji...
"%NSSM%" stop %SERVIS% >nul 2>&1
"%NSSM%" remove %SERVIS% confirm >nul 2>&1

echo [WMS] Instaliram servis "%SERVIS%"...
"%NSSM%" install %SERVIS% "%PYW%"
"%NSSM%" set %SERVIS% AppParameters "-m uvicorn app.main:app --host 0.0.0.0 --port %PORT%"
"%NSSM%" set %SERVIS% AppDirectory "%~dp0"
"%NSSM%" set %SERVIS% DisplayName "WMS Skladiste (port %PORT%)"
"%NSSM%" set %SERVIS% Description "Skladiste / WMS - FastAPI (uvicorn) na portu %PORT%"
"%NSSM%" set %SERVIS% Start SERVICE_AUTO_START
"%NSSM%" set %SERVIS% AppStdout "%~dp0servis.log"
"%NSSM%" set %SERVIS% AppStderr "%~dp0servis.log"
"%NSSM%" set %SERVIS% AppRotateFiles 1
"%NSSM%" set %SERVIS% AppExit Default Restart

echo [WMS] Otvaram firewall port %PORT%...
netsh advfirewall firewall delete rule name="WMS %PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="WMS %PORT%" dir=in action=allow protocol=TCP localport=%PORT% >nul

echo [WMS] Pokrecem servis...
"%NSSM%" start %SERVIS%

echo.
echo ============================================================
echo  Gotovo. Servis "%SERVIS%" radi i dizat ce se sam na startu.
echo  Adresa (s bilo kojeg racunala u mrezi):  http://IP-SERVERA:%PORT%
echo  IP servera vidis s naredbom:  ipconfig
echo.
echo  Upravljanje servisom:
echo     "%NSSM%" restart %SERVIS%     (nakon update.bat)
echo     "%NSSM%" stop %SERVIS%
echo     "%NSSM%" remove %SERVIS% confirm
echo  ili preko  services.msc  (trazi "WMS Skladiste")
echo ============================================================
pause
goto :eof

:getnssm
echo [WMS] NSSM (upravitelj servisa) nije pronadjen - preuzimam...
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'nssm.zip' -UseBasicParsing; Expand-Archive -Path 'nssm.zip' -DestinationPath 'nssm_tmp' -Force; Copy-Item 'nssm_tmp\nssm-2.24\win64\nssm.exe' '.\nssm.exe' -Force; Remove-Item 'nssm.zip','nssm_tmp' -Recurse -Force } catch { exit 1 }"
if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if defined NSSM goto install
echo.
echo GRESKA: ne mogu automatski preuzeti NSSM (nema interneta ili je stranica nedostupna).
echo Rucno: otvori  https://nssm.cc/download , skini zip, iz mape "win64" kopiraj
echo "nssm.exe" pored ove skripte, pa ponovo pokreni install-servis.bat.
pause
goto :eof

:novenv
echo GRESKA: mapa ".venv" ne postoji.
echo Prvo pokreni run.bat jednom (izgradi okruzenje + .env), pa onda ovu skriptu.
pause
goto :eof

:noadmin
echo Ova skripta mora se pokrenuti kao ADMINISTRATOR.
echo Desni klik na install-servis.bat -^> "Run as administrator".
pause
