@echo off
title JARVIS
if not exist "%~dp0hey-claude\.venv\Scripts\python.exe" goto :neinstalovany
echo.
echo  JARVIS startuje. Pockaj na riadok [ready] a na ostrovcek hore na obrazovke.
echo  Prvy start stahuje modely reci, moze trvat aj 10 minut.
echo.
echo    1. Povedz "Hey Jarvis" a pockaj, kym ostrovcek ukaze, ze pocuva.
echo    2. Hovor po slovensky. Na otazku odpovie hned, pracu robi na pozadi.
echo    3. "Ako to ide?" povie stav ulohy. "Prestan to robit" ju zastavi.
echo    4. Toto okno nechaj otvorene. Ked ho zavries, Jarvis skonci.
echo.
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
rem Dashboard: samostatny proces, ktory len cita stav. JARVIS na nom nezavisi.
if exist "%~dp0dashboard\server.py" start "" "%~dp0hey-claude\.venv\Scripts\pythonw.exe" "%~dp0dashboard\server.py"
cd /d "%~dp0hey-claude"
call run.cmd
pause
exit /b 0

:neinstalovany
echo.
echo  Jarvis este nie je nainstalovany. Spusti najprv INSTALUJ.bat.
echo.
pause
exit /b 1
