"""
Uzilmas — xavf zonasi qoidalari (rules engine).

Asosiy tamoyil:
  * Zonani QOIDALAR belgilaydi, AI emas. Har bir qoida oçiq, versiyalangan
    va manbaga ega.
  * Noma'lum qiymat heç qaçon "norma" deb hisoblanmaydi: muhim körsatkiç
    noma'lum bölsa, ayol yaşil zonaga tuşmaydi va "tekşiriş kerak"
    belgisi qöyiladi.
  * Dinamika: körsatkiç ketma-ket yomonlaşsa, zona bir poğona kötariladi.
  * Bu tizim şifokor qarorini qöllab-quvvatlaydi, taşxis qöymaydi.

DIQQAT: çegaralar hakaton prototipi uçun JSST (WHO) tavsiyalari va
homiladorlikdagi gipertenziya böyiça klinik protokollar asosida olingan.
Amaliyotda qöllaşdan oldin akuşer-ginekolog tomonidan tasdiqlanişi şart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

RULES_VERSION = "2026.11-v1"

GREEN, YELLOW, RED = "green", "yellow", "red"
_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}
_BY_RANK = {v: k for k, v in _ORDER.items()}

SRC_HTN = "Homiladorlikdagi arterial gipertenziya klinik protokoli (SAD/DAD çegaralari, proteinuriya ≥0,3 g/l)"
SRC_WHO_HB = "JSST (WHO): homiladorlikda anemiya — Hb < 110 g/l, oğir anemiya — Hb < 70 g/l"
SRC_WHO_GDM = "JSST (WHO) 2013: homiladorlik diabeti — oç qoringa glyukoza ≥ 5,1 mmol/l; ≥ 7,0 — manifest diabet"
SRC_DANGER = "JSST (WHO): homiladorlikdagi xavfli belgilar (danger signs)"
SRC_RISK = "Perinatal xavf omillari (yoş, köp homilalik, oldingi asoratlar)"
SRC_TREND = "Uzilmas dinamika qoidasi (3 taşrif ketma-ket yomonlaşiş)"

# Manbalar ruscha
SRC_RU = {
    SRC_HTN: "Клинический протокол «Артериальная гипертензия при беременности» (пороги САД/ДАД, протеинурия ≥0,3 г/л)",
    SRC_WHO_HB: "ВОЗ: анемия при беременности — Hb < 110 г/л, тяжёлая анемия — Hb < 70 г/л",
    SRC_WHO_GDM: "ВОЗ, 2013: гестационный диабет — глюкоза натощак ≥ 5,1 ммоль/л; ≥ 7,0 — манифестный диабет",
    SRC_DANGER: "ВОЗ: опасные признаки при беременности (danger signs)",
    SRC_RISK: "Перинатальные факторы риска (возраст, многоплодие, осложнения в анамнезе)",
    SRC_TREND: "Правило динамики Uzilmas (ухудшение 3 визита подряд)",
}
REVIEW_RU = {"qon bosimi": "артериальное давление", "gemoglobin": "гемоглобин",
             "taşrif ma'lumotlari yöq": "нет данных о визитах"}

# Xavfli belgilar: kalit -> özbekça nom
DANGER_SIGNS = {
    "severe_headache": "kuçli boş oğriği",
    "blurred_vision": "köriş xiralaşişi",
    "vaginal_bleeding": "qindan qon ketişi",
    "convulsions": "tutqanoq (talvasa)",
    "reduced_fetal_movement": "homila harakati kamaygan",
    "severe_abdominal_pain": "qorinda kuçli oğriq",
    "high_fever": "yuqori isitma",
}
DANGER_SIGNS_RU = {
    "severe_headache": "сильная головная боль",
    "blurred_vision": "нарушение зрения",
    "vaginal_bleeding": "влагалищное кровотечение",
    "convulsions": "судороги",
    "reduced_fetal_movement": "снижение шевелений плода",
    "severe_abdominal_pain": "сильная боль в животе",
    "high_fever": "высокая температура",
}


@dataclass
class Visit:
    date: str
    ga_weeks: Optional[float] = None          # homiladorlik muddati (hafta)
    sbp: Optional[int] = None                 # sistolik bosim
    dbp: Optional[int] = None                 # diastolik bosim
    protein_g_l: Optional[float] = None       # siydikda oqsil (g/l)
    hb_g_l: Optional[float] = None            # gemoglobin (g/l)
    glucose_fasting: Optional[float] = None   # oç qoringa glyukoza (mmol/l)
    symptoms: list[str] = field(default_factory=list)


@dataclass
class Patient:
    age: Optional[int] = None
    multiple_pregnancy: bool = False
    prev_preeclampsia: bool = False


@dataclass
class Finding:
    rule_id: str
    level: str
    reason_uz: str
    source: str
    reason_ru: str = ""

    def reason(self, lang: str = "uz") -> str:
        return self.reason_ru if lang == "ru" and self.reason_ru else self.reason_uz

    def as_dict(self, lang: str = "uz") -> dict:
        return {"rule_id": self.rule_id, "level": self.level, "reason": self.reason(lang),
                "source": SRC_RU.get(self.source, self.source) if lang == "ru" else self.source}


@dataclass
class Assessment:
    zone: str
    findings: list[Finding]
    needs_review: list[str]        # tekşirilişi kerak bölgan körsatkiçlar
    trend_raised: bool
    rules_version: str = RULES_VERSION

    def review(self, lang: str = "uz") -> list[str]:
        return [REVIEW_RU.get(x, x) for x in self.needs_review] if lang == "ru" else list(self.needs_review)

    def summary(self, lang: str = "uz") -> str:
        if not self.findings and not self.needs_review:
            return "Признаки риска не выявлены." if lang == "ru" else "Xavf belgilari aniqlanmadi."
        parts = [f.reason(lang) for f in self.findings]
        if self.needs_review:
            parts.append(("Нужно проверить: " if lang == "ru" else "Tekşiriş kerak: ") + ", ".join(self.review(lang)))
        return "; ".join(parts)

    @property
    def summary_uz(self) -> str:
        return self.summary("uz")

    def as_dict(self, lang: str = "uz") -> dict:
        return {
            "zone": self.zone,
            "summary": self.summary(lang),
            "findings": [f.as_dict(lang) for f in self.findings],
            "needs_review": self.review(lang),
            "trend_raised": self.trend_raised,
            "rules_version": self.rules_version,
        }


def _raise(zone: str, levels: int = 1) -> str:
    return _BY_RANK[min(_ORDER[zone] + levels, _ORDER[RED])]


def _max(*zones: str) -> str:
    return max(zones, key=lambda z: _ORDER[z])


def _visit_findings(v: Visit) -> list[Finding]:
    f: list[Finding] = []
    sbp, dbp, prot = v.sbp, v.dbp, v.protein_g_l
    htn = (sbp is not None and sbp >= 140) or (dbp is not None and dbp >= 90)
    severe_htn = (sbp is not None and sbp >= 160) or (dbp is not None and dbp >= 110)
    bp_txt = f"{sbp if sbp is not None else '?'}/{dbp if dbp is not None else '?'}"

    # --- Qon bosimi va preeklampsiya ---
    if severe_htn:
        f.append(Finding("R-BP-SEVERE", RED,
                         f"Oğir gipertenziya: bosim {bp_txt} (≥160/110)", SRC_HTN,
                         f"Тяжёлая гипертензия: давление {bp_txt} (≥160/110)"))
    if htn and prot is not None and prot >= 0.3:
        f.append(Finding("R-PE", RED,
                         f"Preeklampsiya xavfi: bosim {bp_txt} + siydikda oqsil {prot} g/l", SRC_HTN,
                         f"Риск преэклампсии: давление {bp_txt} + белок в моче {prot} г/л"))
    elif htn and not severe_htn:
        f.append(Finding("Y-BP", YELLOW,
                         f"Gipertenziya: bosim {bp_txt} (140–159 / 90–109)", SRC_HTN,
                         f"Гипертензия: давление {bp_txt} (140–159 / 90–109)"))
    if not htn and prot is not None and prot >= 0.3:
        f.append(Finding("Y-PROT", YELLOW,
                         f"Siydikda oqsil {prot} g/l (bosim normal)", SRC_HTN,
                         f"Белок в моче {prot} г/л (давление в норме)"))

    # --- Gemoglobin ---
    if v.hb_g_l is not None:
        if v.hb_g_l < 70:
            f.append(Finding("R-HB-SEVERE", RED, f"Oğir anemiya: Hb {v.hb_g_l:g} g/l (<70)", SRC_WHO_HB,
                             f"Тяжёлая анемия: Hb {v.hb_g_l:g} г/л (<70)"))
        elif v.hb_g_l < 110:
            f.append(Finding("Y-HB", YELLOW, f"Anemiya: Hb {v.hb_g_l:g} g/l (<110)", SRC_WHO_HB,
                             f"Анемия: Hb {v.hb_g_l:g} г/л (<110)"))

    # --- Glyukoza ---
    if v.glucose_fasting is not None:
        if v.glucose_fasting >= 7.0:
            f.append(Finding("R-GLU", RED,
                             f"Glyukoza {v.glucose_fasting:g} mmol/l (≥7,0)", SRC_WHO_GDM,
                             f"Глюкоза {v.glucose_fasting:g} ммоль/л (≥7,0)"))
        elif v.glucose_fasting >= 5.1:
            f.append(Finding("Y-GDM", YELLOW,
                             f"Homiladorlik diabeti xavfi: glyukoza {v.glucose_fasting:g} mmol/l (≥5,1)",
                             SRC_WHO_GDM, f"Риск гестационного диабета: глюкоза {v.glucose_fasting:g} ммоль/л (≥5,1)"))

    # --- Xavfli belgilar ---
    for s in v.symptoms:
        if s in DANGER_SIGNS:
            f.append(Finding(f"R-DANGER-{s}", RED, f"Xavfli belgi: {DANGER_SIGNS[s]}", SRC_DANGER,
                             f"Опасный признак: {DANGER_SIGNS_RU[s]}"))
    return f


def _patient_findings(p: Patient) -> list[Finding]:
    f: list[Finding] = []
    if p.age is not None and (p.age < 18 or p.age > 35):
        f.append(Finding("Y-AGE", YELLOW, f"Yoş xavf omili: {p.age} yoş", SRC_RISK,
                         f"Возрастной фактор риска: {p.age} лет"))
    if p.multiple_pregnancy:
        f.append(Finding("Y-MULTI", YELLOW, "Köp homilalik", SRC_RISK, "Многоплодная беременность"))
    if p.prev_preeclampsia:
        f.append(Finding("Y-PREV-PE", YELLOW, "Oldingi homiladorlikda preeklampsiya", SRC_RISK,
                         "Преэклампсия в предыдущей беременности"))
    return f


def _worsening(values: list[Optional[float]], direction: int, min_change: float) -> bool:
    """Oxirgi 3 qiymat ketma-ket yomonlaşganmi (direction=-1: kamaymoqda, +1: oşmoqda)."""
    vals = [x for x in values if x is not None][-3:]
    if len(vals) < 3:
        return False
    steps = all((b - a) * direction > 0 for a, b in zip(vals, vals[1:]))
    return steps and abs(vals[-1] - vals[0]) >= min_change


def assess(patient: Patient, visits: list[Visit]) -> Assessment:
    """Bemorni barça taşriflari böyiça baholaydi. Zonani oxirgi taşrif belgilaydi."""
    if not visits:
        return Assessment(YELLOW, [], ["taşrif ma'lumotlari yöq"], False)

    visits = sorted(visits, key=lambda v: v.date)
    last = visits[-1]
    findings = _visit_findings(last) + _patient_findings(patient)

    zone = GREEN
    for fi in findings:
        zone = _max(zone, fi.level)

    # Noma'lum qiymat heç qaçon "norma" emas
    needs_review = []
    if last.sbp is None or last.dbp is None:
        needs_review.append("qon bosimi")
    if last.hb_g_l is None:
        needs_review.append("gemoglobin")
    if needs_review and zone == GREEN:
        zone = YELLOW

    # Dinamika
    trend_raised = False
    trend_msgs = []
    if _worsening([v.hb_g_l for v in visits], -1, 10):
        trend_msgs.append(("gemoglobin 3 taşrif ketma-ket kamaymoqda", "гемоглобин снижается 3 визита подряд"))
    if _worsening([v.sbp for v in visits], +1, 15) and (last.sbp or 0) >= 130:
        trend_msgs.append(("sistolik bosim 3 taşrif ketma-ket oşmoqda", "систолическое давление растёт 3 визита подряд"))
    if trend_msgs and zone != RED:
        zone = _raise(zone)
        trend_raised = True
    for m_uz, m_ru in trend_msgs:
        findings.append(Finding("T-TREND", zone if trend_raised else RED,
                                f"Salbiy dinamika: {m_uz}", SRC_TREND, f"Отрицательная динамика: {m_ru}"))

    # Qizil topilmalar birinçi
    findings.sort(key=lambda x: -_ORDER[x.level])
    return Assessment(zone, findings, needs_review, trend_raised)
