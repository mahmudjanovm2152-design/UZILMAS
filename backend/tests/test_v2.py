"""Rollar, qabulxona, bemor kabineti, AI funksiyalari, kritik bosqiç (103)."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UZILMAS_DB", str(tmp_path / "t.db"))
    for k in ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "AISHA_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("UZILMAS_AUTH", "on")
    from app import db, seed, notify, auth, main
    for m in (db, auth, seed, notify, main):
        importlib.reload(m)
    seed.seed(n=10)
    with TestClient(main.app) as c:
        yield c


def H(client, user, pw):
    r = client.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_login_and_roles(client):
    assert client.post("/api/login", json={"username": "qabul", "password": "x"}).status_code == 401
    assert client.get("/api/patients").status_code == 401            # tokensiz — yöq
    staff = H(client, "shifokor", "Shifokor2026")
    assert client.get("/api/patients", headers=staff).status_code == 200
    assert client.get("/api/my/card", headers=staff).status_code == 403
    pat = H(client, "bemor", "Bemor2026")
    assert client.get("/api/patients", headers=pat).status_code == 403  # bemor boşqa bemorlarni körmaydi
    me = client.get("/api/me", headers=pat).json()
    assert me["role"] == "bemor" and me["patient_id"] == 101 and me["home"] == "/patient"
    client.post("/api/logout", headers=pat)
    assert client.get("/api/me", headers=pat).status_code == 401


def test_reception_red_premium_live(client):
    h = H(client, "qabul", "Qabul2026")
    body = {"full_name": "Sevara Ismoilova", "age": 24, "phone": "+998 90 123 45 67", "district": "Yunusobod",
            "ga_weeks": 32, "sbp": 162, "dbp": 112, "symptoms": ["severe_headache"], "plan": "premium",
            "complaint": "boş oğriği"}
    r = client.post("/api/reception/register", json=body, headers=h).json()
    assert r["zone"] == "red" and r["alert_id"] and r["nurse"] and r["family_doctor"]
    assert r["appointment"]["prepaid"] == r["appointment"]["price"] // 2 > 0
    live = client.get("/api/live", headers=h).json()
    assert live["registrations"][0]["id"] == r["patient_id"]
    assert live["registrations"][0]["nurse"] == r["nurse"]
    # premium: şaxsiy şifokorga 24 soatlik uy taşrifi vazifasi
    tasks = client.get("/api/doctor/tasks", headers=h).json()
    assert any(t["patient_id"] == r["patient_id"] for t in tasks)
    # kelmadi -> risk oşadi
    client.post(f"/api/appointments/{r['appointment']['id']}/status", json={"status": "no_show"}, headers=h)
    risk = client.get("/api/risk?limit=50", headers=h).json()
    me = next(x for x in risk if x["id"] == r["patient_id"])
    assert any("kelmagan" in s for s in me["reasons"])


def test_patient_triage_danger_creates_red(client):
    h = H(client, "bemor", "Bemor2026")
    ok = client.post("/api/my/ask", json={"text": "Vitamin qaçon içaman?"}, headers=h).json()
    assert ok["danger"] == [] and ok["alert_id"] is None
    neg = client.post("/api/my/ask", json={"text": "Boşim oğrimayapti, hammasi yaxşi"}, headers=h).json()
    assert neg["danger"] == []
    bad = client.post("/api/my/ask", json={"text": "Boşim qattiq oğriyapti, közim xiralaşdi"}, headers=h).json()
    assert bad["danger"] and bad["zone_after"] == "red" and bad["alert_id"]
    card = client.get("/api/my/card", headers=h).json()
    assert card["zone"] == "red" and card["doctor_notified"] and len(card["messages"]) == 3


def test_critical_103_flow(client):
    staff = H(client, "bosh", "Bosh2026")
    pat = H(client, "bemor", "Bemor2026")
    aid = client.post("/api/my/ask", json={"text": "qon ketyapti"}, headers=pat).json()["alert_id"]
    assert aid
    assert aid in client.post("/api/alerts/critical-now", headers=staff).json()["critical"]
    assert client.get("/api/my/card", headers=pat).json()["critical"] is True
    live = client.get("/api/live", headers=staff).json()
    assert any(c["id"] == aid for c in live["critical"])
    a = client.post(f"/api/alerts/{aid}/critical-ack", json={"action": "103"}, headers=staff).json()
    assert "103" in a["critical_ack_by"] and a["acknowledged_at"]
    assert not client.get("/api/live", headers=staff).json()["critical"]


def test_ai_summary_and_intake_fallback(client):
    h = H(client, "shifokor", "Shifokor2026")
    s = client.get("/api/patients/101/ai-summary", headers=h).json()
    assert s["source"] == "rules" and s["text"].startswith("• Zona") and "score" in s["risk"]
    q = H(client, "qabul", "Qabul2026")
    r = client.post("/api/ai/intake", json={"text": "Ismi Dilfuza Karimova, 27 yoş, Çilonzor, 30 hafta, "
                                                    "bosim 150/95, telefon 90 123 45 67, premium paket"}, headers=q).json()
    assert r["district"] == "Çilonzor" and r["age"] == 27 and r["ga_weeks"] == 30
    assert r["sbp"] == 150 and r["dbp"] == 95 and r["plan"] == "premium"
    assert "Dilfuza" in (r["full_name"] or "")
