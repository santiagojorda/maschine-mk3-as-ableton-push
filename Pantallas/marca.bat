@echo off
cd /d "%~dp0"
set /p NOTA=Nota (Enter para marcar sin nota): 
call make.bat marca %NOTA%
timeout /t 2 >nul
