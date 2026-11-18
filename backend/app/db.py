"""SQLite ma'lumotlar bazasi (prototip uçun yetarli, keyin PostgreSQL)."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

def _writable(folder: Path) -> bool:
    """Papkaga haqiqatan yozib böladimi (Windows'da os.access işonçsiz)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".uzilmas_write_test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _default_db() -> Path:
    if os.environ.get("UZILMAS_DB"):
        return Path(os.environ["UZILMAS_DB"])
    here = Path(__file__).resolve().parent.parent
    if _writable(here):
        return here / "uzilmas.db"
    # Loyiha papkasiga yoziş taqiqlangan bölsa (antivirus/Defender) — foydalanuvçi papkasi
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Uzilmas"
    base.mkdir(parents=True, exist_ok=True)
    return base / "uzilmas.db"


DB_PATH = _default_db()

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    age             INTEGER,
    phone           TEXT,
    district        TEXT,
    mahalla         TEXT,
    lat             REAL,
    lon             REAL,
    multiple_pregnancy INTEGER DEFAULT 0,
    prev_preeclampsia  INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pregnant',   -- pregnant | discharged
    nurse           TEXT,
    family_doctor   TEXT,
    blood_group     TEXT,
    allergies       TEXT,
    discharged_at   TEXT,
    discharge_reason TEXT
);
CREATE TABLE IF NOT EXISTS visits (
    id              INTEGER PRIMARY KEY,
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    date            TEXT NOT NULL,
    ga_weeks        REAL,
    sbp             INTEGER,
    dbp             INTEGER,
    protein_g_l     REAL,
    hb_g_l          REAL,
    glucose_fasting REAL,
    symptoms        TEXT DEFAULT '[]',
    source          TEXT DEFAULT 'manual',     -- manual | photo | voice | offline
    client_id       TEXT UNIQUE,               -- offline navbatdagi yozuv ID si
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY,
    patient_id      INTEGER NOT NULL REFERENCES patients(id),
    kind            TEXT NOT NULL,             -- red_zone | active_call
    message         TEXT,
    recipient       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    due_at          TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    escalated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id, date);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as c:
        c.executescript(SCHEMA)


def row_to_visit_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["symptoms"] = json.loads(d.get("symptoms") or "[]")
    return d
