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
goto run

:rebuild
echo [WMS] Postojeci .venv ne radi na ovom racunalu - ponovo gradim...
rmdir /s /q ".venv" 2>nul

:build
echo [WMS] Kreiram okruzenje i instaliram ovisnosti (jednom, ~1-2 min)...
py -3 -m venv .venv
if errorlevel 1 goto nopy
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt

:run
echo.
echo [WMS] Pokrecem server na http://localhost:8600
echo Za prekid: CTRL+C pa zatvori prozor.
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8600
echo.
echo Server je zaustavljen.
pause
goto :eof

:nopy
echo.
echo GRESKA: Python nije pronadjen ("py" ne radi).
echo Instaliraj Python 3 s python.org i ukljuci "Add Python to PATH", pa pokreni run.bat ponovno.
echo.
pause
