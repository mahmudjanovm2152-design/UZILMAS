"""
Uzilmas API.

Işga tuşiriş (backend/ papkasidan):
    python -m app.seed                          # sintetik ma'lumotlar
    uvicorn app.main:app --host 0.0.0.0         # http://127.0.0.1:8000
Sahifalar:  /  (rollar)   /dashboard  (№9)   /nurse  (№10)   /doctor  (№11)   /docs  (API)
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import chain, notify, rules
from .alphabet import to_new
from .config import load_env, save_user_env
from .db import init_db, row_to_visit_dict, session
from .extract import extract_from_image
from .voice import parse_text, transcribe

load_env()
STATIC = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app):
    init_db()
    stop = asyncio.Event()
    BG["stop"] = stop
    await notify.startup_report()
    tasks = [asyncio.create_task(notify.escalation_loop(stop))]
    _start_polling()
    yield
    stop.set()
    for t in tasks + ([BG["poll"]] if BG.get("poll") else []):
        t.cancel()


BG: dict = {}


def _start_polling() -> None:
    """Telegram tinglaşni (qayta) işga tuşiradi — /setup da token kiritilganda ham."""
    if not notify._env("TELEGRAM_BOT_TOKEN") or "stop" not in BG:
        return
    if BG.get("poll") and not BG["poll"].done():
        BG["poll"].cancel()
    BG["poll"] = asyncio.create_task(notify.poll_telegram(BG["stop"]))


app = FastAPI(title="Uzilmas API", version="0.3.0", lifespan=lifespan,
              description="Homilador ayollarni xavf zonalari böyiça monitoring (№9), "
                          "hamşira offline kiritişi (№10), javob berilgandan keyin aktiv çaqiruv (№11)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- Modellar ----------
class VisitIn(BaseModel):
    date: str = Field(..., examples=["2026-11-18"])
    ga_weeks: Optional[float] = Field(None, ge=0, le=45)
    sbp: Optional[int] = Field(None, ge=50, le=260)
    dbp: Optional[int] = Field(None, ge=30, le=180)
    protein_g_l: Optional[float] = Field(None, ge=0, le=20)
    hb_g_l: Optional[float] = Field(None, ge=30, le=200)
    glucose_fasting: Optional[float] = Field(None, ge=1, le=40)
    symptoms: list[str] = []
    source: str = Field("manual", pattern="^(manual|photo|voice|offline)$")
    client_id: Optional[str] = None      # offline navbatdagi yozuv ID si (takrorlanmasligi uçun)


class DischargeIn(BaseModel):
    reason: str = Field("postpartum", max_length=200)
    notes: str = Field("", max_length=1000)


class AckIn(BaseModel):
    by: str = Field("Dashboard", max_length=80)


class TextIn(BaseModel):
    text: str = Field(..., max_length=2000)


# ---------- Yordamçi ----------
def _patient_obj(p) -> rules.Patient:
    return rules.Patient(age=p["age"], multiple_pregnancy=bool(p["multiple_pregnancy"]),
                         prev_preeclampsia=bool(p["prev_preeclampsia"]))


def _visit_obj(v: dict) -> rules.Visit:
    return rules.Visit(date=v["date"], ga_weeks=v.get("ga_weeks"), sbp=v.get("sbp"), dbp=v.get("dbp"),
                       protein_g_l=v.get("protein_g_l"), hb_g_l=v.get("hb_g_l"),
                       glucose_fasting=v.get("glucose_fasting"), symptoms=v.get("symptoms") or [])


def _load(c, pid: int):
    p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Bemor topilmadi")
    visits = [row_to_visit_dict(r) for r in
              c.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY date, id", (pid,))]
    a = rules.assess(_patient_obj(p), [_visit_obj(v) for v in visits])
    return dict(p), visits, a


REASONS = {"postpartum": ("Tuğruqdan keyin", "После родов")}


def reason_label(key: Optional[str], lang: str = "uz") -> str:
    if not key:
        return ""
    r = REASONS.get(key)
    return (r[1] if lang == "ru" else r[0]) if r else key


def _lang(lang: Optional[str]) -> str:
    return "ru" if lang == "ru" else "uz"


def _brief(p: dict, visits: list, a: rules.Assessment, alerts: Optional[list] = None, lang: str = "uz") -> dict:
    last = visits[-1] if visits else {}
    ch = chain.build(p, visits, a, alerts or [], lang=lang)
    return {
        "id": p["id"], "full_name": p["full_name"], "age": p["age"], "nurse": p["nurse"],
        "district": p["district"], "mahalla": p["mahalla"], "lat": p["lat"], "lon": p["lon"],
        "status": p["status"], "zone": a.zone, "summary": a.summary(lang),
        "trend_raised": a.trend_raised, "last_visit": last.get("date"), "ga_weeks": last.get("ga_weeks"),
        "chain_status": ch["status"], "chain_break": ch["break_at"], "chain_break_key": ch["break_key"],
        "chain_reason": ch["reason"],
    }


def _all_patients(zone: Optional[str] = None, district: Optional[str] = None,
                  nurse: Optional[str] = None, lang: str = "uz") -> list[dict]:
    out = []
    with session() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM patients ORDER BY id")]
        by_pid: dict[int, list] = {}
        for r in c.execute("SELECT * FROM alerts"):
            by_pid.setdefault(r["patient_id"], []).append(dict(r))
        for pid in ids:
            p, visits, a = _load(c, pid)
            if (zone and a.zone != zone) or (district and p["district"] != district) \
                    or (nurse and p["nurse"] != nurse):
                continue
            out.append(_brief(p, visits, a, by_pid.get(pid), lang))
    order = {"red": 0, "yellow": 1, "green": 2}
    corder = {"broken": 0, "wait": 1, "ok": 2}
    out.sort(key=lambda x: (corder[x["chain_status"]], order[x["zone"]], x["full_name"]))
    return out


# ---------- Bemorlar (№9) ----------
@app.get("/api/health")
def health():
    return {"ok": True, "rules_version": rules.RULES_VERSION,
            "telegram": bool(notify._env("TELEGRAM_BOT_TOKEN")),
            "gemini": bool(notify._env("GEMINI_API_KEY")), "aisha": bool(notify._env("AISHA_API_KEY"))}


class SetupIn(BaseModel):
    values: dict


def _local_only(request: Request) -> None:
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, "Sozlamalarni faqat server kompyuterining özidan özgartiriş mumkin")


@app.get("/api/setup/status")
async def setup_status(request: Request):
    _local_only(request)
    return await notify.status()


@app.post("/api/setup")
async def setup_save(body: SetupIn, request: Request):
    _local_only(request)
    path = save_user_env(body.values)
    _start_polling()
    if notify._env("TELEGRAM_BOT_TOKEN"):
        await notify.setup_bot()
    st = await notify.status()
    st["saved_to"] = str(path)
    return st


@app.get("/api/config")
def config():
    """Frontend uçun ommaviy sozlamalar (maxfiy kalitlar emas)."""
    return {"carto_key": notify._env("CARTO_API_KEY") or None, "webapp_url": notify.webapp_url() or None}


@app.get("/api/patients")
def list_patients(zone: Optional[str] = Query(None, pattern="^(green|yellow|red)$"),
                  district: Optional[str] = None, nurse: Optional[str] = None, lang: str = "uz"):
    return _all_patients(zone, district, nurse, _lang(lang))


@app.get("/api/patients/{pid}")
def get_patient(pid: int, lang: str = "uz"):
    lang = _lang(lang)
    with session() as c:
        p, visits, a = _load(c, pid)
        alerts = [dict(r) for r in c.execute(
            "SELECT * FROM alerts WHERE patient_id=? ORDER BY id DESC", (pid,))]
    p["discharge_label"] = reason_label(p.get("discharge_reason"), lang)
    return {"patient": p, "visits": visits, "assessment": a.as_dict(lang), "alerts": alerts,
            "chain": chain.build(p, visits, a, alerts, lang=lang)}


@app.post("/api/patients/{pid}/visits")
async def add_visit(pid: int, v: VisitIn, lang: str = "uz"):
    lang = _lang(lang)
    unknown = [s for s in v.symptoms if s not in rules.DANGER_SIGNS]
    if unknown:
        raise HTTPException(422, f"Noma'lum belgi: {unknown}. Mumkin: {list(rules.DANGER_SIGNS)}")
    with session() as c:
        if v.client_id and c.execute("SELECT 1 FROM visits WHERE client_id=?", (v.client_id,)).fetchone():
            p, visits, a = _load(c, pid)       # offline navbat qayta yuborildi — takrorlamaymiz
            return {"duplicate": True, "zone_before": a.zone, "zone_after": a.zone,
                    "zone_changed": False, "assessment": a.as_dict(lang), "alert_id": None}
        _, _, before = _load(c, pid)
        c.execute(
            """INSERT INTO visits (patient_id, date, ga_weeks, sbp, dbp, protein_g_l, hb_g_l,
                   glucose_fasting, symptoms, source, client_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, v.date, v.ga_weeks, v.sbp, v.dbp, v.protein_g_l, v.hb_g_l,
             v.glucose_fasting, json.dumps(v.symptoms), v.source, v.client_id))
        c.commit()
        p, visits, after = _load(c, pid)
    alert_id = None
    if after.zone == "red":
        alert_id = await notify.create_red_alert(p, after.as_dict(), v.ga_weeks or visits[-1].get("ga_weeks"))
    return {"zone_before": before.zone, "zone_after": after.zone, "zone_changed": before.zone != after.zone,
            "assessment": after.as_dict(lang), "alert_id": alert_id}


@app.post("/api/patients/{pid}/extract")
async def extract_photo(pid: int, file: UploadFile = File(...), date: Optional[str] = None, lang: str = "uz"):
    """Tahlil rasmi -> AI öqiydi -> zona OLDINDAN körsatiladi (saqlanmaydi, hamşira tasdiqlaydi)."""
    if (file.content_type or "").split(";")[0] not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Faqat rasm (jpg, png, webp)")
    image = await file.read()
    if len(image) > 10 * 1024 * 1024:
        raise HTTPException(413, "Rasm 10 MB dan katta")
    try:
        ex = await extract_from_image(image, file.content_type.split(";")[0])
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return _preview(pid, ex, "photo", date, _lang(lang))


@app.post("/api/patients/{pid}/voice")
async def voice_input(pid: int, file: UploadFile = File(...), lang: str = "uz"):
    """Hamşira ovozi -> matn -> körsatkiçlar -> zona oldindan (saqlanmaydi)."""
    audio = await file.read()
    if len(audio) > 15 * 1024 * 1024:
        raise HTTPException(413, "Audio juda katta")
    try:
        text, stt = await transcribe(audio, file.content_type or "audio/webm")
        ex = await parse_text(text, rules.DANGER_SIGNS)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    ex["transcript"], ex["stt"] = text, stt
    return _preview(pid, ex, "voice", None, _lang(lang))


@app.post("/api/patients/{pid}/voice-text")
async def voice_text(pid: int, body: TextIn, lang: str = "uz"):
    """Matn (yoki brauzer tanigan nutq) -> körsatkiçlar. Demo va zaxira uçun."""
    ex = await parse_text(body.text, rules.DANGER_SIGNS)
    ex["transcript"] = body.text
    return _preview(pid, ex, "voice", None, _lang(lang))


def _preview(pid: int, ex: dict, source: str, date: Optional[str], lang: str = "uz") -> dict:
    with session() as c:
        p, visits, before = _load(c, pid)
    last = visits[-1] if visits else {}
    vals = ex["values"]
    draft = {"date": date or _date.today().isoformat(),
             "ga_weeks": vals.get("ga_weeks") or last.get("ga_weeks"),
             "sbp": vals.get("sbp"), "dbp": vals.get("dbp"), "protein_g_l": vals.get("protein_g_l"),
             "hb_g_l": vals.get("hb_g_l"), "glucose_fasting": vals.get("glucose_fasting"),
             "symptoms": ex.get("symptoms", []), "source": source}
    preview = rules.assess(_patient_obj(p), [_visit_obj(v) for v in visits] + [_visit_obj(draft)])
    name_match = None
    if ex.get("patient_name"):
        norm = lambda s: {w for w in to_new(s).lower().replace("'", "").replace("ʻ", "").split() if len(w) > 2}
        name_match = bool(norm(ex["patient_name"]) & norm(p["full_name"])) or \
            _translit_match(ex["patient_name"], p["full_name"])
    if lang == "ru":
        ex["warnings"] = [_warn_ru(w) for w in ex.get("warnings", [])]
    return {"extraction": ex, "draft_visit": draft, "name_match": name_match,
            "zone_before": before.zone, "preview_assessment": preview.as_dict(lang)}


_FIELD_RU = {"Gemoglobin": "Гемоглобин", "Oç qoringa glyukoza": "Глюкоза натощак", "Siydikda oqsil": "Белок в моче",
             "Arterial bosim — sistolik": "Систолическое давление", "Arterial bosim — diastolik": "Диастолическое давление",
             "Homiladorlik muddati": "Срок беременности"}


def _warn_ru(w: str) -> str:
    label, _, rest = w.partition(": ")
    short = label.split(",")[0].split(" (")[0]
    name = _FIELD_RU.get(short, short)
    if "raqam öqilmadi" in rest:
        return f"{name}: число не распознано — проверьте вручную"
    if "AI işonçi past" in rest:
        pct = rest[rest.find("(") + 1:rest.find(")")]
        return f"{name}: низкая уверенность AI ({pct}) — проверьте вручную"
    if "mantiqsiz qiymat" in rest:
        return f"{name}: {rest.split(' ')[0]} — недопустимое значение, проверьте вручную"
    return w


_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
                ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s",
                 "t", "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))


def _translit_match(a: str, b: str) -> bool:
    lat = to_new("".join(_CYR.get(ch, ch) for ch in a.lower()))
    wa = {w[:5] for w in lat.split() if len(w) > 2}
    wb = {w[:5] for w in to_new(b).lower().replace("'", "").split() if len(w) > 2}
    return bool(wa & wb)


@app.get("/api/stats")
def stats():
    pts = _all_patients()
    by_zone = Counter(p["zone"] for p in pts)
    by_district: dict[str, Counter] = {}
    for p in pts:
        by_district.setdefault(p["district"], Counter())[p["zone"]] += 1
    with session() as c:
        open_alerts = c.execute("SELECT COUNT(*) n FROM alerts WHERE acknowledged_at IS NULL").fetchone()["n"]
        discharged = c.execute("SELECT COUNT(*) n FROM patients WHERE status='discharged'").fetchone()["n"]
    chains = Counter(p["chain_status"] for p in pts)
    return {"total": len(pts), "open_alerts": open_alerts, "discharged": discharged,
            "chains": {k: chains.get(k, 0) for k in ("broken", "wait", "ok")},
            "by_zone": {z: by_zone.get(z, 0) for z in ("red", "yellow", "green")},
            "by_district": {d: {z: cnt.get(z, 0) for z in ("red", "yellow", "green")}
                            for d, cnt in sorted(by_district.items())},
            "rules_version": rules.RULES_VERSION}


@app.get("/api/rules")
def rules_info():
    """Hakamlar uçun: qoidalar oçiq va manbaga ega."""
    return {"version": rules.RULES_VERSION, "danger_signs": rules.DANGER_SIGNS,
            "principle": "Zonani qoidalar belgilaydi; AI faqat öqiydi va tuşuntiradi. "
                         "AI xavotirni kötara oladi, lekin bekor qila olmaydi. Noma'lum qiymat heç qaçon 'norma' emas."}


# ---------- Ogohlantirişlar ----------
@app.get("/api/alerts")
def list_alerts(open_only: bool = False, kind: Optional[str] = None, lang: str = "uz"):
    lang = _lang(lang)
    q = """SELECT a.*, p.full_name, p.district, p.mahalla, p.phone, p.family_doctor, p.discharge_reason FROM alerts a
           JOIN patients p ON p.id=a.patient_id WHERE 1=1"""
    args: list = []
    if open_only:
        q += " AND a.acknowledged_at IS NULL"
    if kind:
        q += " AND a.kind=?"
        args.append(kind)
    with session() as c:
        rows = [dict(r) for r in c.execute(q + " ORDER BY a.id DESC LIMIT 200", args)]
        cache: dict[int, rules.Assessment] = {}
        for r in rows:
            if r["kind"] == "red_zone":      # xabar — bemorning hozirgi xulosasi, tanlangan tilda
                if r["patient_id"] not in cache:
                    cache[r["patient_id"]] = _load(c, r["patient_id"])[2]
                r["message"] = cache[r["patient_id"]].summary(lang)
            else:                            # aktiv çaqiruv: sabab (tilda) + izoh
                lbl = reason_label(r.get("discharge_reason"), lang)
                r["message"] = lbl + (f" — {r['message']}" if r.get("message") else "")
    return rows


@app.post("/api/alerts/{aid}/ack")
def ack_alert(aid: int, body: AckIn):
    a = notify.acknowledge(aid, body.by)
    if not a:
        raise HTTPException(404, "Ogohlantiriş topilmadi")
    return a


@app.post("/api/alerts/escalate-now")
async def escalate_now():
    """Demo uçun: muddati ötganlarni darhol tekşiriş."""
    return {"escalated": await notify.escalate_due()}


# ---------- №11: javob beriş -> aktiv çaqiruv ----------
@app.post("/api/patients/{pid}/discharge")
async def discharge(pid: int, body: DischargeIn):
    with session() as c:
        p, _, _ = _load(c, pid)
        c.execute("UPDATE patients SET status='discharged', discharged_at=datetime('now','localtime'), "
                  "discharge_reason=? WHERE id=?", (body.reason, pid))
        c.commit()
        p, _, _ = _load(c, pid)
    aid = await notify.create_active_call(p, reason_label(body.reason, "uz"), body.notes)
    with session() as c:
        a = dict(c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone())
    return {"patient_id": pid, "status": "discharged", "active_call": a}


@app.get("/api/doctor/tasks")
def doctor_tasks(lang: str = "uz"):
    return list_alerts(open_only=False, kind="active_call", lang=lang)


# ---------- Sahifalar ----------
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def page_index():
        return FileResponse(STATIC / "index.html")

    @app.get("/{page}", include_in_schema=False)
    def page(page: str):
        f = STATIC / f"{page}.html"
        if page in ("dashboard", "nurse", "doctor", "app", "setup") and f.exists():
            return FileResponse(f)
        if page in ("sw.js", "manifest.webmanifest"):
            return FileResponse(STATIC / page)
        raise HTTPException(404)
