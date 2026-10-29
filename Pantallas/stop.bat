@echo off
cd /d "%~dp0"
call make.bat stop
timeout /t 3
