@echo off
cd /d "%~dp0"
call make.bat restart
timeout /t 3
