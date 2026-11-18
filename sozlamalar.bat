@echo off
chcp 65001 >nul
REM Uzilmas — sozlamalar (.env) faylini TO'G'RI joyda oçadi
cd /d "%~dp0backend"
if not exist .env copy .env.example .env >nul
echo Sozlamalar fayli: %cd%\.env
echo Kalitlarni yozing, Ctrl+S bilan saqlang va Bloknotni yoping.
notepad .env
