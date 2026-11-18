@echo off
cd /d "%~dp0backend"
python -m app.seed
pause
