@echo off
cd /d "%~dp0"

if not exist "wms.db" goto nodb
if not exist "backup" mkdir backup
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
copy /Y "wms.db" "backup\wms_%TS%.db" >nul
echo Backup spremljen: backup\wms_%TS%.db
echo.
pause
goto :eof

:nodb
echo Baza wms.db jos ne postoji - pokreni app barem jednom (run.bat).
echo.
pause
