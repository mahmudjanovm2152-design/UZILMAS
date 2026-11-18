"""
Tahlil blankasi rasmidan körsatkiçlarni öqiş (Gemini Vision).

Xavfsizlik tamoyillari:
  1. AI faqat ÖQIYDI. Zonani rules.py belgilaydi.
  2. Işonç past yoki qiymat mantiqsiz bölsa -> qiymat None ("tekşiriş kerak"),
     heç qaçon taxmin qilinmaydi va "norma" deb yozilmaydi.
  3. Natija avval hamşiraga körsatiladi, u tasdiqlagandan keyin saqlanadi.

Sozlaş (.env):
  GEMINI_API_KEY=...
  GEMINI_MODEL=gemini-2.5-flash
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MIN_CONFIDENCE = 0.7

FIELDS = {
    # nom: (izoh, ruxsat etilgan oraliq — mantiqiy tekşiruv uçun)
    "hb_g_l":          ("Gemoglobin, g/l (HGB, Hb)", (30, 200)),
    "glucose_fasting": ("Oç qoringa glyukoza, mmol/l (GLU, qand)", (1.5, 35)),
    "protein_g_l":     ("Siydikda oqsil, g/l (Белок, Protein, oqsil)", (0, 20)),
    "sbp":             ("Arterial bosim — sistolik (yuqori raqam), mm sim. ust.", (60, 250)),
    "dbp":             ("Arterial bosim — diastolik (pastki raqam), mm sim. ust.", (30, 160)),
    "ga_weeks":        ("Homiladorlik muddati, hafta", (4, 43)),
}

PROMPT = """Sen tibbiy laboratoriya blankalarini raqamlaştiruvçi yordamçisan.
Rasmdagi blankadan FAQAT quyidagi körsatkiçlarni öqi (blanka özbek yoki rus tilida bölişi mumkin):
{fields}

QAT'IY QOIDALAR:
- Faqat rasmda aniq yozilgan raqamni ol. Taxmin qilma, hisoblama, töldirma.
- Agar körsatkiç rasmda yöq, öçgan yoki öqib bölmasa: value = null.
- Har bir körsatkiç uçun confidence (0..1) ber: raqamni qançalik aniq öqiganing.
- unit maydoniga blankadagi ölçov birligini yoz (masalan "g/l", "g/dl", "mmol/l", "mg/dl").
- raw maydoniga blankadagi asl yozuvni yoz (masalan "HGB 98").
- "отр.", "отрицательно", "abs", "yöq", "manfiy", "-" kabi yozuvlar oqsil uçun 0 degani (value = 0).
- Bemorning ism-familiyasini va tahlil sanasini ham öqi (bölmasa null).
"""


def _schema() -> dict:
    item = {"type": "OBJECT", "properties": {
        "value": {"type": "NUMBER", "nullable": True},
        "unit": {"type": "STRING", "nullable": True},
        "raw": {"type": "STRING", "nullable": True},
        "confidence": {"type": "NUMBER"},
    }, "required": ["value", "confidence"]}
    return {"type": "OBJECT", "properties": {
        "patient_name": {"type": "STRING", "nullable": True},
        "test_date": {"type": "STRING", "nullable": True},
        "values": {"type": "OBJECT", "properties": {k: item for k in FIELDS}},
    }, "required": ["values"]}


def _normalize(name: str, value: float, unit: Optional[str]) -> float:
    """Birliklarni tizim birligiga keltiriş."""
    u = (unit or "").lower().replace(" ", "")
    if name == "hb_g_l" and (u in ("g/dl", "г/дл") or value < 25):
        return round(value * 10, 1)            # g/dl -> g/l
    if name == "glucose_fasting" and (u in ("mg/dl", "мг/дл") or value > 40):
        return round(value / 18.0, 1)          # mg/dl -> mmol/l
    if name == "protein_g_l" and u in ("mg/l", "мг/л"):
        return round(value / 1000.0, 3)        # mg/l -> g/l
    return value


def postprocess(raw: dict[str, Any]) -> dict:
    """Gemini javobini tekşiradi: birlik, oraliq, işonç. Şubhali qiymat -> None."""
    values: dict[str, Optional[float]] = {}
    warnings: list[str] = []
    details: dict[str, dict] = {}
    got = (raw or {}).get("values") or {}
    for name, (label, (lo, hi)) in FIELDS.items():
        item = got.get(name) or {}
        val, conf = item.get("value"), float(item.get("confidence") or 0)
        details[name] = {"raw": item.get("raw"), "unit": item.get("unit"), "confidence": conf}
        if val is None:
            values[name] = None
            continue
        try:
            val = _normalize(name, float(val), item.get("unit"))
        except (TypeError, ValueError):
            values[name] = None
            warnings.append(f"{label}: raqam öqilmadi — qölda tekşiring")
            continue
        if conf < MIN_CONFIDENCE:
            values[name] = None
            warnings.append(f"{label}: AI işonçi past ({conf:.0%}) — qölda tekşiring")
        elif not (lo <= val <= hi):
            values[name] = None
            warnings.append(f"{label}: {val} mantiqsiz qiymat — qölda tekşiring")
        else:
            values[name] = int(val) if name in ("sbp", "dbp") else val
    return {
        "values": values,
        "warnings": warnings,
        "details": details,
        "patient_name": (raw or {}).get("patient_name"),
        "test_date": (raw or {}).get("test_date"),
        "note": "AI faqat öqidi. Saqlaşdan oldin hamşira tasdiqlaşi şart.",
    }


async def extract_from_image(image: bytes, mime: str = "image/jpeg",
                             client: Optional[httpx.AsyncClient] = None) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY topilmadi (.env faylini tekşiring)")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    fields_txt = "\n".join(f"- {k}: {label}" for k, (label, _) in FIELDS.items())
    body = {
        "contents": [{"parts": [
            {"text": PROMPT.format(fields=fields_txt)},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": _schema()},
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=60)
    try:
        r = await client.post(GEMINI_URL.format(model=model), json=body,
                              headers={"x-goog-api-key": key})
        if r.status_code != 200:
            raise RuntimeError(f"Gemini xatosi {r.status_code}: {r.text[:200]}")
        data = r.json()
        from .usage import record
        record("vision", "gemini", data)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Gemini bilan aloqa yöq: {e}") from e
    finally:
        if own:
            await client.aclose()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Gemini javobini öqib bölmadi: {e}") from e
    return postprocess(parsed)
