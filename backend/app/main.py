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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import random
from datetime import datetime, timedelta

from . import ai, auth, chain, notify, rules
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


@app.middleware("http")
async def guard(request: Request, call_next):
    """Har bir API so‘rovi: kim kirgan (token) va unga bu bölim ruxsatmi (rol)."""
    path = request.url.path
    request.state.user = None
    if auth.enabled() and path.startswith("/api/") and not path.startswith(auth.PUBLIC_API):
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        u = auth.user_by_token(token)
        if not u:
            return JSONResponse({"detail": "Tizimga kiring"}, status_code=401)
        if not auth.allowed(u["role"], path):
            return JSONResponse({"detail": "Bu bölimga ruxsat yöq"}, status_code=403)
        request.state.user = u
    return await call_next(request)


def who(request: Request, default: str = "Dashboard") -> str:
    u = getattr(request.state, "user", None)
    return f"{u['full_name']} ({u['role_uz']})" if u else default


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
        "chain_reason": ch["reason"], "plan": p.get("plan") or "bepul", "created_at": p.get("created_at"),
        "family_doctor": p.get("family_doctor"),
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
def ack_alert(aid: int, body: AckIn, request: Request):
    a = notify.acknowledge(aid, who(request, body.by))
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


# ---------- Ommaviy (boş sahifa uçun, kiriş talab qilinmaydi) ----------
@app.get("/api/public/overview")
def public_overview(lang: str = "uz"):
    lang = _lang(lang)
    pts = _all_patients(lang=lang)
    br = next((p for p in pts if p["chain_status"] == "broken" and p["chain_break_key"] == "specialist"), None) or \
        next((p for p in pts if p["chain_status"] == "broken"), None)
    ok = next((p for p in pts if p["chain_status"] == "ok" and p["status"] == "discharged"), None) or \
        next((p for p in pts if p["chain_status"] == "ok"), None)
    ex = []
    for p in (br, ok):
        if p:
            d = get_patient(p["id"], lang)
            ex.append({"full_name": d["patient"]["full_name"], "district": d["patient"]["district"], "chain": d["chain"]})
    return {"stats": stats(), "examples": ex}


# ---------- Kiriş ----------
class LoginIn(BaseModel):
    username: str = Field(..., max_length=40)
    password: str = Field(..., max_length=100)


@app.post("/api/login")
def login(body: LoginIn):
    u = auth.login(body.username, body.password)
    if not u:
        raise HTTPException(401, "Login yoki parol notöğri")
    return u


@app.post("/api/logout")
def logout(request: Request):
    auth.logout(request.headers.get("authorization", "").removeprefix("Bearer ").strip())
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return request.state.user or {"username": "demo", "role": "bosh", "full_name": "Demo", "home": "/dashboard",
                                  "role_uz": "Boş şifokor", "role_ru": "Главный врач", "patient_id": None}


# ---------- AI: şifokor xulosasi, jim qoliş xavfi ----------
def _context(c, pid: int, lang: str) -> dict:
    p, visits, a = _load(c, pid)
    alerts = [dict(r) for r in c.execute("SELECT * FROM alerts WHERE patient_id=? ORDER BY id DESC", (pid,))]
    appts = [dict(r) for r in c.execute("SELECT * FROM appointments WHERE patient_id=? ORDER BY at DESC", (pid,))]
    msgs = [dict(r) for r in c.execute("SELECT * FROM messages WHERE patient_id=? ORDER BY id DESC", (pid,))]
    ch = chain.build(p, visits, a, alerts, lang=lang)
    risk = ai.noshow_risk(p, visits, appts, msgs, a.zone, ch["status"], chain.interval_for(p, a.zone), lang)
    return {"patient": p, "visits": visits, "a": a, "assessment": a.as_dict(lang), "alerts": alerts,
            "appointments": appts, "messages": msgs, "chain": ch, "risk": risk}


@app.get("/api/patients/{pid}/ai-summary")
async def ai_summary(pid: int, lang: str = "uz"):
    lang = _lang(lang)
    with session() as c:
        ctx = _context(c, pid, lang)
    data = {k: ctx[k] for k in ("patient", "visits", "assessment", "chain", "risk")}
    data["patient"] = {k: data["patient"].get(k) for k in ("full_name", "age", "plan", "prev_preeclampsia",
                                                          "multiple_pregnancy", "status", "complaint")}
    return {**await ai.summary(data, lang), "risk": ctx["risk"]}


@app.get("/api/risk")
def risk_list(limit: int = 8, lang: str = "uz"):
    """Jim qoliş xavfi eng yuqori bemorlar — "bugun qöng‘iroq qiling" röyxati."""
    lang = _lang(lang)
    out = []
    with session() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM patients WHERE status='pregnant'")]
        for pid in ids:
            ctx = _context(c, pid, lang)
            p = ctx["patient"]
            out.append({"id": pid, "full_name": p["full_name"], "phone": p["phone"], "nurse": p["nurse"],
                        "plan": p.get("plan") or "bepul", "zone": ctx["a"].zone, **ctx["risk"]})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


# ---------- Kritik bosqiç: qizil > 2 soat javobsiz ----------
class CriticalAckIn(BaseModel):
    action: str = Field(..., pattern="^(doctor|103)$")


@app.post("/api/alerts/critical-now")
async def critical_now():
    """Demo: "2 soat ötdi" — barça javobsiz qizil signallarni kritik bosqiçga ötkazadi."""
    return {"critical": await notify.escalate_critical(force=True)}


@app.post("/api/alerts/{aid}/critical-ack")
def critical_ack(aid: int, body: CriticalAckIn, request: Request):
    a = notify.critical_ack(aid, who(request), body.action)
    if not a:
        raise HTTPException(404, "Ogohlantiriş topilmadi")
    return a


# ---------- Qabulxona ----------
PRICE_VISIT = 250_000           # söm, Premium tarif (xususiy klinika)
PREPAY_SHARE = 0.5              # premium: 50% oldindan (125 000 söm)
UZILMAS_SHARE = float(__import__("os").environ.get("UZILMAS_SHARE", "0.2"))   # Uzilmas ulushi (gipoteza): 20%
NURSES = ["M. Ahmedova", "G. Usmonova", "S. Rasulova", "N. Tursunova"]
DOCTORS = ["Dr. A. Sodiqov", "Dr. F. Xudoyberdiyeva", "Dr. B. Qosimov", "Dr. Z. Mamatova"]
PLANS = {
    "bepul": {"uz": ["Klinikaning odatdagi qabuliga kiradi — qöşimça tölov yöq", "Patronaj: har 7/14/28 kunda (zonaga qarab)",
                     "Qizil zona — şifokorga signal va eskalatsiya", "AI yordamçi (savol-javob)"],
              "ru": ["Входит в обычный приём клиники — без доплаты", "Патронаж: каждые 7/14/28 дней (по зоне)",
                     "Красная зона — сигнал врачу и эскалация", "AI-помощник (вопросы)"]},
    "premium": {"uz": ["250 000 söm — 50% (125 000 söm) oldindan", "Şaxsiy oilaviy şifokor — 24 soat içida uyga keladi",
                       "Patronaj 2 baravar tez-tez: har 3/7/14 kunda", "Har hafta AI tekşiruvi + şifokor köradi",
                       "Qizil signal — şaxsiy şifokorga ham, 2 soatda kritik"],
                "ru": ["250 000 сум — 50% (125 000 сум) предоплата", "Личный семейный врач — визит на дом в течение 24 часов",
                       "Патронаж в 2 раза чаще: каждые 3/7/14 дней", "Еженедельная AI-проверка + просмотр врачом",
                       "Красный сигнал — и личному врачу, через 2 часа критично"]},
}


class IntakeIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=3000)


@app.post("/api/ai/intake")
async def ai_intake(body: IntakeIn):
    """Qabulxona AI yordamçisi: erkin matn -> forma (xodim tekşirib, tasdiqlaydi)."""
    from .seed import DISTRICTS
    return await ai.intake(body.text, list(DISTRICTS), rules.DANGER_SIGNS)


class RegisterIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120)
    age: Optional[int] = Field(None, ge=12, le=60)
    phone: Optional[str] = Field(None, max_length=40)
    district: str
    ga_weeks: Optional[float] = Field(None, ge=0, le=45)
    sbp: Optional[int] = Field(None, ge=50, le=260)
    dbp: Optional[int] = Field(None, ge=30, le=180)
    hb_g_l: Optional[float] = Field(None, ge=30, le=200)
    symptoms: list[str] = []
    complaint: Optional[str] = Field(None, max_length=500)
    plan: str = Field("bepul", pattern="^(bepul|premium)$")
    visit_at: Optional[str] = None
    prev_preeclampsia: bool = False
    multiple_pregnancy: bool = False


_POLYS: dict = {}


def _assign(c, district: str, zone: str) -> dict:
    """Javobgarni tanlaş: tumandagi eng kam yuklangan hamşira, umumiy eng kam yuklangan oilaviy şifokor."""
    def load(col, name, where=""):
        return c.execute(f"SELECT COUNT(*) n FROM patients WHERE {col}=? AND status='pregnant' {where}",
                         (name, *([district] if where else []))).fetchone()["n"]
    nurse = min(NURSES, key=lambda n: (load("nurse", n, "AND district=?"), n))
    doctor = min(DOCTORS, key=lambda d: (load("family_doctor", d), d))
    return {"nurse": nurse, "family_doctor": doctor,
            "nurse_load": load("nurse", nurse, "AND district=?"), "doctor_load": load("family_doctor", doctor)}


@app.post("/api/reception/register")
async def reception_register(body: RegisterIn, request: Request, lang: str = "uz"):
    from .seed import DISTRICTS, _point, _polys
    lang = _lang(lang)
    if body.district not in DISTRICTS:
        raise HTTPException(422, f"Tuman notöğri. Mumkin: {list(DISTRICTS)}")
    bad = [s for s in body.symptoms if s not in rules.DANGER_SIGNS]
    if bad:
        raise HTTPException(422, f"Noma'lum belgi: {bad}")
    if "polys" not in _POLYS:
        _POLYS["polys"] = _polys()
    lat, lon = _point(random.Random(), body.district, _POLYS["polys"])
    by = who(request, "Qabulxona")
    today = _date.today().isoformat()
    has_vitals = any(v is not None for v in (body.sbp, body.dbp, body.hb_g_l)) or body.symptoms
    with session() as c:
        # dastlabki zona — javobgarni tanlaşdan oldin (qizil bölsa ham xuddi şu tartib)
        draft = [rules.Visit(date=today, ga_weeks=body.ga_weeks, sbp=body.sbp, dbp=body.dbp, hb_g_l=body.hb_g_l,
                             symptoms=body.symptoms)] if has_vitals else []
        pre = rules.assess(rules.Patient(age=body.age, multiple_pregnancy=body.multiple_pregnancy,
                                         prev_preeclampsia=body.prev_preeclampsia), draft)
        resp = _assign(c, body.district, pre.zone)
        cur = c.execute(
            """INSERT INTO patients (full_name, age, phone, district, mahalla, lat, lon, multiple_pregnancy,
                   prev_preeclampsia, nurse, family_doctor, plan, complaint, created_at, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'),?)""",
            (to_new(body.full_name).strip(), body.age, body.phone, body.district, "", lat, lon,
             int(body.multiple_pregnancy), int(body.prev_preeclampsia), resp["nurse"], resp["family_doctor"],
             body.plan, body.complaint, by))
        pid = cur.lastrowid
        if has_vitals:
            c.execute("""INSERT INTO visits (patient_id, date, ga_weeks, sbp, dbp, hb_g_l, symptoms, source)
                         VALUES (?,?,?,?,?,?,?,?)""",
                      (pid, today, body.ga_weeks, body.sbp, body.dbp, body.hb_g_l, json.dumps(body.symptoms), "manual"))
        at = body.visit_at or (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M")
        price = PRICE_VISIT if body.plan == "premium" else 0
        prepaid = int(price * PREPAY_SHARE)
        ap = c.execute("""INSERT INTO appointments (patient_id, at, plan, price, prepaid, created_by)
                          VALUES (?,?,?,?,?,?)""", (pid, at.replace("T", " "), body.plan, price, prepaid, by)).lastrowid
        c.commit()
        p, visits, a = _load(c, pid)
    alert_id = None
    if a.zone == "red":
        alert_id = await notify.create_red_alert(p, a.as_dict(), body.ga_weeks)
    if body.plan == "premium":       # şaxsiy oilaviy şifokor 24 soat içida uyga
        due = notify.now() + timedelta(hours=24)
        with session() as c:
            c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, due_at, created_at)
                         VALUES (?,?,?,?,?,?)""",
                      (pid, "active_call", "Premium: birinçi uy taşrifi (24 soat)", "family_doctor",
                       due.isoformat(sep=" "), notify.now().isoformat(sep=" ")))
    with session() as c:
        ctx = _context(c, pid, lang)
    why = (f"{body.district}: eng kam yuklangan hamşira ({resp['nurse_load']} bemor), "
           f"oilaviy şifokor — {resp['doctor_load']} bemor") if lang == "uz" else \
          (f"{body.district}: наименее загруженная медсестра ({resp['nurse_load']} пац.), "
           f"семейный врач — {resp['doctor_load']} пац.")
    return {"patient_id": pid, "zone": a.zone, "assessment": a.as_dict(lang), "nurse": resp["nurse"],
            "family_doctor": resp["family_doctor"], "why": why, "alert_id": alert_id, "plan": body.plan,
            "appointment": {"id": ap, "at": at, "price": price, "prepaid": prepaid}, "risk": ctx["risk"],
            "chain": ctx["chain"]}


@app.get("/api/reception/plans")
def reception_plans(lang: str = "uz"):
    lang = _lang(lang)
    return {"price": PRICE_VISIT, "prepay_share": PREPAY_SHARE,
            "plans": {k: v[lang] for k, v in PLANS.items()}}


@app.get("/api/live")
def live(limit: int = 12, lang: str = "uz"):
    """Jonli lenta: qabulxonada yozilganlar (kim javobgar), kritik signallar."""
    lang = _lang(lang)
    with session() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT p.id, p.full_name, p.district, p.nurse, p.family_doctor, p.plan, p.created_at, p.created_by,
                      a.at, a.status AS appt_status, a.prepaid, a.price, a.id AS appt_id
               FROM patients p LEFT JOIN appointments a ON a.patient_id=p.id
               WHERE p.created_at IS NOT NULL ORDER BY p.created_at DESC, p.id DESC LIMIT ?""", (limit,))]
        for r in rows:
            _, _, a = _load(c, r["id"])
            r["zone"] = a.zone
        crit = [dict(r) for r in c.execute(
            """SELECT a.id, a.patient_id, a.created_at, a.critical_at, p.full_name, p.phone, p.family_doctor, p.district
               FROM alerts a JOIN patients p ON p.id=a.patient_id
               WHERE a.critical_at IS NOT NULL AND a.critical_ack_at IS NULL ORDER BY a.critical_at DESC""")]
    return {"registrations": rows, "critical": crit, "critical_minutes": notify.critical_minutes(),
            "now": notify.now().isoformat(sep=" ")}


class ApptStatusIn(BaseModel):
    status: str = Field(..., pattern="^(came|no_show|moved)$")


@app.post("/api/appointments/{aid}/status")
def appointment_status(aid: int, body: ApptStatusIn, request: Request):
    """Keldi / kelmadi / köçirildi. Kelmasa: premium oldindan tölov qaytarilmaydi, hamşiraga qöng‘iroq vazifasi."""
    with session() as c:
        a = c.execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone()
        if not a:
            raise HTTPException(404, "Qabul topilmadi")
        if body.status == "moved":
            new_at = (datetime.fromisoformat(a["at"][:16]) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
            c.execute("UPDATE appointments SET at=?, status='scheduled' WHERE id=?", (new_at, aid))
        else:
            c.execute("UPDATE appointments SET status=? WHERE id=?", (body.status, aid))
        return dict(c.execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone())


# ---------- Statistika (boş şifokor / klinika rahbari) ----------
MARKET = {  # xususiy sektor: rasmiy manbalar (pitç va hakamlar uçun)
    "private_clinics_2026": 8700, "private_clinics_2016": 3200, "private_beds_share": [12, 31],
    "new_private_2025": 1329, "new_private_tashkent_2025": 251, "births_2025": 879_599, "births_tashkent_2025": 62_318,
    "sources": [["spot.uz — Prezident taqdimoti, 2026-05-01", "https://www.spot.uz/ru/2026/05/01/private-healthcare/"],
                ["podrobno.uz — 2025-yilda 1329 xususiy klinika", "https://podrobno.uz/cat/obchestvo/svyshe-1300-chastnykh-klinik-otkrylis-v-uzbekistane-za-god/"],
                ["stat.uz — 2025-yil tuğilişlar", "https://stat.uz/uz/matbuot-markazi/qo-mita-yangiliklar/66611"],
                ["Gemini API narxlari", "https://ai.google.dev/gemini-api/docs/pricing"]],
}


def _mins(a: Optional[str], b: Optional[str]) -> Optional[float]:
    try:
        return (datetime.fromisoformat(b[:19]) - datetime.fromisoformat(a[:19])).total_seconds() / 60
    except (TypeError, ValueError):
        return None


@app.get("/api/analytics")
def analytics(lang: str = "uz"):
    from . import usage
    lang = _lang(lang)
    pts = _all_patients(lang=lang)
    with session() as c:
        ap = [dict(r) for r in c.execute("SELECT * FROM appointments")]
        al = [dict(r) for r in c.execute("SELECT a.*, p.family_doctor FROM alerts a JOIN patients p ON p.id=a.patient_id")]
        ai_rows = [dict(r) for r in c.execute(
            """SELECT feature, source, COUNT(*) n, SUM(tokens_in) tin, SUM(tokens_out) tout, SUM(tokens_think) tth,
                      SUM(cost_usd) cost, SUM(ok=0) errors FROM ai_usage GROUP BY feature, source""")]
        msgs = c.execute("SELECT COUNT(*) n, SUM(danger != '[]') d FROM messages").fetchone()
    # bemorlar va tariflar
    prem = [p for p in pts if p["plan"] == "premium"]
    plan = {"total": len(pts), "premium": len(prem), "standart": len(pts) - len(prem),
            "premium_share": round(100 * len(prem) / max(len(pts), 1), 1),
            "new_7d": sum(1 for p in pts if p.get("created_at") and _mins(p["created_at"], datetime.now().isoformat()) < 7 * 1440)}
    # pul (faqat Premium; Standart — klinika qabuli narxiga kiradi)
    st = Counter(a["status"] for a in ap)
    pa = [a for a in ap if a["plan"] == "premium"]
    came = sum(a["price"] for a in pa if a["status"] == "came")
    prepaid_open = sum(a["prepaid"] for a in pa if a["status"] in ("scheduled", "moved"))
    forfeited = sum(a["prepaid"] for a in pa if a["status"] == "no_show")
    revenue = came + prepaid_open + forfeited
    money = {"price": PRICE_VISIT, "prepay": int(PRICE_VISIT * PREPAY_SHARE), "premium_appts": len(pa),
             "collected": revenue, "paid_in_full": came, "prepaid_open": prepaid_open, "forfeited": forfeited,
             "expected_rest": sum(a["price"] - a["prepaid"] for a in pa if a["status"] == "scheduled"),
             "uzilmas_share": UZILMAS_SHARE, "uzilmas_revenue": int(revenue * UZILMAS_SHARE)}

    def noshow(rows):
        done = [a for a in rows if a["status"] in ("came", "no_show")]
        return round(100 * sum(a["status"] == "no_show" for a in done) / len(done), 1) if done else None
    appts = {"by_status": {k: st.get(k, 0) for k in ("scheduled", "came", "no_show", "moved")},
             "noshow_rate": noshow(ap), "noshow_premium": noshow(pa), "noshow_standart": noshow([a for a in ap if a["plan"] != "premium"])}
    # signallar va javob tezligi
    red = [a for a in al if a["kind"] == "red_zone"]
    ack_m = [m for m in (_mins(a["created_at"], a["acknowledged_at"]) for a in red if a["acknowledged_at"]) if m is not None and m >= 0]
    by_doc: dict = {}
    for a in al:
        d = by_doc.setdefault(a["family_doctor"] or "—", {"alerts": 0, "open": 0, "ack_min": []})
        d["alerts"] += 1
        if not a["acknowledged_at"]:
            d["open"] += 1
        m = _mins(a["created_at"], a["acknowledged_at"]) if a["acknowledged_at"] else None
        if m is not None and m >= 0:
            d["ack_min"].append(m)
    staff = []
    for name, d in sorted(by_doc.items()):
        staff.append({"name": name, "patients": sum(1 for p in pts if p.get("family_doctor") == name),
                      "alerts": d["alerts"], "open": d["open"],
                      "avg_ack_min": round(sum(d["ack_min"]) / len(d["ack_min"]), 1) if d["ack_min"] else None})
    signals = {"red_total": len(red), "red_acked": len(ack_m), "avg_ack_min": round(sum(ack_m) / len(ack_m), 1) if ack_m else None,
               "median_ack_min": round(sorted(ack_m)[len(ack_m) // 2], 1) if ack_m else None,
               "escalated": sum(1 for a in al if a["escalated_at"]), "critical": sum(1 for a in al if a.get("critical_at")),
               "calls_103": sum(1 for a in al if "103" in (a.get("critical_ack_by") or "")),
               "active_calls": sum(1 for a in al if a["kind"] == "active_call"),
               "patient_msgs": msgs["n"] or 0, "patient_danger_msgs": msgs["d"] or 0}
    # AI sarfi
    pr = usage.prices()
    feats = {}
    for r in ai_rows:
        f = feats.setdefault(r["feature"], {"name": usage.FEATURES.get(r["feature"], (r["feature"],) * 2)[1 if lang == "ru" else 0],
                                            "requests": 0, "gemini": 0, "rules": 0, "tokens_in": 0, "tokens_out": 0,
                                            "tokens_think": 0, "cost_usd": 0.0, "errors": 0})
        f["requests"] += r["n"]
        f[r["source"] if r["source"] in ("gemini", "rules") else "rules"] += r["n"]
        for k, col in (("tokens_in", "tin"), ("tokens_out", "tout"), ("tokens_think", "tth"), ("errors", "errors")):
            f[k] += r[col] or 0
        f["cost_usd"] += r["cost"] or 0
    tot = {k: sum(f[k] for f in feats.values()) for k in ("requests", "gemini", "rules", "tokens_in", "tokens_out", "tokens_think", "errors")}
    tot["cost_usd"] = round(sum(f["cost_usd"] for f in feats.values()), 6)
    tot["cost_uzs"] = round(tot["cost_usd"] * pr["usd_uzs"])
    tot["cost_per_request_uzs"] = round(tot["cost_uzs"] / tot["gemini"], 1) if tot["gemini"] else 0
    tot["cost_per_patient_uzs"] = round(tot["cost_uzs"] / max(len(pts), 1), 2)
    for f in feats.values():
        f["cost_usd"] = round(f["cost_usd"], 6)
        f["cost_uzs"] = round(f["cost_usd"] * pr["usd_uzs"], 1)
    # xavf
    risk = Counter(r["level"] for r in risk_list(limit=10_000, lang=lang))
    return {"plan": plan, "money": money, "appointments": appts, "signals": signals, "staff": staff,
            "zones": Counter(p["zone"] for p in pts), "chains": Counter(p["chain_status"] for p in pts),
            "risk": {k: risk.get(k, 0) for k in ("high", "mid", "low")},
            "ai": {"features": feats, "total": tot, "prices": pr}, "market": MARKET,
            "generated_at": notify.now().isoformat(sep=" ")}


# ---------- Bemor kabineti ----------
def _my_pid(request: Request) -> int:
    u = getattr(request.state, "user", None)
    if u and u.get("patient_id"):
        return int(u["patient_id"])
    if not auth.enabled():
        return 101
    raise HTTPException(403, "Bemor hisobi emas")


@app.get("/api/my/card")
def my_card(request: Request, lang: str = "uz"):
    lang = _lang(lang)
    pid = _my_pid(request)
    with session() as c:
        ctx = _context(c, pid, lang)
    p = ctx["patient"]
    last = ctx["visits"][-1] if ctx["visits"] else {}
    crit = next((x for x in ctx["alerts"] if x.get("critical_at") and not x.get("critical_ack_at")), None)
    open_red = next((x for x in ctx["alerts"] if x["kind"] == "red_zone" and not x["acknowledged_at"]), None)
    return {"patient": {k: p.get(k) for k in ("id", "full_name", "age", "district", "nurse", "family_doctor", "plan",
                                              "phone", "status")},
            "zone": ctx["a"].zone, "summary": ctx["a"].summary(lang), "ga_weeks": last.get("ga_weeks"),
            "last_visit": last.get("date"), "next_visit_in": max(0, chain.interval_for(p, ctx["a"].zone) - (
                (_date.today() - _date.fromisoformat(last["date"][:10])).days if last else 0)),
            "appointments": ctx["appointments"][:3], "messages": list(reversed(ctx["messages"][:20])),
            "chain": ctx["chain"], "critical": bool(crit), "doctor_notified": bool(open_red),
            "plan_features": PLANS[p.get("plan") or "bepul"][lang]}


class AskIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


@app.post("/api/my/ask")
async def my_ask(body: AskIn, request: Request, lang: str = "uz"):
    """Bemor savoli -> AI triaj. Xavf belgisi bölsa: taşrif sifatida yoziladi -> qoidalar -> şifokorga signal."""
    lang = _lang(lang)
    pid = _my_pid(request)
    with session() as c:
        p, visits, a = _load(c, pid)
    last = visits[-1] if visits else {}
    tr = await ai.triage(body.text, p, a.zone, last.get("ga_weeks"), rules.DANGER_SIGNS, lang)
    vals = (await parse_text(body.text, rules.DANGER_SIGNS))["values"]
    bp = {k: vals.get(k) for k in ("sbp", "dbp") if vals.get(k)}
    if bp.get("sbp") and not bp.get("dbp"):
        bp = {}
    alert_id, zone_after = None, a.zone
    if tr["danger"] or bp:
        with session() as c:
            c.execute("""INSERT INTO visits (patient_id, date, ga_weeks, sbp, dbp, symptoms, source)
                         VALUES (?,?,?,?,?,?,?)""",
                      (pid, _date.today().isoformat(), last.get("ga_weeks"), bp.get("sbp"), bp.get("dbp"),
                       json.dumps(tr["danger"]), "manual"))
            c.commit()
            p, visits, after = _load(c, pid)
        zone_after = after.zone
        if after.zone == "red":
            alert_id = await notify.create_red_alert(p, after.as_dict(), last.get("ga_weeks"))
    with session() as c:
        c.execute("INSERT INTO messages (patient_id, text, reply, danger, source) VALUES (?,?,?,?,?)",
                  (pid, body.text, tr["reply"], json.dumps(tr["danger"]), tr["source"]))
    names = rules.DANGER_SIGNS_RU if lang == "ru" else rules.DANGER_SIGNS
    return {"reply": tr["reply"], "danger": [names[s] for s in tr["danger"]], "zone_before": a.zone,
            "zone_after": zone_after, "alert_id": alert_id, "source": tr["source"]}


@app.post("/api/my/appointments/{aid}/move")
def my_move(aid: int, request: Request):
    pid = _my_pid(request)
    with session() as c:
        a = c.execute("SELECT * FROM appointments WHERE id=? AND patient_id=?", (aid, pid)).fetchone()
        if not a:
            raise HTTPException(404, "Qabul topilmadi")
        if datetime.fromisoformat(a["at"][:16]) - datetime.now() < timedelta(hours=24):
            raise HTTPException(409, "24 soatdan kam qoldi — klinikaga qöng‘iroq qiling")
    return appointment_status(aid, ApptStatusIn(status="moved"), request)


# ---------- Sahifalar ----------
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def page_index():
        return FileResponse(STATIC / "index.html")

    @app.get("/{page}", include_in_schema=False)
    def page(page: str):
        f = STATIC / f"{page}.html"
        if page in ("dashboard", "nurse", "doctor", "app", "setup", "login", "reception", "patient", "analytics") and f.exists():
            return FileResponse(f)
        if page in ("sw.js", "manifest.webmanifest"):
            return FileResponse(STATIC / page)
        raise HTTPException(404)
