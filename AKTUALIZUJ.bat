@echo off
title JARVIS - aktualizacia
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalaciaktualizuj.ps1"
echo.
pause
