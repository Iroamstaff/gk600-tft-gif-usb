@echo off
title GK600 - boot animation
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gk600_easy.ps1" -Mode boot -Picture "%~1"
echo.
pause
