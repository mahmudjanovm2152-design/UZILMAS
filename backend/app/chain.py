"""
Uzilmas — "Jonli zanjir": bemor yölining 5 böğini va qayerda uzilgani.

  1. Patronaj taşrifi    — hamşira öz vaqtida kelganmi?
  2. Xavf baholaş        — ma'lumot töliqmi, zona aniqmi?
  3. Mutaxassis          — qizil zona bölsa, mutaxassis tasdiqladimi?
  4. Tuğruq muassasasi   — javob berildimi?
  5. Oilaviy şifokor     — aktiv çaqiruv 24 soatda bajarildimi?

Holatlar: ok (bajarildi), wait (kutilmoqda, muddat bor), broken (uzildi — kimdir harakat qilişi kerak),
next (hali navbati kelmagan), skip (bu bemorga kerak emas).
Matnlar ikki tilda: özbekça (yangi alifbo) va ruscha.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

# Patronaj oraliği (kun): xavf qança yuqori bölsa, taşrif şunça tez-tez
VISIT_INTERVAL = {"red": 7, "yellow": 14, "green": 28}
# Premium (pullik) paket: patronaj ikki baravar tez-tez
PREMIUM_INTERVAL = {"red": 3, "yellow": 7, "green": 14}


def interval_for(p: dict, zone: str) -> int:
    return (PREMIUM_INTERVAL if (p.get("plan") or "bepul") == "premium" else VISIT_INTERVAL)[zone]
ZONE_TXT = {"uz": {"red": "qizil", "yellow": "sariq", "green": "yaşil"},
            "ru": {"red": "красной", "yellow": "жёлтой", "green": "зелёной"}}
TITLES = {
    "nurse": ("Patronaj taşrifi", "Патронажный визит"),
    "assess": ("Xavf baholaş", "Оценка риска"),
    "specialist": ("Mutaxassis", "Специалист"),
    "hospital": ("Tuğruq muassasasi", "Роддом"),
    "doctor": ("Oilaviy şifokor", "Семейный врач"),
}
ACK_BY_RU = {"OvaBMU mutaxassisi": "специалист ОМД", "Oilaviy şifokor": "семейный врач",
             "Boş şifokor": "главный врач", "Telegram": "Telegram"}


def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("T", " ")[:19])
    except ValueError:
        return None


def _hm(s: Optional[str]) -> str:
    d = _dt(s)
    return d.strftime("%d.%m %H:%M") if d else "—"


def _alert_link(al: dict, now: datetime, who: str, lang: str) -> tuple[str, str, Optional[str]]:
    """Ogohlantiriş holatidan böğin holatini çiqaradi. who — "specialist" yoki "doctor"."""
    ru = lang == "ru"
    if al["acknowledged_at"]:
        by = al.get("acknowledged_by") or ""
        if ru:
            by = ACK_BY_RU.get(by, by)
        return "ok", (f"Подтвердил: {by} · {_hm(al['acknowledged_at'])}" if ru
                      else f"Tasdiqladi: {by} · {_hm(al['acknowledged_at'])}"), None
    if al.get("escalated_at"):
        if ru:
            w = "Специалист" if who == "specialist" else "Семейный врач"
            return "broken", f"{w} не подтвердил вовремя — передано главному врачу", None
        w = "Mutaxassis" if who == "specialist" else "Oilaviy şifokor"
        return "broken", f"{w} muddatda tasdiqlamadi — boş şifokorga kötarildi", None
    due = _dt(al["due_at"])
    if due and due < now:
        return "broken", (f"Срок подтверждения истёк ({_hm(al['due_at'])})" if ru
                          else f"Tasdiqlaş muddati ötdi ({_hm(al['due_at'])})"), None
    return "wait", (f"Ждём подтверждения · срок {_hm(al['due_at'])}" if ru
                    else f"Tasdiq kutilmoqda · muddat {_hm(al['due_at'])}"), al["due_at"]


def build(p: dict, visits: list[dict], a, alerts: list[dict],
          today: Optional[date] = None, now: Optional[datetime] = None, lang: str = "uz") -> dict:
    today = today or date.today()
    now = now or datetime.now()
    ru = lang == "ru"
    L = (lambda uz, r: r) if ru else (lambda uz, r: uz)
    zone = a.zone
    zt = ZONE_TXT["ru" if ru else "uz"][zone]
    alerts = sorted(alerts, key=lambda x: x["id"], reverse=True)
    red_al = next((x for x in alerts if x["kind"] == "red_zone"), None)
    call_al = next((x for x in alerts if x["kind"] == "active_call"), None)
    links = []

    def add(key, who, status, note, due=None):
        links.append(dict(key=key, title=TITLES[key][1 if ru else 0], who=who, status=status, note=note, due_at=due))

    # 1. Patronaj
    interval = interval_for(p, zone)
    nurse = p.get("nurse") or L("Hamşira", "Медсестра")
    last = visits[-1]["date"] if visits else None
    if not last:
        add("nurse", nurse, "broken", L("Birorta taşrif qayd etilmagan", "Ни одного визита не зарегистрировано"))
    else:
        days = (today - date.fromisoformat(last[:10])).days
        if days > interval:
            add("nurse", nurse, "broken",
                L(f"Oxirgi taşrif {days} kun oldin — {zt} zonada har {interval} kunda kerak",
                  f"Последний визит {days} дн. назад — в {zt} зоне нужен каждые {interval} дн."))
        else:
            when = L("bugun", "сегодня") if days == 0 else L(f"{days} kun oldin", f"{days} дн. назад")
            add("nurse", nurse, "ok",
                L(f"Oxirgi taşrif {when} · keyingisi {interval - days} kundan keyin",
                  f"Последний визит {when} · следующий через {interval - days} дн."))

    # 2. Baholaş
    who = L("Oçiq qoidalar + AI", "Открытые правила + AI")
    if a.needs_review:
        add("assess", who, "wait", L("Tekşiriş kerak: ", "Нужно проверить: ") + ", ".join(a.review(lang)))
    else:
        add("assess", who, "ok", L(f"Zona: {zt} · {len(a.findings)} ta xavf belgisi",
                                   f"Зона: {ZONE_TXT['ru'][zone].replace('ой', 'ая')} · признаков риска: {len(a.findings)}"))

    # 3. Mutaxassis
    who = L("OvaBMU mutaxassisi", "Специалист ОМД")
    if red_al and not red_al["acknowledged_at"]:
        st, note, due = _alert_link(red_al, now, "specialist", lang)
        if red_al.get("critical_at"):
            st, due = "broken", None
            note = L("KRITIK: javob yöq — oilaviy şifokor darhol bog‘lansin, kerak bölsa 103",
                     "КРИТИЧНО: нет ответа — семейный врач срочно связывается, при необходимости 103")
        add("specialist", who, st, note, due)
    elif zone == "red":
        if red_al:
            st, note, _ = _alert_link(red_al, now, "specialist", lang)
            add("specialist", who, st, note)
        else:
            add("specialist", who, "broken", L("Qizil zona, lekin mutaxassis xabardor qilinmagan",
                                              "Красная зона, но специалист не уведомлён"))
    else:
        add("specialist", who, "skip", L(f"Şart emas — {zt} zona", f"Не требуется — {ZONE_TXT['ru'][zone].replace('ой', 'ая')} зона"))

    # 4. Tuğruq muassasasi
    who = L("Statsionar", "Стационар")
    if p.get("status") == "discharged":
        add("hospital", who, "ok", L(f"Javob berildi · {_hm(p.get('discharged_at'))}", f"Выписана · {_hm(p.get('discharged_at'))}"))
    else:
        add("hospital", who, "next", L("Tuğruq kutilmoqda", "Ожидаются роды"))

    # 5. Oilaviy şifokor
    who = p.get("family_doctor") or L("Oilaviy şifokor", "Семейный врач")
    if call_al:
        st, note, due = _alert_link(call_al, now, "doctor", lang)
        add("doctor", who, st, note, due)
    elif p.get("status") == "discharged":
        add("doctor", who, "broken", L("Javob berilgan, lekin aktiv çaqiruv yuborilmagan",
                                       "Пациентка выписана, но активный вызов не отправлен"))
    else:
        add("doctor", who, "next", L("Javob berilgaç avtomatik ulanadi (24 soat)",
                                     "Подключится автоматически после выписки (24 часа)"))

    broken = [x for x in links if x["status"] == "broken"]
    waiting = [x for x in links if x["status"] == "wait"]
    status = "broken" if broken else "wait" if waiting else "ok"
    head = broken[0] if broken else waiting[0] if waiting else None
    return {"status": status, "links": links,
            "break_at": head["title"] if head else None, "break_key": head["key"] if head else None,
            "reason": head["note"] if head else None}
