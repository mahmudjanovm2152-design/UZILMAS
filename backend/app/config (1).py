"""`.env` faylini öqiş (qöşimça kutubxonasiz).

Windows Bloknoti bilan saqlangan faylni ham to'g'ri öqiydi: BOM, qatordagi izohlar (# ...),
qöştirnoqlar va ortiqça böşliqlar olib taşlanadi.
"""
import os
import re
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+[#(]", v.strip(), maxsplit=1)[0]      # "2   # izoh" -> "2"
        v = v.strip().strip('"').strip("'").strip()
        os.environ.setdefault(k.strip().lstrip("﻿"), v)
