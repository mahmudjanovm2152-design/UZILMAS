"""
Telegram xabarnomalari + eskalatsiya.

  * Qizil zona   -> mutaxassis (OvaBMU) çatiga xabar, "✅ Qabul qildim" tugmasi.
                    ESCALATE_MINUTES içida tasdiqlanmasa -> boş şifokor çatiga.
  * Aktiv çaqiruv (№11) -> oilaviy şifokor çatiga, "✅ Taşrif qildim" tugmasi.
                    Muddat (24 soat) ötsa -> boş şifokor çatiga.

Token bölmasa xabarlar yuborilmaydi, lekin ogohlantirişlar bazada yaratiladi
va daşboardda körinadi (demo internetsiz ham işlaydi).
"""
from __future__ import annotations

import asyncio
import re
import html
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .db import session

log = logging.getLogger("uzilmas.notify")
TG = "https://api.telegram.org/bot{token}/{method}"
ICON = {"red": "🔴", "yellow": "🟡", "green": "🟢"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _num(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)).replace(",", ".") or default)
    except ValueError:
        return default


def escalate_minutes() -> float:
    return _num("ESCALATE_MINUTES", 2)


def active_call_minutes() -> float:
    return _num("ACTIVE_CALL_MINUTES", 24 * 60)


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


async def tg(method: str, **params) -> Optional[dict]:
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=35) as c:
            r = await c.post(TG.format(token=token, method=method), json=params)
            data = r.json()
            if not data.get("ok"):
                log.warning("Telegram %s: %s", method, data)
            return data
    except httpx.HTTPError as e:
        log.warning("Telegram aloqasi yöq: %s", e)
        return None


def webapp_url() -> str:
    """Mini App manzili (faqat https — Telegram talabi). Masalan: https://xxxx.trycloudflare.com"""
    u = _env("WEBAPP_URL").rstrip("/")
    return u if u.startswith("https://") else ""


async def send(chat_id: str, text: str, button: Optional[tuple[str, str]] = None,
               rows: Optional[list] = None) -> Optional[int]:
    if not chat_id:
        return None
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    kb = []
    if button:
        kb.append([{"text": button[0], "callback_data": button[1]}])
    kb += rows or []
    if kb:
        params["reply_markup"] = {"inline_keyboard": kb}
    data = await tg("sendMessage", **params)
    return (data or {}).get("result", {}).get("message_id")


# ---------------- Xabar matnlari ----------------
def red_text(p: dict, a: dict, ga) -> str:
    e = html.escape
    lines = [f"🔴 <b>QIZIL ZONA</b> — {e(p['full_name'])}, {p['age']} yoş",
             f"📍 {e(p['district'])}, {e(p['mahalla'])} mahallasi" + (f" · {ga:g} hafta" if ga else "")]
    for f in a["findings"][:4]:
        lines.append(f"{ICON[f['level']]} {e(f['reason'])}")
    if a["needs_review"]:
        lines.append("❔ Tekşiriş kerak: " + e(", ".join(a["needs_review"])))
    src = a["findings"][0]["rule_id"] if a["findings"] else "-"
    lines += [f"📋 Qoida: <code>{e(src)}</code> · v{e(a['rules_version'])}",
              f"👩‍⚕️ {e(p.get('nurse') or '-')} · 📞 {e(p.get('phone') or '-')}",
              f"🩸 Qon guruhi: {e(p.get('blood_group') or '-')} · Allergiya: {e(p.get('allergies') or '-')}",
              f"⏱ {escalate_minutes():g} daqiqada tasdiqlanmasa — boş şifokorga yuboriladi.",
              "<i>Uzilmas · bemor zanjiri uzilmaydi</i>"]
    return "\n".join(lines)


def active_call_text(p: dict, reason: str, notes: str, hours: float) -> str:
    e = html.escape
    return "\n".join([
        f"🏠 <b>AKTIV ÇAQIRUV</b> — {e(p['full_name'])}, {p['age']} yoş",
        f"🏥 Statsionardan javob berildi: {e(reason)}",
        f"📍 {e(p['district'])}, {e(p['mahalla'])} mahallasi · 📞 {e(p.get('phone') or '-')}",
        (f"📝 {e(notes)}" if notes else "📝 Izoh yöq"),
        "Tekşiring: bosim, qon ketiş, isitma, boş oğriği, çaqaloq emişi va harorati.",
        f"⏱ <b>{hours:g} soat</b> içida holidan xabar olib, tasdiqlang.",
        "<i>Uzilmas · bemor zanjiri uzilmaydi</i>",
    ])


# ---------------- Ogohlantirişlar ----------------
async def create_red_alert(p: dict, assessment: dict, ga) -> int:
    with session() as c:
        open_ = c.execute("""SELECT id FROM alerts WHERE patient_id=? AND kind='red_zone'
                             AND acknowledged_at IS NULL""", (p["id"],)).fetchone()
        if open_:
            return open_["id"]
        due = now() + timedelta(minutes=escalate_minutes())
        cur = c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, due_at)
                           VALUES (?,?,?,?,?)""",
                        (p["id"], "red_zone", assessment["summary"], "specialist", due.isoformat(sep=" ")))
        aid = cur.lastrowid
    rows = [[{"text": "📋 Bemor kartasi", "url": f"{webapp_url()}/dashboard?p={p['id']}"}]] if webapp_url() else None
    await send(_env("TELEGRAM_SPECIALIST_CHAT_ID"), red_text(p, assessment, ga), ("✅ Qabul qildim", f"ack:{aid}"), rows)
    return aid


async def create_active_call(p: dict, reason: str, notes: str) -> int:
    minutes = active_call_minutes()
    with session() as c:
        due = now() + timedelta(minutes=minutes)
        cur = c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, due_at)
                           VALUES (?,?,?,?,?)""",
                        (p["id"], "active_call", notes or "",
                         "family_doctor", due.isoformat(sep=" ")))
        aid = cur.lastrowid
    chat = _env("TELEGRAM_DOCTOR_CHAT_ID") or _env("TELEGRAM_SPECIALIST_CHAT_ID")
    rows = [[{"text": "📋 Çaqiruvlar röyxati", "url": f"{webapp_url()}/doctor"}]] if webapp_url() else None
    await send(chat, active_call_text(p, reason, notes, round(minutes / 60, 2)), ("✅ Taşrif qildim", f"ack:{aid}"), rows)
    return aid


def acknowledge(aid: int, by: str) -> Optional[dict]:
    with session() as c:
        a = c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone()
        if not a:
            return None
        if not a["acknowledged_at"]:
            c.execute("UPDATE alerts SET acknowledged_at=?, acknowledged_by=? WHERE id=?",
                      (now().isoformat(sep=" "), by, aid))
        return dict(c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone())


async def escalate_due() -> list[int]:
    """Muddati ötgan va tasdiqlanmagan ogohlantirişlarni boş şifokorga yuboradi."""
    t = now().isoformat(sep=" ")
    with session() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT a.*, p.full_name, p.district, p.phone FROM alerts a JOIN patients p ON p.id=a.patient_id
               WHERE a.acknowledged_at IS NULL AND a.escalated_at IS NULL AND a.due_at <= ?""", (t,))]
        for r in rows:
            c.execute("UPDATE alerts SET escalated_at=? WHERE id=?", (t, r["id"]))
    for r in rows:
        who = "Mutaxassis" if r["kind"] == "red_zone" else "Oilaviy şifokor"
        what = "qizil zona xabarini" if r["kind"] == "red_zone" else "aktiv çaqiruvni"
        await send(_env("TELEGRAM_HEAD_CHAT_ID") or _env("TELEGRAM_SPECIALIST_CHAT_ID"),
                   f"⏫ <b>ESKALATSIYA</b>\n{who} {what} öz vaqtida tasdiqlamadi.\n"
                   f"👤 {html.escape(r['full_name'])} · {html.escape(r['district'])} · 📞 {html.escape(r['phone'] or '-')}\n"
                   f"📝 {html.escape(r['message'] or '')}",
                   ("✅ Nazoratga oldim", f"ack:{r['id']}"))
    return [r["id"] for r in rows]


# ---------------- Fon vazifalari ----------------
async def poll_telegram(stop: asyncio.Event) -> None:
    """Tugma bosilişini qabul qiladi (webhook örniga — hakatonda server oçiq bölmasa ham işlaydi)."""
    offset = 0
    await tg("deleteWebhook")
    await setup_bot()
    while not stop.is_set():
        data = await tg("getUpdates", offset=offset, timeout=25, allowed_updates=["callback_query", "message"])
        for u in (data or {}).get("result", []):
            offset = u["update_id"] + 1
            cq = u.get("callback_query")
            if cq and cq.get("data", "").startswith("ack:"):
                user = cq["from"]
                by = (user.get("first_name", "") + " " + user.get("last_name", "")).strip() or str(user["id"])
                a = acknowledge(int(cq["data"][4:]), by)
                await tg("answerCallbackQuery", callback_query_id=cq["id"], text="Tasdiqlandi ✅")
                if a and cq.get("message"):
                    m = cq["message"]
                    await tg("editMessageText", chat_id=m["chat"]["id"], message_id=m["message_id"],
                             parse_mode="HTML",
                             text=html.escape(m.get("text", "")) + f"\n\n✅ <b>Tasdiqladi:</b> {html.escape(by)} · {now():%H:%M}")
            msg = u.get("message")
            if msg and msg.get("text", "").split("@")[0].split(" ")[0] in ("/start", "/app"):
                await send_welcome(msg["chat"])
        if not data:
            await asyncio.sleep(3)
        else:
            await asyncio.sleep(0)   # boşqa vazifalarga navbat beriş


async def status() -> dict:
    """Ulanişlar holati (/setup sahifasi uçun)."""
    token = _env("TELEGRAM_BOT_TOKEN")
    tgst = {"ok": False, "msg": "TELEGRAM_BOT_TOKEN yöq"}
    if token:
        me = await tg("getMe")
        if me and me.get("ok"):
            tgst = {"ok": True, "msg": "@" + me["result"]["username"]}
        elif me is None:
            tgst = {"ok": False, "msg": "api.telegram.org ga ulanib bölmadi (internet / VPN?)"}
        else:
            tgst = {"ok": False, "msg": "Token notöğri: " + str(me.get("description"))}
    cid = lambda k: bool(re.fullmatch(r"-?\d+", _env(k)))
    from .config import LOADED
    return {"gemini": bool(_env("GEMINI_API_KEY")), "telegram": tgst,
            "specialist_chat": cid("TELEGRAM_SPECIALIST_CHAT_ID"), "head_chat": cid("TELEGRAM_HEAD_CHAT_ID"),
            "webapp": webapp_url() or None, "escalate_minutes": escalate_minutes(),
            "active_call_minutes": active_call_minutes(), "files": LOADED}


async def startup_report() -> None:
    """run.bat oynasida aniq holat: nima ulangan, nima yöq."""
    ok, no = "  [OK] ", "  [--] "
    print("\n================ Uzilmas: ulanişlar tekşiruvi ================")
    from .config import CANDIDATES, LOADED
    if LOADED:
        print("  [OK] Sozlamalar fayli: " + LOADED[0])
    else:
        print("  [--] .env fayli TOPILMADI. Qidirilgan joylar:")
        for c in CANDIDATES[:2]:
            print("        " + str(c))
    print((ok if _env("GEMINI_API_KEY") else no) + "Gemini (tahlil rasmini öqiş)" +
          ("" if _env("GEMINI_API_KEY") else " — .env da GEMINI_API_KEY yöq"))
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        print(no + "Telegram — .env da TELEGRAM_BOT_TOKEN yöq")
    else:
        me = await tg("getMe")
        if me and me.get("ok"):
            print(ok + f"Telegram bot ulandi: @{me['result']['username']}")
        elif me is None:
            print(no + "Telegram: api.telegram.org ga ulanib bölmadi (internet / VPN / firewall?)")
        else:
            print(no + f"Telegram: token notöğri ({me.get('description')}) — BotFather dan qayta nusxalang")
    for key, name in (("TELEGRAM_SPECIALIST_CHAT_ID", "Mutaxassis guruhi"), ("TELEGRAM_HEAD_CHAT_ID", "Boş şifokor guruhi")):
        v = _env(key)
        good = bool(re.fullmatch(r"-?\d+", v))
        print((ok if good else no) + f"{name}: " + (v if good else "Chat ID yozilmagan (botga /start yuboring)"))
    print((ok if webapp_url() else no) + "Mini App: " + (webapp_url() or "WEBAPP_URL yöq (ixtiyoriy, https)"))
    print(f"  Eskalatsiya: {escalate_minutes():g} daqiqa · Aktiv çaqiruv: {active_call_minutes():g} daqiqa")
    print("  Sozlamalarni brauzerda kiritiş:  http://127.0.0.1:8000/setup")
    print("=============================================================\n", flush=True)


async def setup_bot() -> None:
    """Bot menyusi: buyruqlar va Mini App tugmasi (WEBAPP_URL berilgan bölsa)."""
    await tg("setMyCommands", commands=[
        {"command": "start", "description": "Boşlaş · Начать"},
        {"command": "app", "description": "Ilovani oçiş · Открыть приложение"},
    ])
    url = webapp_url()
    if url:
        await tg("setChatMenuButton", menu_button={"type": "web_app", "text": "Uzilmas", "web_app": {"url": url + "/app"}})


async def send_welcome(chat: dict) -> None:
    cid = str(chat["id"])
    text = ("👋 <b>Uzilmas</b> — bemor zanjiri uzilmaydi.\n"
            "Homilador ayolni hamşiradan oilaviy şifokorgaça nazorat qiluvçi platforma.\n\n"
            "👋 <b>Uzilmas</b> — цепочка помощи не прерывается.\n"
            "Платформа ведёт беременную от медсестры до семейного врача.\n\n"
            f"Chat ID: <code>{cid}</code>")
    url = webapp_url()
    rows = None
    if url:
        btn = ({"web_app": {"url": url + "/app"}} if chat.get("type") == "private" else {"url": url + "/app"})
        rows = [[{"text": "📱 Uzilmas ilovasini oçiş · Открыть", **btn}]]
    else:
        text += "\n\n⚠️ Mini App uçun .env da WEBAPP_URL (https) ni yozing."
    await send(cid, text, None, rows)


async def escalation_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await escalate_due()
        except Exception as e:  # fon vazifasi töxtab qolmasin
            log.exception("escalation: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except asyncio.TimeoutError:
            pass
