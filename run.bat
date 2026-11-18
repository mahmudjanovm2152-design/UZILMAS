@echo off
chcp 65001 >nul
title Uzilmas
REM Uzilmas — Windows uchun ishga tushirish (venv'siz, xatoda oyna yopilmaydi)
cd /d "%~dp0backend"
echo Papka: %cd%

where python >nul 2>nul
if errorlevel 1 (
  echo [XATO] Python topilmadi. python.org dan o'rnating va "Add to PATH" ni belgilang.
  pause & exit /b 1
)

echo [1/3] Kutubxonalar o'rnatilmoqda...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [XATO] Kutubxonalar o'rnatilmadi. Yuqoridagi xabarni skrinshot qiling.
  pause & exit /b 1
)

if not exist .env copy .env.example .env >nul
if not exist uzilmas.db (
  echo [2/3] Demo ma'lumotlar yaratilmoqda...
  python -m app.seed
)

echo.
echo [3/3] Uzilmas ishga tushdi:  http://127.0.0.1:8000
echo       Telefondan: ipconfig dagi IPv4 manzil + :8000/nurse
echo       To'xtatish: Ctrl+C
echo.
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo Server to'xtadi.
pause
