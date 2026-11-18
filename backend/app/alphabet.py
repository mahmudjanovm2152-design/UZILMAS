"""
Yangi o‘zbek lotin alifbosi (O‘RQ–1184, 21.10.2026; kuchga kirishi — 22.04.2027):
  O‘ o‘ → Ö ö,  G‘ g‘ → Ğ ğ,  Sh sh → Ş ş,  Ch ch → Ç ç.  Tutuq belgisi (’) saqlanadi.

to_new() — amaldagi lotin yozuvidagi matnni yangi alifboga o‘giradi.
Ovozli kiritish (STT) va hamshira yozgan matn ikkala yozuvda kelishi mumkin — avval shu funksiya bilan normallashtiriladi.
"""
from __future__ import annotations

import re

_APOS = "'‘ʻ’`"
_OG = re.compile(rf"([OoGg])[{_APOS}](?=[A-Za-zÀ-ž])")
_WORD = re.compile(r"[A-Za-zÀ-ž]+")

# Kod va xalqaro atamalar — o‘girilmaydi
KEEP = {
    "chain", "chains", "shadow", "catch", "discharged", "discharge", "ch", "foreach", "check", "checkc", "checked",
    "checkbox", "sh", "stylesheet", "flash", "fetchone", "fetch", "choice", "chat", "search", "match", "dashboard",
    "schema", "responseschema", "anchor", "lastchain", "refresh", "fresh", "chart", "aisha", "show", "showpreview",
    "showguide", "showlist", "shown", "short", "share", "push", "headache", "chunks", "charset", "flush", "unshift",
    "trackchains", "shift", "shield", "shade", "onchange", "chip", "child", "children", "chev", "changed", "change",
    "appendchild", "dash", "dasharray", "dischargein", "chainleft", "chainpill", "chainhtml", "chainbanner", "chrome",
    "chromium", "cache", "caches", "touch", "scheme", "english", "speech", "machine", "fetchall", "approach", "each",
    "which", "such", "much", "attach", "branch", "batch", "launch", "reach", "watch", "switch", "finish", "publish",
    "bash", "hash", "crash", "cash", "ship", "shell", "shape", "sha", "chunk", "chars", "char", "cached", "techn", "pitch", "chcp", "echo", "mismatch", "monkeypatch",
}

_MAP = {"sh": "ş", "Sh": "Ş", "SH": "Ş", "sH": "ş", "ch": "ç", "Ch": "Ç", "CH": "Ç", "cH": "ç"}


def _og(m: re.Match) -> str:
    return {"O": "Ö", "o": "ö", "G": "Ğ", "g": "ğ"}[m.group(1)]


def _word(m: re.Match) -> str:
    w = m.group(0)
    if w.lower() in KEEP:
        return w
    return re.sub(r"[sScC][hH]", lambda x: _MAP[x.group(0)], w)


def to_new(text: str) -> str:
    if not text:
        return text
    text = _OG.sub(_og, text)
    return _WORD.sub(_word, text)


def to_old(text: str) -> str:
    """Teskari: yangi alifbodan amaldagi lotinga (eski STT/qidiruv bilan moslik uchun)."""
    return (text.replace("Ö", "O‘").replace("ö", "o‘").replace("Ğ", "G‘").replace("ğ", "g‘")
            .replace("Ş", "Sh").replace("ş", "sh").replace("Ç", "Ch").replace("ç", "ch"))
