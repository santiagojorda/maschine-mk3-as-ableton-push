@echo off
setlocal

rem Detectar si estamos en la raiz del proyecto o dentro de maschine-mk3-driver
if exist "%~dp0maschine-mk3-driver" (
    set "ROOT_DIR=%~dp0"
    set "DRIVER_DIR=%~dp0maschine-mk3-driver"
) else (
    set "DRIVER_DIR=%~dp0"
    set "ROOT_DIR=%~dp0..\"
)

set "DIST_EXE=%DRIVER_DIR%\dist\MaschineMK3AsPush\MaschineMK3AsPush.exe"
set "LOCAL_EXE=%DRIVER_DIR%\MaschineMK3AsPush.exe"
set "VENV_PY=%DRIVER_DIR%\.venv\Scripts\python.exe"

set "TARGET=%~1"
if "%TARGET%"=="" goto help
if /i "%TARGET%"=="start" goto cmd_start
if /i "%TARGET%"=="monitor" goto cmd_monitor
if /i "%TARGET%"=="diagnostico" goto cmd_diagnostico
if /i "%TARGET%"=="marca" goto cmd_marca
if /i "%TARGET%"=="stop" goto cmd_stop
if /i "%TARGET%"=="restart" goto cmd_restart
if /i "%TARGET%"=="status" goto cmd_status
if /i "%TARGET%"=="help" goto help

echo.
echo [!] Comando '%TARGET%' no reconocido.
echo.
goto help

:cmd_start
echo ========================================================
echo   [+] Iniciando Driver de Pantallas - Maschine MK3
echo ========================================================
echo.

powershell -NoProfile -Command "if (Get-Process MaschineMK3AsPush -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto start_already_running

if exist "%DIST_EXE%" (
    echo [*] Arrancando ejecutable: %DIST_EXE%
    cd /d "%DRIVER_DIR%"
    start "" "%DIST_EXE%"
    cd /d "%ROOT_DIR%"
    goto check_start
)

if exist "%LOCAL_EXE%" (
    echo [*] Arrancando ejecutable local: %LOCAL_EXE%
    start "" "%LOCAL_EXE%"
    goto check_start
)

if exist "%VENV_PY%" (
    echo [*] Arrancando via Python venv...
    cd /d "%DRIVER_DIR%"
    start "" "%VENV_PY%" "prototipo\supervisor.py"
    cd /d "%ROOT_DIR%"
    goto check_start
)

echo [!] Error: No se encontro el ejecutable ni el entorno .venv en maschine-mk3-driver.
goto end

:start_already_running
echo [!] El driver ya esta corriendo (MaschineMK3AsPush.exe activo).
echo     Usa 'make restart' si necesitas reiniciarlo.
goto end

:check_start
ping 127.0.0.1 -n 3 >nul
powershell -NoProfile -Command "if (Get-Process MaschineMK3AsPush -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
    echo [+] Driver iniciado con EXITO y supervisado en segundo plano.
) else (
    echo [*] Driver lanzado. Verificando procesos...
)
goto end


:cmd_monitor
echo ========================================================
echo   [+] Iniciando Monitor de Rendimiento y Leaks Web
echo ========================================================
echo.

powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -like '*monitor_set.py*' }; if ($p) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto monitor_already_running

cd /d "%ROOT_DIR%"
echo [*] Iniciando servidor de telemetria en puerto 8888...
start "Live Benchmark y Monitor - Ableton y VDJ" python rendimiento\monitor_set.py --interval 3 --port 8888

ping 127.0.0.1 -n 3 >nul
echo [*] Abriendo Dashboard Web en http://localhost:8888 ...
start http://localhost:8888
echo [+] Monitor activo en consola y dashboard abierto en navegador.
goto end

:monitor_already_running
echo [!] El monitor ya esta corriendo.
echo [*] Abriendo el dashboard en el navegador: http://localhost:8888
start http://localhost:8888
goto end


:cmd_diagnostico
echo ========================================================
echo   [+] Monitor en modo diagnostico (muestreo de 1 segundo)
echo ========================================================
echo.
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -like '*monitor_set.py*' }; if ($p) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
    echo [!] El monitor ya esta corriendo. Cerralo con 'make stop' y volve a abrirlo con 'make diagnostico'.
    goto end
)
cd /d "%ROOT_DIR%"
start "Monitor diagnostico - Ableton y VDJ" python rendimiento\monitor_set.py --diagnostico --port 8888
ping 127.0.0.1 -n 3 >nul
start http://localhost:8888
echo [+] Monitor activo. Cada sesion queda en rendimiento\sesiones\
goto end


:cmd_marca
cd /d "%ROOT_DIR%"
python rendimiento\marca.py %~2 %~3 %~4 %~5 %~6 %~7 %~8 %~9
goto end


:cmd_stop
echo ========================================================
echo   [-] Deteniendo Driver de Pantallas y Monitor
echo ========================================================
echo.

cd /d "%ROOT_DIR%"
python rendimiento\marca.py --cerrar >nul 2>&1
ping 127.0.0.1 -n 6 >nul

python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.5); s.sendto(b'salir', ('127.0.0.1', 9020)); s.close()" >nul 2>&1

ping 127.0.0.1 -n 2 >nul

taskkill /F /IM MaschineMK3AsPush.exe >nul 2>&1

powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and ($_.CommandLine -like '*supervisor.py*' -or $_.CommandLine -like '*dj_screens.py*' -or $_.CommandLine -like '*vdj_puerto.py*') }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force }" >nul 2>&1
echo [-] Driver de pantallas y supervisor detenidos.

powershell -NoProfile -Command "$mon = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -like '*monitor_set.py*' }; foreach ($p in $mon) { Stop-Process -Id $p.ProcessId -Force }" >nul 2>&1
echo [-] Monitor de rendimiento detenido.

echo.
echo [+] Procesos auxiliares cerrados limpiamente.
echo [*] Ableton Live y VirtualDJ continuan funcionando intactos.
goto end


:cmd_restart
echo ========================================================
echo   [!] Reiniciando Driver de Pantallas (Panico / Refresh)
echo ========================================================
echo.
call :cmd_stop
echo.
echo [*] Esperando 1 segundo para liberar puertos USB y MIDI...
ping 127.0.0.1 -n 2 >nul
echo.
call :cmd_start
goto end


:cmd_status
echo ========================================================
echo   [*] Estado de Procesos del Sistema en Vivo
echo ========================================================
echo.
powershell -NoProfile -Command ^
  "$targets = @('Live', 'Ableton Live 12 Suite', 'VirtualDJ', 'virtualdj_x64', 'MaschineMK3AsPush');" ^
  "Write-Host '--- PROCESOS PRINCIPALES ---' -ForegroundColor Cyan;" ^
  "foreach ($t in $targets) {" ^
  "  $procs = Get-Process -Name $t -ErrorAction SilentlyContinue;" ^
  "  if ($procs) {" ^
  "    foreach ($p in $procs) {" ^
  "      $ram = [math]::Round($p.WorkingSet64 / 1MB, 1);" ^
  "      Write-Host (' [ACTIVO]   {0,-22} (PID {1,6}) | RAM: {2,7} MB' -f $p.ProcessName, $p.Id, $ram) -ForegroundColor Green;" ^
  "    }" ^
  "  }" ^
  "};" ^
  "Write-Host '';" ^
  "Write-Host '--- MONITOR & TELEMETRIA ---' -ForegroundColor Cyan;" ^
  "$mon = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*python*' -and $_.CommandLine -like '*monitor_set.py*' };" ^
  "if ($mon) {" ^
  "  Write-Host (' [ACTIVO]   monitor_set.py       (PID {0,6}) | Web: http://localhost:8888' -f $mon.ProcessId) -ForegroundColor Green;" ^
  "} else {" ^
  "  Write-Host ' [APAGADO]  monitor_set.py' -ForegroundColor DarkGray;" ^
  "};"
goto end


:help
echo Uso de comandos rapidos:
echo   make start       - Inicia el driver de pantallas de la Maschine MK3
echo   make monitor     - Levanta el monitor de rendimiento y abre el dashboard web
echo   make diagnostico - Igual, pero con muestreo de 1 segundo (para cazar glitches)
echo   make marca [nota]- Marca la hora exacta en la sesion que se esta midiendo
echo   make stop        - Detiene el driver y el monitor de forma limpia
echo   make restart     - Reinicia el driver de pantallas en 1 segundo (panico/reset)
echo   make status      - Muestra que componentes estan activos y su uso de memoria
echo.
goto end

:end
