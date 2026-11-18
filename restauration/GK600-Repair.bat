@echo off
title GK600 - screen repair
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gk600_easy.ps1" -Mode repair
echo.
pause
