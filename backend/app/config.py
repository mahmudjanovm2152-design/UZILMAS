"""`.env` faylini öqiş (qöşimça kutubxonasiz).

Windows Bloknoti bilan saqlangan faylni ham to'g'ri öqiydi: BOM, qatordagi izohlar (# ...),
qöştirnoqlar va ortiqça böşliqlar olib taşlanadi.
"""
import os
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND / ".env"
# Qidiriladigan joylar: Windowsda Bloknot ".env.txt" qilib saqlab qöyişi mumkin
USER_ENV = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Uzilmas" / ".env"   # /setup sahifasi shu yerga yozadi
CANDIDATES = [USER_ENV, BACKEND / ".env", BACKEND / ".env.txt", BACKEND / "env.txt", BACKEND / "env",
              BACKEND.parent / ".env", BACKEND.parent / ".env.txt"]
LOADED: list = []     # qaysi fayl öqilgani (run.bat oynasida körsatiladi)


def load_env(path: Path = None) -> None:
    for p in ([path] if path else CANDIDATES):     # hammasi öqiladi; birinçi topilgan qiymat ustun
        if p and p.exists() and p.is_file():
            _read(p)
            LOADED.append(str(p))


SETUP_KEYS = ["CRITICAL_MINUTES", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_SPECIALIST_CHAT_ID", "TELEGRAM_DOCTOR_CHAT_ID",
              "TELEGRAM_HEAD_CHAT_ID", "WEBAPP_URL", "ESCALATE_MINUTES", "ACTIVE_CALL_MINUTES", "AISHA_API_KEY", "CARTO_API_KEY"]


def save_user_env(values: dict) -> Path:
    """Brauzerdagi /setup formasidan kelgan qiymatlarni saqlaydi va darhol qöllaydi."""
    cur = {}
    if USER_ENV.exists():
        for line in USER_ENV.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
    for k, v in values.items():
        if k in SETUP_KEYS and v is not None:
            v = str(v).strip()
            if "=" in v and k != "WEBAPP_URL":          # "KALIT = 123" deb yozilsa — faqat qiymat olinadi
                v = v.split("=", 1)[1]
            v = v.strip().strip('"').strip("'").strip()
            if v:
                cur[k] = v
                os.environ[k] = v
    USER_ENV.parent.mkdir(parents=True, exist_ok=True)
    USER_ENV.write_text("# Uzilmas sozlamalari (/setup sahifasidan yozilgan)\n" +
                        "\n".join(f"{k}={v}" for k, v in cur.items()) + "\n", encoding="utf-8")
    if str(USER_ENV) not in LOADED:
        LOADED.insert(0, str(USER_ENV))
    return USER_ENV


def _read(path: Path) -> None:
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+[#(]", v.strip(), maxsplit=1)[0]      # "2   # izoh" -> "2"
        v = v.strip().strip('"').strip("'").strip()
        os.environ.setdefault(k.strip().lstrip("﻿"), v)
