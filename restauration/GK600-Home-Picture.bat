@echo off
title GK600 - home screen picture
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gk600_easy.ps1" -Mode picture -Picture "%~1"
echo.
pause
