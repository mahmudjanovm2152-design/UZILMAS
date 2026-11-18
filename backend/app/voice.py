"""
Ovozli kiritiş (№10): hamşira özbekça gapiradi -> matn -> körsatkiçlar.

  1. Nutq -> matn: Aisha STT (özbek tili uçun), kalit bölmasa — Gemini audio.
  2. Matn -> körsatkiçlar: Gemini (JSON), zaxira sifatida oddiy qoidalar (regex).
  3. Natija extract.postprocess orqali ötadi: şubhali qiymat -> None.

Misol: "bosim yuz ellik ikki ga töqson sakkiz, gemoglobin yuz ön ikki, siydikda oqsil nol butun olti"
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Optional

import httpx

from .alphabet import to_new
from .extract import FIELDS, GEMINI_URL, postprocess

AISHA_URL = "https://back.aisha.group/api/v1/stt/post/"

TEXT_PROMPT = """Hamşira homilador ayolni körikdan ötkazib, natijalarni ovoz bilan aytdi (özbek yoki rus tilida,
raqamlar söz bilan bölişi mumkin). Matndan FAQAT aytilgan körsatkiçlarni ol:
{fields}
Şuningdek xavfli belgilar (symptoms) röyxati: {signs}
Aytilmagan körsatkiç -> value = null. Taxmin qilma. confidence (0..1) ber.
Matn: \"\"\"{text}\"\"\""""

NUM_WORDS = {"nol": 0, "bir": 1, "ikki": 2, "uç": 3, "tört": 4, "tort": 4, "beş": 5, "olti": 6,
             "yetti": 7, "sakkiz": 8, "töqqiz": 9, "toqqiz": 9, "ön": 10, "on": 10, "yigirma": 20,
             "öttiz": 30, "ottiz": 30, "qirq": 40, "ellik": 50, "oltmiş": 60, "yetmiş": 70,
             "sakson": 80, "töqson": 90, "tokson": 90, "yuz": 100}


def words_to_numbers(text: str) -> str:
    """'yuz ellik ikki' -> '152', 'nol butun olti' -> '0.6' (oddiy özbekça sonlar)."""
    t = to_new(text).lower()   # amaldagi va yangi alifbo — ikkalasi ham qabul qilinadi
    tokens = re.findall(r"[a-zşçğöа-яё']+|\d+[.,]?\d*|\S", t)
    out, cur, have = [], 0, False

    def flush():
        nonlocal cur, have
        if have:
            out.append(str(cur))
        cur, have = 0, False

    i = 0
    while i < len(tokens):
        w = tokens[i]
        if w in NUM_WORDS:
            n = NUM_WORDS[w]
            if n == 100:
                cur = (cur or 1) * 100
            else:
                cur += n
            have = True
        elif w == "butun" and have:
            whole = cur
            cur, have = 0, False
            j, frac = i + 1, ""
            while j < len(tokens) and tokens[j] in NUM_WORDS and NUM_WORDS[tokens[j]] < 10:
                frac += str(NUM_WORDS[tokens[j]])
                j += 1
            out.append(f"{whole}.{frac or 0}")
            i = j
            continue
        else:
            flush()
            out.append(w)
        i += 1
    flush()
    return " ".join(out)


def regex_parse(text: str) -> dict:
    """Zaxira: Gemini işlamasa ham asosiy raqamlarni topadi."""
    t = words_to_numbers(text).replace(",", ".")
    vals: dict = {}

    def conf(v):
        return {"value": v, "confidence": 0.8}

    m = re.search(r"(?:bosim|давлени\w*|ad)\D{0,15}?(\d{2,3})\s*(?:ga|/|на|на\s)\s*(\d{2,3})", t)
    if m:
        vals["sbp"], vals["dbp"] = conf(int(m.group(1))), conf(int(m.group(2)))
    for key, pat in [("hb_g_l", r"(?:gemoglobin|гемоглобин|hb)\D{0,10}?(\d{2,3}(?:\.\d)?)"),
                     ("glucose_fasting", r"(?:glyukoza|qand|глюкоз\w*|сахар)\D{0,10}?(\d{1,2}(?:\.\d)?)"),
                     ("protein_g_l", r"(?:oqsil|белок)\D{0,10}?(\d(?:\.\d+)?)"),
                     ("ga_weeks", r"(\d{1,2})\s*(?:hafta|недел\w*)")]:
        m = re.search(pat, t)
        if m:
            vals[key] = conf(float(m.group(1)))
    symptoms = []
    for sign, words in {"severe_headache": ["boş oğr", "головн"], "blurred_vision": ["köz", "xiralaş", "зрени"],
                        "vaginal_bleeding": ["qon ket", "кровотеч"], "reduced_fetal_movement": ["harakat kam", "шевел"]
                        }.items():
        if any(w in t for w in words):
            symptoms.append(sign)
    return {"values": vals, "symptoms": symptoms}


async def transcribe(audio: bytes, mime: str) -> tuple[str, str]:
    """(matn, manba). Aisha -> Gemini."""
    key = os.environ.get("AISHA_API_KEY", "").strip()
    if key:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(AISHA_URL, headers={"X-Api-Key": key},
                             files={"audio": ("voice.webm", audio, mime)}, data={"language": "uz"})
        if r.status_code < 300:
            d = r.json()
            text = next((d[k] for k in ("transcript", "text", "result") if isinstance(d.get(k), str)), None)
            if text:
                return text, "aisha"
    gkey = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gkey:
        raise RuntimeError("AISHA_API_KEY yoki GEMINI_API_KEY kerak")
    body = {"contents": [{"parts": [
        {"text": "Bu audioni sözma-söz matnga aylantir (özbek yoki rus tili). Faqat matnni qaytar."},
        {"inline_data": {"mime_type": mime.split(";")[0], "data": base64.b64encode(audio).decode()}}]}],
        "generationConfig": {"temperature": 0}}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(GEMINI_URL.format(model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")),
                         json=body, headers={"x-goog-api-key": gkey})
    if r.status_code != 200:
        raise RuntimeError(f"Nutqni tanib bölmadi: {r.status_code}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), "gemini"


async def parse_text(text: str, signs: dict) -> dict:
    """Matn -> körsatkiçlar. Gemini bölmasa yoki xato bersa — regex."""
    gkey = os.environ.get("GEMINI_API_KEY", "").strip()
    parsed: Optional[dict] = None
    if gkey:
        item = {"type": "OBJECT", "properties": {"value": {"type": "NUMBER", "nullable": True},
                                                 "confidence": {"type": "NUMBER"}}}
        schema = {"type": "OBJECT", "properties": {
            "values": {"type": "OBJECT", "properties": {k: item for k in FIELDS}},
            "symptoms": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(signs)}}}}
        body = {"contents": [{"parts": [{"text": TEXT_PROMPT.format(
            fields="\n".join(f"- {k}: {v[0]}" for k, v in FIELDS.items()),
            signs=", ".join(f"{k} ({v})" for k, v in signs.items()), text=text)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseSchema": schema}}
        try:
            async with httpx.AsyncClient(timeout=40) as c:
                r = await c.post(GEMINI_URL.format(model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")),
                                 json=body, headers={"x-goog-api-key": gkey})
            if r.status_code == 200:
                parsed = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
            parsed = None
    source = "gemini"
    if not parsed:
        parsed, source = regex_parse(text), "rules"
    out = postprocess(parsed)
    out["symptoms"] = [s for s in parsed.get("symptoms", []) if s in signs]
    out["parser"] = source
    return out
