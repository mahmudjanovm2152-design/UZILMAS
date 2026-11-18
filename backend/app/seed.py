"""
Sintetik ma'lumotlar: Toşkent tumanlarida 100 nafar homilador ayol.
Heç qanday real şaxs ma'lumoti işlatilmaydi.

Işga tuşiriş:  python -m app.seed
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from datetime import date, datetime, timedelta

from . import rules
from .db import init_db, row_to_visit_dict, session, DB_PATH

# Toşkent tumanlari va taxminiy markaz koordinatalari
DISTRICTS = {
    "Yunusobod":       (41.3650, 69.2870),
    "Çilonzor":       (41.2750, 69.2040),
    "Mirzo Uluğbek":  (41.3380, 69.3350),
    "Yaşnobod":       (41.2900, 69.3340),
    "Şayxontohur":    (41.3270, 69.2400),
    "Olmazor":         (41.3530, 69.2200),
    "Sergeli":         (41.2250, 69.2200),
    "Uçtepa":         (41.2960, 69.1700),
    "Yakkasaroy":      (41.2900, 69.2600),
    "Mirobod":         (41.2950, 69.2850),
    "Bektemir":        (41.2090, 69.3340),
    "Yangihayot":      (41.2000, 69.2500),
    "Yangi Toşkent":   (41.2500, 69.3000),
}

# Tumanlar çegarasi (OpenStreetMap, ODbL) — bemor nuqtalari aynan tuman içiga tuşadi
_GEO = Path(__file__).resolve().parents[2] / "frontend" / "tashkent_districts.geojson"


def _polys() -> dict:
    try:
        g = json.loads(_GEO.read_text(encoding="utf-8"))
    except OSError:
        return {}
    out = {}
    for f in g["features"]:
        geom = f["geometry"]
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        out[f["properties"]["name"]] = rings
    return out


def _inside(x: float, y: float, ring: list) -> bool:
    ins = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            ins = not ins
        j = i
    return ins


def _point(rng: random.Random, district: str, polys: dict) -> tuple[float, float]:
    rings = polys.get(district)
    if not rings:
        lat, lon = DISTRICTS[district]
        return lat + rng.uniform(-0.018, 0.018), lon + rng.uniform(-0.022, 0.022)
    xs = [c[0] for r in rings for c in r]; ys = [c[1] for r in rings for c in r]
    for _ in range(2000):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if any(_inside(x, y, r) for r in rings):
            return y, x
    lat, lon = DISTRICTS[district]
    return lat, lon
MAHALLAS = ["Navröz", "Boğişamol", "Ming örik", "Guliston", "Döstlik", "Obod",
            "Istiqlol", "Mehrjon", "Bunyodkor", "Tinçlik", "Nurafşon", "Yangi hayot"]
FIRST = ["Dilnoza", "Madina", "Nigora", "Şahnoza", "Gulnora", "Malika", "Zarina", "Feruza",
         "Sevara", "Mohira", "Nodira", "Dildora", "Kamola", "Lola", "Umida", "Barno",
         "Saida", "Muxlisa", "Ozoda", "Nilufar", "Gulçehra", "Şoira", "Zilola", "Mavluda"]
LAST = ["Karimova", "Rahimova", "Toşpölatova", "Yusupova", "Aliyeva", "Ismoilova",
        "Nazarova", "Qodirova", "Ergaşeva", "Mirzayeva", "Saidova", "Hasanova",
        "Abdullayeva", "Xolmatova", "Sobirova", "Jörayeva"]
NURSES = ["M. Ahmedova", "G. Usmonova", "S. Rasulova", "N. Tursunova"]
DOCTORS = ["Dr. A. Sodiqov", "Dr. F. Xudoyberdiyeva", "Dr. B. Qosimov", "Dr. Z. Mamatova"]
BLOOD = ["O(I) Rh+", "A(II) Rh+", "B(III) Rh+", "AB(IV) Rh+", "O(I) Rh-", "A(II) Rh-"]


def _profile(rnd: random.Random, kind: str, n_visits: int):
    """Har bir taşrif uçun körsatkiçlar. kind: normal | anemia_trend | htn | pe | gdm."""
    visits = []
    base_sbp = rnd.randint(105, 125)
    base_hb = rnd.randint(115, 130)
    for i in range(n_visits):
        sbp = base_sbp + rnd.randint(-5, 5)
        dbp = int(sbp * 0.63) + rnd.randint(-3, 3)
        hb = base_hb + rnd.randint(-3, 3)
        prot = 0.0 if rnd.random() < 0.8 else round(rnd.uniform(0.05, 0.2), 2)
        glu = round(rnd.uniform(4.0, 4.9), 1)
        symptoms: list[str] = []
        last = i == n_visits - 1
        if kind == "anemia_trend":
            hb = base_hb - 4 * i - rnd.randint(0, 1)
        elif kind == "htn" and i >= n_visits - 2:
            sbp, dbp = rnd.randint(140, 154), rnd.randint(90, 100)
        elif kind == "pe" and last:
            sbp, dbp, prot = rnd.randint(148, 165), rnd.randint(96, 112), round(rnd.uniform(0.4, 1.5), 2)
            if rnd.random() < 0.5:
                symptoms = ["severe_headache"]
        elif kind == "gdm" and i >= n_visits - 2:
            glu = round(rnd.uniform(5.2, 6.4), 1)
        visits.append(dict(sbp=sbp, dbp=dbp, hb_g_l=hb, protein_g_l=prot,
                           glucose_fasting=glu, symptoms=symptoms))
    return visits


def seed(n: int = 100, rng_seed: int = 17) -> None:
    rnd = random.Random(rng_seed)
    geo_rng = random.Random(rng_seed + 1)
    polys = _polys()
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    today = date.today()
    kinds = (["normal"] * 72 + ["anemia_trend"] * 8 + ["htn"] * 8 + ["pe"] * 5 + ["gdm"] * 7)
    with session() as c:
        for pid in range(1, n + 1):
            district = rnd.choice(list(DISTRICTS))
            lat, lon = _point(geo_rng, district, polys)
            rnd.random(); rnd.random()   # avvalgi tasodifiy ketma-ketlik saqlansin
            age = rnd.choice([17] + list(range(19, 35)) * 4 + [36, 38, 40])
            kind = kinds[(pid - 1) % len(kinds)]
            c.execute(
                """INSERT INTO patients (id, full_name, age, phone, district, mahalla, lat, lon,
                       multiple_pregnancy, prev_preeclampsia, nurse, family_doctor, blood_group, allergies)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", age,
                 f"+998 9{rnd.randint(0, 9)} {rnd.randint(100, 999)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}",
                 district, rnd.choice(MAHALLAS),
                 lat, lon,
                 int(rnd.random() < 0.04), int(rnd.random() < 0.05),
                 rnd.choice(NURSES), rnd.choice(DOCTORS), rnd.choice(BLOOD),
                 rnd.choice(["Yöq"] * 8 + ["Penitsillin", "Sulfanilamidlar"])))

            n_visits = rnd.randint(3, 6)
            start_ga = rnd.randint(8, 20)
            first_day = today - timedelta(weeks=3 * (n_visits - 1)) - timedelta(days=rnd.randint(0, 10))
            for i, v in enumerate(_profile(rnd, kind, n_visits)):
                c.execute(
                    """INSERT INTO visits (patient_id, date, ga_weeks, sbp, dbp, protein_g_l, hb_g_l,
                           glucose_fasting, symptoms, source) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (pid, (first_day + timedelta(weeks=3 * i)).isoformat(), start_ga + 3 * i,
                     v["sbp"], v["dbp"], v["protein_g_l"], v["hb_g_l"], v["glucose_fasting"],
                     json.dumps(v["symptoms"]), "manual"))
        if n >= 50:   # testlarda (kiçik n) ssenariylar qöşilmaydi
            _chain_scenarios(c, today, rnd, n)
        _demo_patients(c, today, polys)
        _appointments(c, rnd, n)
    print(f"OK: {n} + 3 demo bemor yaratildi -> {DB_PATH}")


def _zone(c, pid: int) -> str:
    p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    vs = [row_to_visit_dict(r) for r in c.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY date, id", (pid,))]
    pt = rules.Patient(age=p["age"], multiple_pregnancy=bool(p["multiple_pregnancy"]),
                       prev_preeclampsia=bool(p["prev_preeclampsia"]))
    return rules.assess(pt, [rules.Visit(date=v["date"], ga_weeks=v.get("ga_weeks"), sbp=v.get("sbp"), dbp=v.get("dbp"),
                                         protein_g_l=v.get("protein_g_l"), hb_g_l=v.get("hb_g_l"),
                                         glucose_fasting=v.get("glucose_fasting"), symptoms=v.get("symptoms") or [])
                             for v in vs])


def _chain_scenarios(c, today, rnd, n: int) -> None:
    """Real hayotdagi holat: zanjirning köp qismi işlaydi, lekin ba'zi böğinlar uzilgan."""
    ts = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")
    nowdt = datetime.now().replace(microsecond=0)
    assess = {pid: _zone(c, pid) for pid in range(1, n + 1)}
    zones = {pid: a.zone for pid, a in assess.items()}
    reds = [pid for pid, z in zones.items() if z == "red"]
    for i, pid in enumerate(reds):
        if i in (1, 4):   # mutaxassis tasdiqlamagan -> boş şifokorga kötarilgan (zanjir uzilgan)
            c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, created_at, due_at, escalated_at)
                         VALUES (?,?,?,?,?,?,?)""",
                      (pid, "red_zone", assess[pid].summary_uz, "specialist", ts(nowdt - timedelta(hours=7)),
                       ts(nowdt - timedelta(hours=6)), ts(nowdt - timedelta(hours=6))))
        else:             # mutaxassis öz vaqtida tasdiqlagan
            t = nowdt - timedelta(days=rnd.randint(1, 5), hours=rnd.randint(1, 8))
            c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, created_at, due_at,
                             acknowledged_at, acknowledged_by) VALUES (?,?,?,?,?,?,?,?)""",
                      (pid, "red_zone", assess[pid].summary_uz, "specialist", ts(t), ts(t + timedelta(minutes=30)),
                       ts(t + timedelta(minutes=rnd.randint(4, 25))), "OvaBMU mutaxassisi"))
    others = [pid for pid, z in zones.items() if z != "red"]
    # Patronaj keçikkan bemorlar (hamşira bormagan)
    for pid in others[5::19][:4]:
        shift = 20 if zones[pid] == "yellow" else 34
        c.execute("UPDATE visits SET date = date(date, ?) WHERE patient_id=?", (f"-{shift} days", pid))
    # Tuğruqdan keyin javob berilgan bemorlar: biri töliq zanjir, biri oilaviy şifokorda uzilgan
    done_pid, late_pid = others[2], others[11]
    for pid, ok in ((done_pid, True), (late_pid, False)):
        d = nowdt - timedelta(days=2 if ok else 3)
        c.execute("UPDATE patients SET status='discharged', discharged_at=?, discharge_reason=? WHERE id=?",
                  (ts(d), "postpartum", pid))
        if ok:
            c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, created_at, due_at,
                             acknowledged_at, acknowledged_by) VALUES (?,?,?,?,?,?,?,?)""",
                      (pid, "active_call", "", "family_doctor",
                       ts(d), ts(d + timedelta(hours=24)), ts(d + timedelta(hours=9)), "Oilaviy şifokor"))
        else:
            c.execute("""INSERT INTO alerts (patient_id, kind, message, recipient, created_at, due_at, escalated_at)
                         VALUES (?,?,?,?,?,?,?)""",
                      (pid, "active_call", "", "family_doctor",
                       ts(d), ts(d + timedelta(hours=24)), ts(d + timedelta(hours=24))))


# Demo uçun 3 bemor: tahlil rasmlari demo/ papkasida (namuna blankalar)
DEMO = [
    # id, ism, yoş, tuman, oldingi taşriflar (sbp, dbp, hb)
    (101, "Bahromova Naima", 26, "Yunusobod", [(112, 72, 121), (116, 74, 119), (118, 76, 118)]),
    (102, "Akbarxodjayeva Aziza", 29, "Mirzo Uluğbek", [(110, 70, 124), (112, 70, 123)]),
    (103, "Gulyamova Farzona", 31, "Çilonzor", [(114, 72, 120), (113, 71, 121)]),
]


def _demo_patients(c, today, polys=None) -> None:
    drng = random.Random(101)
    for pid, name, age, district, hist in DEMO:
        lat, lon = _point(drng, district, polys or {})
        c.execute(
            """INSERT INTO patients (id, full_name, age, phone, district, mahalla, lat, lon,
                   nurse, family_doctor, blood_group, allergies)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, name, age, "+998 90 000 00 00", district, "Navröz", lat, lon,
             "M. Ahmedova", "Dr. A. Sodiqov", "A(II) Rh+", "Yöq"))
        for i, (sbp, dbp, hb) in enumerate(hist):
            d = today - timedelta(weeks=3 * (len(hist) - i))
            c.execute(
                """INSERT INTO visits (patient_id, date, ga_weeks, sbp, dbp, protein_g_l, hb_g_l,
                       glucose_fasting, symptoms, source) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, d.isoformat(), 24 + 3 * i, sbp, dbp, 0.0, hb, 4.6, "[]", "manual"))


def _appointments(c, rnd, n: int) -> None:
    """Qabullar: bepul va premium (50% oldindan), ba'zilari kelmagan — "jim qoliş xavfi" uçun real manzara."""
    nowdt = datetime.now().replace(second=0, microsecond=0)
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M")
    for pid in range(1, n + 1):
        premium = rnd.random() < 0.3
        price = 550_000 if premium else 0
        if premium:
            c.execute("UPDATE patients SET plan='premium' WHERE id=?", (pid,))
        if rnd.random() < 0.18:   # oldingi qabulga kelmagan
            c.execute("INSERT INTO appointments (patient_id, at, plan, price, prepaid, status, created_by) VALUES (?,?,?,?,?,?,?)",
                      (pid, fmt(nowdt - timedelta(days=rnd.randint(3, 12), hours=-10)), "premium" if premium else "bepul",
                       price, price // 2, "no_show", "Qabulxona"))
        c.execute("INSERT INTO appointments (patient_id, at, plan, price, prepaid, created_by) VALUES (?,?,?,?,?,?)",
                  (pid, fmt((nowdt + timedelta(days=rnd.randint(1, 14))).replace(hour=rnd.choice([9, 10, 11, 14, 15]), minute=0)),
                   "premium" if premium else "bepul", price, price // 2, "Qabulxona"))
    # Demo bemor (kabinet): premium, 3 kundan keyin qabul, 50% tölangan
    c.execute("UPDATE patients SET plan='premium' WHERE id=101")
    c.execute("DELETE FROM appointments WHERE patient_id IN (101,102,103)")
    c.execute("INSERT INTO appointments (patient_id, at, plan, price, prepaid, created_by) VALUES (?,?,?,?,?,?)",
              (101, fmt((nowdt + timedelta(days=3)).replace(hour=10, minute=0)), "premium", 550_000, 275_000, "Qabulxona"))


if __name__ == "__main__":
    seed()
