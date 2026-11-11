@echo off
title JARVIS - instalacia
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalacia\instaluj.ps1"
echo.
pause
