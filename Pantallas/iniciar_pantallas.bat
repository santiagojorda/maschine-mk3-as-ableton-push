@echo off
title Maschine MK3 Display Driver
cd /d "%~dp0"

echo ========================================================
echo   Iniciando Pantallas Maschine MK3 para Ableton Live 12
echo ========================================================
echo.

if exist "MaschineMK3AsPush.exe" (
    start "" "MaschineMK3AsPush.exe"
    echo [+] Driver iniciado con ejecutable local.
    goto :fin
)

if exist "dist\MaschineMK3AsPush\MaschineMK3AsPush.exe" (
    start "" "dist\MaschineMK3AsPush\MaschineMK3AsPush.exe"
    echo [+] Driver iniciado con dist\MaschineMK3AsPush\MaschineMK3AsPush.exe.
    goto :fin
)

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" prototipo\supervisor.py
    echo [+] Driver iniciado mediante Python (.venv).
    goto :fin
)

echo [!] Error: No se encontro MaschineMK3AsPush.exe ni el entorno .venv.
echo     Revisa docs\GUIA-INSTALACION.md para mas detalles.
pause

:fin
ping 127.0.0.1 -n 3 >nul
