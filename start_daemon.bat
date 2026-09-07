@echo off
cd /d "%~dp0"
start "JiraTgBot" /MIN ".venv\Scripts\pythonw.exe" bot.py
