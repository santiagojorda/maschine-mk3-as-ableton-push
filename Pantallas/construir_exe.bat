@echo off
rem Compila el ejecutable autocontenido en dist\MaschineMK3AsPush
cd /d "%~dp0"

rem Si el driver esta corriendo, PyInstaller no puede reemplazar dist\ (libusb-1.0.dll bloqueada)
powershell -NoProfile -Command "if (Get-Process MaschineMK3AsPush -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo [!] El driver esta corriendo. Cerralo antes de compilar: make stop  ^(o MaschineMK3AsPush.exe --salir^)
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias de compilacion...
.venv\Scripts\pip install -q pyinstaller
if errorlevel 1 goto fallo

echo [2/3] Generando icono...
.venv\Scripts\python prototipo\hacer_icono.py
if errorlevel 1 goto fallo

echo [3/3] Compilando con PyInstaller...
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onedir --noconsole --name MaschineMK3AsPush ^
  --icon prototipo\icono.ico --paths prototipo ^
  --add-data "prototipo\config.example.json;." ^
  --collect-all libusb_package --hidden-import mido.backends.rtmidi --hidden-import rtmidi ^
  prototipo\maschine_mk3.py
if errorlevel 1 goto fallo
if not exist "dist\MaschineMK3AsPush\MaschineMK3AsPush.exe" goto fallo

echo.
echo [+] Compilacion completada con exito en: dist\MaschineMK3AsPush\MaschineMK3AsPush.exe
pause
exit /b 0

:fallo
echo.
echo [!] La compilacion FALLO. Revisa los mensajes de arriba.
pause
exit /b 1
