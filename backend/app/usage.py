"""
AI sarfi hisobi: har bir so‘rov — qaysi funksiya, nechta token (kiriş / çiqiş / fikrlaş), narxi.

Narx (Gemini 2.5 Flash, Google AI Studio, pullik tarif): kiriş $0.30, çiqiş $2.50 — 1 mln token uçun.
Fikrlaş (thinking) tokenlari çiqiş narxida hisoblanadi. .env orqali özgartiriş mumkin:
  AI_PRICE_IN_USD=0.30   AI_PRICE_OUT_USD=2.50   USD_UZS=12000
"""
from __future__ import annotations

import os
from typing import Optional

from .db import session

FEATURES = {
    "intake": ("Qabulxona AI yordamçisi", "AI-помощник приёмной"),
    "triage": ("Bemor savoli (triaj)", "Вопрос пациентки (триаж)"),
    "summary": ("Şifokor uçun xulosa", "Сводка для врача"),
    "vision": ("Tahlil rasmini öqiş", "Чтение фото анализа"),
    "stt": ("Ovozni matnga", "Голос в текст"),
    "parse": ("Matndan körsatkiçlar", "Показатели из текста"),
}


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def prices() -> dict:
    return {"in_usd": _f("AI_PRICE_IN_USD", 0.30), "out_usd": _f("AI_PRICE_OUT_USD", 2.50),
            "usd_uzs": _f("USD_UZS", 12000), "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")}


def record(feature: str, source: str, response: Optional[dict] = None, ok: bool = True) -> None:
    """source: gemini | rules. response — Gemini javobi (usageMetadata öqiladi)."""
    um = (response or {}).get("usageMetadata") or {}
    pin = int(um.get("promptTokenCount") or 0)
    out = int(um.get("candidatesTokenCount") or 0)
    think = int(um.get("thoughtsTokenCount") or 0)
    p = prices()
    cost = (pin * p["in_usd"] + (out + think) * p["out_usd"]) / 1_000_000
    try:
        with session() as c:
            c.execute("""INSERT INTO ai_usage (feature, source, model, tokens_in, tokens_out, tokens_think, cost_usd, ok)
                         VALUES (?,?,?,?,?,?,?,?)""", (feature, source, p["model"] if source == "gemini" else "-",
                                                      pin, out, think, cost, int(ok)))
    except Exception:       # hisob yozilmasa ham asosiy funksiya işlayversin
        pass
