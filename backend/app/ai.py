"""
Uzilmas AI funksiyalari (Gemini). Har biri internet / kalit bölmasa ham işlaydi (qoidalar zaxirasi).

  1. intake()      — Qabulxona: erkin matn/ovoz -> bemor kartasi (ism, yoş, telefon, tuman, muddat, bosim, şikoyat).
  2. triage()      — Bemor savoli: xavf belgilarini aniqlaydi (QOIDALAR — har doim), javobni AI yozadi.
                     Xavf topilsa -> taşrif sifatida saqlanadi -> qoidalar zonani beradi -> şifokorga signal.
  3. summary()     — Şifokor uçun bir tugmada xulosa: nima özgardi, nimani tekşiriş kerak.
  4. noshow_risk() — "Jim qoliş xavfi": bemor kelmay qolişi / yöqolib qolişi ehtimoli (0–100) va sabablari.

Xavfsizlik: AI zonani PASAYTIRA OLMAYDI. Xavf belgisi kalit sözlar böyiça aniqlanadi (deterministik),
AI faqat qöşimça belgi topişi mumkin. Tahşis qöyilmaydi — yakuniy qaror şifokorda.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Optional

import httpx

from .alphabet import to_new
from .extract import GEMINI_URL

# ---------------------------------------------------------------- Gemini
def _key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


async def _gemini(prompt: str, schema: Optional[dict] = None, temperature: float = 0.2,
                  feature: str = "other") -> Optional[str]:
    from .usage import record
    if not _key():
        record(feature, "rules")
        return None
    cfg: dict = {"temperature": temperature}
    if schema:
        cfg.update(responseMimeType="application/json", responseSchema=schema)
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(GEMINI_URL.format(model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")),
                             json=body, headers={"x-goog-api-key": _key()})
        if r.status_code != 200:
            record(feature, "rules", ok=False)
            return None
        data = r.json()
        record(feature, "gemini", data)
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        record(feature, "rules", ok=False)
        return None


def _norm(text: str) -> str:
    return to_new(text or "").lower().replace("ʻ", "'").replace("’", "'").replace("‘", "'")


# ---------------------------------------------------------------- 2. Xavf belgilari (deterministik)
DANGER_WORDS = {
    "severe_headache": ["boş oğri", "boşim oğri", "boşim qattiq oğri", "kallam oğri", "головн", "голова бол", "болит голова"],
    "blurred_vision": ["köz xira", "közim xira", "közlarim xira", "köriş xira", "közim tinmay", "в глазах", "зрени", "мушки"],
    "vaginal_bleeding": ["qon ket", "qon kel", "qonli", "кровотеч", "кровян", "кровь ид", "идет кровь", "идёт кровь"],
    "convulsions": ["tutqanoq", "tiriş", "talvasa", "судорог"],
    "reduced_fetal_movement": ["qimirlamay", "kam qimirla", "qimirlaşi kam", "tepmay", "harakati kam", "harakat qilmay",
                               "не шевел", "мало шевел", "перестал шевел", "шевелится мало", "шевелится слаб"],
    "severe_abdominal_pain": ["qorin oğri", "qornim oğri", "qorinda oğri", "qorinda kuçli", "живот бол", "боль в живот",
                              "боли в живот", "болит живот"],
    "high_fever": ["isitma", "haroratim", "harorat 38", "harorat 39", "температур", "жар "],
}
NEGATIONS = ["yöq", "emas", "нет", "не было"]


def detect_danger(text: str) -> list[str]:
    t = _norm(text) + " "
    found = []
    for sign, words in DANGER_WORDS.items():
        for w in words:
            i = t.find(w)
            if i < 0:
                continue
            tail = t[i:i + len(w) + 14]
            rest = t[i + len(w):]
            if sign != "reduced_fetal_movement" and (any(f" {n}" in tail for n in NEGATIONS)
                                                      or re.match(r"[a-zöğşç]{0,3}?(may|mag|mas)", rest)):
                continue          # "boşim oğrimayapti / oğriq yöq / qon ketmagan" — xavf emas
            found.append(sign)
            break
    return found


TRIAGE_PROMPT = """Sen O‘zbekistondagi xususiy klinikaning homilador ayollar uçun yordamçisisan (Uzilmas).
Bemor: {name}, {weeks} hafta, xavf zonasi: {zone}.
Bemor yozdi: "{text}"
Aniqlangan xavf belgilari (qoidalar): {danger}

QOIDALAR:
- Javobni {lang_name} tilida, 2–4 qisqa gapda, iliq va tuşunarli yoz.
- Tahşis qöyma, dori nomini va dozasini yozma.
- Agar xavf belgisi bölsa: "Şifokoringizga xabar yuborildi" deb ayt va holat yomonlaşsa 103 ga qöng‘iroq qilişni ayt.
- Xavf bölmasa: umumiy maslahat ber va keyingi vizitni eslat.
- Qöşimça xavf belgisi körsang, uni "extra_signs" ga yoz (faqat ruxsat etilganlar: {signs}).
"""
FALLBACK = {
    "uz": {"danger": "Siz yozgan belgilar xavfli bölişi mumkin. Şifokoringizga darhol signal yuborildi — u siz bilan bog‘lanadi. "
                     "Holat yomonlaşsa, kutmang: 103 ga qöng‘iroq qiling.",
           "ok": "Rahmat, xabaringiz qabul qilindi. Xavfli belgi aniqlanmadi. Bosimni kuniga bir marta ölçab yozib boring, "
                 "suv içing va dam oling. Keyingi vizitni ötkazib yubormang — u sizning va bolangiz xavfsizligi uçun."},
    "ru": {"danger": "Описанные признаки могут быть опасными. Вашему врачу отправлен сигнал — он свяжется с вами. "
                     "Если станет хуже, не ждите: звоните 103.",
           "ok": "Спасибо, сообщение получено. Опасных признаков не обнаружено. Измеряйте давление раз в день, пейте воду "
                 "и отдыхайте. Не пропускайте следующий визит — это важно для вас и малыша."},
}


async def triage(text: str, patient: dict, zone: str, weeks, signs: dict, lang: str = "uz") -> dict:
    danger = detect_danger(text)
    reply, source = None, "rules"
    schema = {"type": "OBJECT", "properties": {"reply": {"type": "STRING"},
                                               "extra_signs": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(signs)}}},
              "required": ["reply"]}
    raw = await _gemini(TRIAGE_PROMPT.format(
        name=patient.get("full_name"), weeks=weeks or "?", zone=zone, text=text.replace('"', "'"),
        danger=", ".join(signs[s] for s in danger) or "yöq", signs=", ".join(signs),
        lang_name="rus" if lang == "ru" else "özbek (lotin)"), schema, 0.3, "triage")
    if raw:
        try:
            d = json.loads(raw)
            reply = d.get("reply")
            danger += [s for s in d.get("extra_signs", []) if s in signs and s not in danger]   # AI faqat QÖŞA oladi
            source = "gemini"
        except ValueError:
            reply = None
    if not reply:
        reply = FALLBACK[lang]["danger" if danger else "ok"]
    elif lang != "ru":
        reply = to_new(reply)
    return {"danger": danger, "reply": reply, "source": source}


# ---------------------------------------------------------------- 1. Qabulxona AI yordamçisi
PHONE = re.compile(r"(\+?998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b9\d[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b)")
AGE = re.compile(r"(\d{2})\s*(?:yoş|yosh|ёш|лет|год|y\.)")
WEEKS = re.compile(r"(\d{1,2})\s*(?:-?\s*)(?:hafta|недел|нед)")
BP = re.compile(r"(\d{2,3})\s*(?:/|ga|на|\\)\s*(\d{2,3})")
NAME = re.compile(r"(?:ismi|ism|фио|имя|bemor)[:\s]+([A-ZА-ЯЁÖĞŞÇOʻ‘'][\wʻ‘'’-]+(?:\s+[A-ZА-ЯЁÖĞŞÇ][\wʻ‘'’-]+)?)", re.I)
PREMIUM_WORDS = ["pullik", "premium", "platn", "платн", "премиум", "paket", "пакет"]

INTAKE_PROMPT = """Qabulxona xodimi yangi homilador bemor haqida erkin matn aytdi/yozdi. Undan maydonlarni ajrat.
Matn: "{text}"
Tumanlar (faqat şulardan biri): {districts}
Qoida: faqat matnda aniq aytilganini yoz, taxmin qilma (bölmasa null). Ism-familiyani lotin yozuvida yoz.
complaint — bemor şikoyatini 1 qisqa gapda. plan — "premium" agar pullik/premium paket aytilgan bölsa, aks holda "bepul".
"""


async def intake(text: str, districts: list[str], signs: dict) -> dict:
    """Erkin matn -> forma. Avval Gemini, bölmasa qoidalar. Qiymatlar formada körsatiladi — xodim tasdiqlaydi."""
    from .voice import parse_text
    vit = await parse_text(text, signs)               # bosim, gemoglobin, muddat, belgilar (Gemini yoki regex)
    vals = {k: v for k, v in vit["values"].items() if v is not None}
    out = {"full_name": None, "age": None, "phone": None, "district": None, "ga_weeks": vals.get("ga_weeks"),
           "sbp": vals.get("sbp"), "dbp": vals.get("dbp"), "hb_g_l": vals.get("hb_g_l"),
           "complaint": None, "plan": "bepul", "symptoms": vit.get("symptoms", []), "source": vit.get("parser", "rules")}
    schema = {"type": "OBJECT", "properties": {
        "full_name": {"type": "STRING", "nullable": True}, "age": {"type": "INTEGER", "nullable": True},
        "phone": {"type": "STRING", "nullable": True}, "district": {"type": "STRING", "nullable": True, "enum": districts},
        "ga_weeks": {"type": "NUMBER", "nullable": True}, "complaint": {"type": "STRING", "nullable": True},
        "plan": {"type": "STRING", "enum": ["bepul", "premium"]}}}
    raw = await _gemini(INTAKE_PROMPT.format(text=text.replace('"', "'"), districts=", ".join(districts)), schema, 0, "intake")
    got = {}
    if raw:
        try:
            got = json.loads(raw)
            out["source"] = "gemini"
        except ValueError:
            got = {}
    t = _norm(text)
    if not got.get("phone"):
        m = PHONE.search(text)
        got["phone"] = m.group(1) if m else None
    if not got.get("age"):
        m = AGE.search(t)
        got["age"] = int(m.group(1)) if m else None
    if not got.get("ga_weeks"):
        m = WEEKS.search(t)
        got["ga_weeks"] = float(m.group(1)) if m else None
    if not got.get("district"):
        for d in districts:
            if _norm(d).split()[0][:6] in t:
                got["district"] = d
                break
    if not got.get("full_name"):
        m = NAME.search(text)
        if m:
            got["full_name"] = m.group(1)
        else:      # birinçi ikkita bosh harfli söz
            caps = re.findall(r"\b([A-ZÖĞŞÇ][a-zöğşç'ʻ‘’]+)\b", to_new(text))
            stop = {"Bemor", "Ismi", "Tuman", "Telefon", "Bosim", "Boşim", "Premium", "Pullik", "Bepul"}
            caps = [c for c in caps if c not in stop and _norm(c) not in [_norm(d) for d in districts]]
            got["full_name"] = " ".join(caps[:2]) if len(caps) >= 2 else None
    if not out["sbp"]:
        m = BP.search(t)
        if m and 70 <= int(m.group(1)) <= 250:
            out["sbp"], out["dbp"] = int(m.group(1)), int(m.group(2))
    if got.get("plan") != "premium" and any(w in t for w in PREMIUM_WORDS):
        got["plan"] = "premium"
    out.update({k: v for k, v in got.items() if v not in (None, "")})
    if out["full_name"]:
        out["full_name"] = to_new(out["full_name"]).strip().title()
    out["symptoms"] = sorted(set(out["symptoms"]) | set(detect_danger(text)))
    if not out.get("complaint"):
        out["complaint"] = text.strip()[:160]
    return out


# ---------------------------------------------------------------- 3. Şifokor uçun xulosa
SUMMARY_PROMPT = """Sen akuşer-ginekolog uçun yordamçisan. Quyidagi bemor ma'lumotidan {lang_name} tilida qisqa klinik xulosa yoz.
Format (4–6 qator, har biri "• " bilan): holat va zona sababi; dinamika (nima özgardi); xavf omillari;
vizitda nimani tekşiriş kerak; zanjirdagi muammo (bölsa). Tahşis qöyma, dori yozma, faqat berilgan ma'lumotdan foydalan.
Ma'lumot (JSON): {data}
"""


async def summary(data: dict, lang: str = "uz") -> dict:
    raw = await _gemini(SUMMARY_PROMPT.format(lang_name="rus" if lang == "ru" else "özbek (lotin)",
                                              data=json.dumps(data, ensure_ascii=False, default=str)[:6000]), None, 0.2, "summary")
    if raw:
        return {"text": raw.strip() if lang == "ru" else to_new(raw.strip()), "source": "gemini"}
    return {"text": _summary_rules(data, lang), "source": "rules"}


def _trend(vs: list, key: str) -> Optional[str]:
    vals = [v.get(key) for v in vs if v.get(key) is not None]
    if len(vals) < 2:
        return None
    return f"{vals[-2]:g} → {vals[-1]:g}"


def _summary_rules(d: dict, lang: str) -> str:
    ru = lang == "ru"
    vs, a, ch = d["visits"], d["assessment"], d["chain"]
    lines = []
    z = {"red": ("QIZIL", "КРАСНАЯ"), "yellow": ("SARIQ", "ЖЁЛТАЯ"), "green": ("YAŞIL", "ЗЕЛЁНАЯ")}[a["zone"]][1 if ru else 0]
    lines.append(("• Зона: " if ru else "• Zona: ") + z + " — " + a["summary"])
    tr = [f"{lbl} {x}" for lbl, x in ((("АД" if ru else "Bosim"), _trend(vs, "sbp")), ("Hb", _trend(vs, "hb_g_l")),
                                      (("Белок" if ru else "Oqsil"), _trend(vs, "protein_g_l"))) if x]
    if tr:
        lines.append(("• Динамика: " if ru else "• Dinamika: ") + "; ".join(tr))
    p = d["patient"]
    risks = []
    if p.get("age") and (p["age"] < 18 or p["age"] >= 35):
        risks.append(("возраст " if ru else "yoş ") + str(p["age"]))
    if p.get("prev_preeclampsia"):
        risks.append("в анамнезе преэклампсия" if ru else "oldin preeklampsiya bölgan")
    if p.get("multiple_pregnancy"):
        risks.append("многоплодная" if ru else "köp homilali")
    if risks:
        lines.append(("• Факторы риска: " if ru else "• Xavf omillari: ") + ", ".join(risks))
    checks = {"red": ("АД повторно через 15 мин, белок в моче, головная боль/зрение, решить вопрос госпитализации",
                      "15 daqiqadan keyin bosimni qayta ölçaş, siydikda oqsil, boş oğriği/köriş, statsionar masalasi"),
              "yellow": ("контроль АД и Hb, повторный анализ через 7–14 дней",
                         "bosim va gemoglobin nazorati, 7–14 kunda qayta tahlil"),
              "green": ("плановый визит, витамины по протоколу", "rejali vizit, protokol böyiça vitaminlar")}[a["zone"]]
    lines.append(("• Проверить на визите: " if ru else "• Vizitda tekşiring: ") + checks[0 if ru else 1])
    if ch["status"] != "ok":
        lines.append(("• Цепочка: " if ru else "• Zanjir: ") + f"{ch['break_at']} — {ch['reason']}")
    r = d.get("risk")
    if r and r["score"] >= 50:
        lines.append((f"• Риск неявки {r['score']}%: " if ru else f"• Kelmay qoliş xavfi {r['score']}%: ") + "; ".join(r["reasons"][:2]))
    return "\n".join(lines)


# ---------------------------------------------------------------- 4. Jim qoliş xavfi
def noshow_risk(p: dict, visits: list, appts: list, msgs: list, zone: str, chain_status: str,
                interval_days: int, lang: str = "uz") -> dict:
    """Ayol kelmay qolişi / aloqadan yöqolişi ehtimoli (0–100). Har bir ball — tuşuntirilgan sabab.
    Hozir: oçiq vaznli model (pilot ma'lumotlari bilan ML ga almaştiriladi)."""
    ru = lang == "ru"
    score, why = 10, []

    def add(n, uz, rus):
        nonlocal score
        score += n
        why.append(rus if ru else uz)
    today = date.today()
    last = max((v["date"] for v in visits), default=None)
    if last:
        days = (today - date.fromisoformat(last[:10])).days
        if days > interval_days:
            add(30, f"oxirgi taşrifdan {days} kun ötdi (me'yor {interval_days})", f"с последнего визита {days} дн. (норма {interval_days})")
        elif days > interval_days - 3:
            add(10, "taşrif muddati yaqinlaşdi", "срок визита подходит")
    ns = sum(1 for a in appts if a.get("status") == "no_show")
    if ns:
        add(25 * ns, f"{ns} marta vizitga kelmagan", f"{ns} раз(а) не пришла на визит")
    if (p.get("plan") or "bepul") == "premium" and any((a.get("prepaid") or 0) > 0 for a in appts):
        add(-15, "oldindan tölangan (premium)", "предоплата внесена (премиум)")
    else:
        add(10, "oldindan tölov yöq", "нет предоплаты")
    if not msgs:
        add(10, "bemor ilovaga heç yozmagan", "пациентка ни разу не писала в приложение")
    else:
        lastm = max(m["created_at"] for m in msgs)
        if (datetime.now() - datetime.fromisoformat(lastm[:19])).days > 14:
            add(10, "2 haftadan beri aloqa yöq", "нет связи больше 2 недель")
    if p.get("age") and p["age"] < 20:
        add(10, "yoş ayol (20 dan kiçik)", "молодой возраст (до 20)")
    if chain_status == "broken":
        add(15, "zanjir uzilgan", "цепочка прервана")
    if zone == "red":
        add(5, "qizil zona — e'tibor kuçaytirilsin", "красная зона — усилить внимание")
    score = max(0, min(100, score))
    level = "high" if score >= 60 else "mid" if score >= 35 else "low"
    return {"score": score, "level": level, "reasons": why}
