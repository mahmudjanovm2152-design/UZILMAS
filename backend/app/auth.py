"""
Kiriş va rollar.

Har bir xodim öz login-paroli bilan kiradi; har bir rol faqat öz bölimini köradi:
  qabul     — Qabulxona: yangi bemorni yozadi, javobgar avtomatik biriktiriladi
  hamshira  — Patronaj hamşira: taşrif, ovoz/rasm orqali kiritiş
  shifokor  — Oilaviy şifokor / mutaxassis: signallar, aktiv çaqiruvlar, AI xulosa
  bosh      — Boş şifokor: hamma böllimlar + eskalatsiyalar
  bemor     — Pastient: öz kabineti, AI yordamçi, vizitlar

Parollar PBKDF2-SHA256 (tuz bilan) saqlanadi, ochiq holda emas.
Demo parollarni .env orqali almaştiriş mumkin: UZILMAS_PASS_<LOGIN>=...
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from .db import session

ROLES = {
    "qabul": ("Qabulxona", "Приёмная", "/reception"),
    "hamshira": ("Hamşira", "Медсестра", "/nurse"),
    "shifokor": ("Şifokor", "Врач", "/dashboard"),
    "bosh": ("Boş şifokor", "Главный врач", "/dashboard"),
    "bemor": ("Bemor", "Пациентка", "/patient"),
}

# Demo hisoblar (hakamlar va jamoa uçun). Ishlab çiqarişda — har bir xodimga alohida.
DEMO_USERS = [
    # login, parol, rol, F.I.Ş, bemor_id
    ("qabul", "Qabul2026", "qabul", "Dilnoza Karimova", None),
    ("hamshira", "Hamshira2026", "hamshira", "M. Ahmedova", None),
    ("shifokor", "Shifokor2026", "shifokor", "Dr. A. Sodiqov", None),
    ("bosh", "Bosh2026", "bosh", "Dr. N. Rahimova", None),
    ("bemor", "Bemor2026", "bemor", "Bahromova Naima", 101),
]

SESSION_HOURS = 12


def hash_password(pw: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120_000)
    return salt.hex() + "$" + dk.hex()


def check_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def seed_users() -> None:
    with session() as c:
        for login, pw, role, name, pid in DEMO_USERS:
            pw = os.environ.get(f"UZILMAS_PASS_{login.upper()}", pw)
            if c.execute("SELECT 1 FROM users WHERE username=?", (login,)).fetchone():
                continue
            c.execute("INSERT INTO users (username, pass_hash, role, full_name, patient_id) VALUES (?,?,?,?,?)",
                      (login, hash_password(pw), role, name, pid))


def login(username: str, password: str) -> Optional[dict]:
    with session() as c:
        u = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        if not u or not check_password(password, u["pass_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions (token, username) VALUES (?,?)", (token, u["username"]))
    return {"token": token, **public(dict(u))}


def public(u: dict) -> dict:
    r = ROLES[u["role"]]
    return {"username": u["username"], "role": u["role"], "full_name": u["full_name"],
            "patient_id": u.get("patient_id"), "role_uz": r[0], "role_ru": r[1], "home": r[2]}


def user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    with session() as c:
        row = c.execute("""SELECT u.*, s.created_at AS s_created FROM sessions s JOIN users u ON u.username=s.username
                           WHERE s.token=?""", (token,)).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["s_created"]) < datetime.now() - timedelta(hours=SESSION_HOURS):
            c.execute("DELETE FROM sessions WHERE token=?", (token,))
            return None
    return public(dict(row))


def logout(token: str) -> None:
    with session() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


def enabled() -> bool:
    return os.environ.get("UZILMAS_AUTH", "on").strip().lower() not in ("off", "0", "false")


# API yöllari: kim nimaga kira oladi
PUBLIC_API = ("/api/login", "/api/health", "/api/config", "/api/setup", "/api/public/", "/api/rules")
PATIENT_API = ("/api/me", "/api/logout", "/api/my/")


def allowed(role: str, path: str) -> bool:
    if role == "bemor":
        return path.startswith(PATIENT_API)
    return not path.startswith("/api/my/")   # xodimlar: bemor kabineti API sidan tashqari hammasi
