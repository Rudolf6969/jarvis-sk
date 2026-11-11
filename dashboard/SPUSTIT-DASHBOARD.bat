@echo off
rem Otvori dashboard aj bez JARVISa (server sa spusti, ak este nebezi).
start "" "%~dp0..\hey-claude\.venv\Scripts\pythonw.exe" "%~dp0server.py"
