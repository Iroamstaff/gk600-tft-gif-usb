@echo off
title GK600 - panel
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\restauration\gk600_easy.ps1" -Mode panel
echo.
pause
