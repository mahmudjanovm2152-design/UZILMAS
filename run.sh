#!/usr/bin/env bash
# Uzilmas — bitta buyruq bilan ishga tushirish (Mac/Linux)
set -e
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
[ -f uzilmas.db ] || python -m app.seed
echo ""
echo "  Uzilmas ishga tushdi:  http://127.0.0.1:8000"
echo "  Telefondan ochish:      http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}'):8000/nurse"
echo ""
uvicorn app.main:app --host 0.0.0.0 --port 8000
