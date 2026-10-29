@echo off
title Detener Maschine MK3 Driver
cd /d "%~dp0"

echo ========================================================
echo   Deteniendo Pantallas Maschine MK3
echo ========================================================
echo.

if exist "MaschineMK3AsPush.exe" (
    MaschineMK3AsPush.exe --salir >nul 2>&1
    goto :verificar
)

if exist "dist\MaschineMK3AsPush\MaschineMK3AsPush.exe" (
    dist\MaschineMK3AsPush\MaschineMK3AsPush.exe --salir >nul 2>&1
    goto :verificar
)

:verificar
taskkill /F /IM MaschineMK3AsPush.exe >nul 2>&1
echo [+] Servicio de pantallas detenido.
ping 127.0.0.1 -n 2 >nul
