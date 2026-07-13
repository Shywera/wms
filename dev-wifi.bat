@echo off
cd /d "%~dp0"

if exist ".env" goto venv
echo [WMS] Generiram .env (nasumicni tajni kljuc + admin lozinka)...
for /f %%i in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')"') do set "SK=%%i"
>.env echo SECRET_KEY=%SK%
>>.env echo ADMIN_PASSWORD=admin

:venv
if not exist ".venv\Scripts\python.exe" goto build
.venv\Scripts\python.exe -c "import fastapi, uvicorn" 1>nul 2>nul
if errorlevel 1 goto rebuild
goto net

:rebuild
echo [WMS] Postojeci .venv ne radi na ovom racunalu - ponovo gradim...
rmdir /s /q ".venv" 2>nul

:build
echo [WMS] Kreiram okruzenje i instaliram ovisnosti...
py -3 -m venv .venv
if errorlevel 1 goto nopy
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt

:net
set "IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do if not defined IP set "IP=%%a"
if defined IP set "IP=%IP: =%"

echo.
echo Pokrecem WMS server (WiFi mreza)...
echo   Lokalno:  http://localhost:8600
if defined IP echo   Mreza:    http://%IP%:8600
echo.
echo Sve IPv4 adrese ovog racunala:
ipconfig | findstr /c:"IPv4"
echo.
echo NAPOMENA: Ako drugi uredjaj ne moze pristupiti, pokreni JEDNOM kao Administrator:
echo   netsh advfirewall firewall add rule name="WMS dev 8600" dir=in action=allow protocol=TCP localport=8600
echo.

.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8600
pause
goto :eof

:nopy
echo.
echo GRESKA: Python nije pronadjen. Instaliraj Python 3 (Add to PATH) pa pokreni ponovno.
echo.
pause
