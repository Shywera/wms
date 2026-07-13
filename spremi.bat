@echo off
cd /d "%~dp0"
setlocal
set "PORUKA=%*"
if "%PORUKA%"=="" set "PORUKA=Update s racunala %COMPUTERNAME%"

echo [WMS] Dodajem promjene...
git add -A
git commit -m "%PORUKA%"

echo.
echo [WMS] Povlacim promjene s GitHuba (spajanje)...
git pull --no-rebase --no-edit
if errorlevel 1 goto konflikt

echo.
echo [WMS] Saljem na GitHub...
git push
if errorlevel 1 goto pusherr

echo.
echo [WMS] Gotovo - sve je na GitHubu.
pause
goto :eof

:konflikt
echo.
echo GRESKA: "git pull" nije uspio (vjerojatno konflikt spajanja).
echo Rijesi konflikt rucno pa ponovo pokreni spremi.bat.
pause
goto :eof

:pusherr
echo.
echo GRESKA pri slanju (push). Provjeri internet/prijavu pa probaj ponovo.
pause
