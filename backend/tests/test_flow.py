"""Töliq demo zanjiri: qizil zona -> ogohlantiriş -> eskalatsiya; javob beriş -> aktiv çaqiruv; ovoz; offline."""
import importlib
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UZILMAS_DB", str(tmp_path / "t.db"))
    for k in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "AISHA_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("ESCALATE_MINUTES", "0")         # darhol eskalatsiya (test uçun)
    monkeypatch.setenv("UZILMAS_AUTH", "off")
    from app import db, seed, notify, main
    for m in (db, seed, notify, main):
        importlib.reload(m)
    seed.seed(n=10)
    with TestClient(main.app) as c:
        yield c


RED = {"date": "2026-11-18", "ga_weeks": 33, "sbp": 152, "dbp": 98, "protein_g_l": 0.6, "hb_g_l": 112}


def test_red_creates_single_alert(client):
    r = client.post("/api/patients/101/visits", json=RED).json()
    assert r["zone_after"] == "red" and r["alert_id"]
    r2 = client.post("/api/patients/101/visits", json={**RED, "date": "2026-11-19"}).json()
    assert r2["alert_id"] == r["alert_id"]          # oçiq ogohlantiriş takrorlanmaydi
    assert client.get("/api/stats").json()["open_alerts"] == 1


def test_green_visit_no_alert(client):
    r = client.post("/api/patients/102/visits", json={"date": "2026-11-18", "sbp": 112, "dbp": 70, "hb_g_l": 124}).json()
    assert r["zone_after"] == "green" and r["alert_id"] is None


def test_escalation_and_ack(client):
    aid = client.post("/api/patients/101/visits", json=RED).json()["alert_id"]
    assert aid in client.post("/api/alerts/escalate-now").json()["escalated"]
    a = client.post(f"/api/alerts/{aid}/ack", json={"by": "Dr. Test"}).json()
    assert a["acknowledged_by"] == "Dr. Test" and a["escalated_at"]
    assert client.get("/api/stats").json()["open_alerts"] == 0


def test_discharge_active_call(client):
    r = client.post("/api/patients/103/discharge", json={"reason": "Tuğruqdan keyin", "notes": "çaqaloq 3200 g"}).json()
    assert r["status"] == "discharged" and r["active_call"]["kind"] == "active_call"
    tasks = client.get("/api/doctor/tasks").json()
    assert tasks and tasks[0]["full_name"] == "Gulyamova Farzona"
    assert client.get("/api/stats").json()["discharged"] == 1


def test_voice_text_uzbek_words(client):
    t = "bosim yuz ellik ikki ga töqson sakkiz, gemoglobin yuz ön ikki, siydikda oqsil nol butun olti, boş oğriği bor"
    d = client.post("/api/patients/101/voice-text", json={"text": t}).json()
    v = d["draft_visit"]
    assert (v["sbp"], v["dbp"], v["hb_g_l"], v["protein_g_l"]) == (152, 98, 112.0, 0.6)
    assert "severe_headache" in v["symptoms"]
    assert d["preview_assessment"]["zone"] == "red"
    assert d["extraction"]["parser"] == "rules"     # Gemini kalitisiz ham işlaydi


def test_offline_queue_dedup(client):
    cid = str(uuid.uuid4())
    body = {**RED, "source": "offline", "client_id": cid}
    client.post("/api/patients/101/visits", json=body)
    r = client.post("/api/patients/101/visits", json=body).json()
    assert r.get("duplicate") is True
    n = len(client.get("/api/patients/101").json()["visits"])
    assert n == 4   # 3 ta tarixiy + 1 ta yangi (takror yozilmadi)


def test_pages_served(client):
    for p in ("/", "/dashboard", "/nurse", "/doctor", "/sw.js", "/static/uzilmas.css"):
        assert client.get(p).status_code == 200, p


def test_russian_and_new_alphabet(client):
    """Ikki til: özbekça (yangi alifbo) va ruscha."""
    b = {"date": "2026-11-17", "sbp": 152, "dbp": 98, "hb_g_l": 112, "protein_g_l": 0.6, "symptoms": []}
    client.post("/api/patients/101/visits", json=b)
    uz = client.get("/api/patients/101").json()
    ru = client.get("/api/patients/101?lang=ru").json()
    assert "Preeklampsiya xavfi" in uz["assessment"]["summary"]
    assert "Риск преэклампсии" in ru["assessment"]["summary"]
    assert ru["chain"]["links"][2]["title"] == "Специалист" and uz["chain"]["links"][2]["title"] == "Mutaxassis"
    assert any("Uzilmas" in x or "ВОЗ" in x or "протокол" in x for x in [f["source"] for f in ru["assessment"]["findings"]])
    client.post("/api/patients/103/discharge", json={"reason": "postpartum", "notes": ""})
    tasks_ru = client.get("/api/doctor/tasks?lang=ru").json()
    tasks_uz = client.get("/api/doctor/tasks").json()
    assert tasks_ru[0]["message"] == "После родов" and tasks_uz[0]["message"] == "Tuğruqdan keyin"
