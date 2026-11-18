"""Gemini javobini taqlid qilib (mock) butun zanjirni tekşiradi: rasm -> öqiş -> zona."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import extract
from app.extract import postprocess

DEMO = Path(__file__).resolve().parent.parent / "demo"


def gem(values: dict, name="Bahromova Naima") -> dict:
    """Gemini generateContent javobi körinişi."""
    payload = {"patient_name": name, "test_date": "2026-11-17",
               "values": {k: {"value": v, "unit": u, "raw": f"{k} {v}", "confidence": c}
                          for k, (v, u, c) in values.items()}}
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


NAIMA = {"hb_g_l": (112, "g/l", 0.97), "glucose_fasting": (4.8, "mmol/l", 0.95),
         "protein_g_l": (0.6, "g/l", 0.93), "sbp": (152, None, 0.9), "dbp": (98, None, 0.9),
         "ga_weeks": (33, None, 0.95)}


# ---------- postprocess: xavfsizlik qoidalari ----------
def test_low_confidence_becomes_unknown():
    r = postprocess(json.loads(gem({"hb_g_l": (112, "g/l", 0.4)})["candidates"][0]["content"]["parts"][0]["text"]))
    assert r["values"]["hb_g_l"] is None and r["warnings"]


def test_implausible_value_rejected():
    r = postprocess({"values": {"sbp": {"value": 1520, "confidence": 0.99}}})
    assert r["values"]["sbp"] is None and "mantiqsiz" in r["warnings"][0]


def test_unit_conversion():
    r = postprocess({"values": {"hb_g_l": {"value": 9.8, "unit": "g/dl", "confidence": 0.9},
                                "glucose_fasting": {"value": 95, "unit": "mg/dl", "confidence": 0.9}}})
    assert r["values"]["hb_g_l"] == 98.0 and r["values"]["glucose_fasting"] == 5.3


def test_missing_field_is_none_not_normal():
    r = postprocess({"values": {}})
    assert all(v is None for v in r["values"].values())


# ---------- API: töliq zanjir ----------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UZILMAS_DB", str(tmp_path / "t.db"))
    import importlib
    from app import db, seed, main
    importlib.reload(db); importlib.reload(seed); importlib.reload(main)
    seed.seed(n=10)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    return TestClient(main.app)


def mock_gemini(monkeypatch, response: dict, status=200):
    real = httpx.AsyncClient

    def handler(request: httpx.Request):
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"
        return httpx.Response(status, json=response)

    monkeypatch.setattr(extract.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler)))


def test_photo_to_red_zone(client, monkeypatch):
    mock_gemini(monkeypatch, gem(NAIMA))
    img = (DEMO / "tahlil_bahromova_naima.jpg").read_bytes()
    r = client.post("/api/patients/101/extract", files={"file": ("n.jpg", img, "image/jpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["zone_before"] == "green"
    assert d["preview_assessment"]["zone"] == "red"
    assert d["name_match"] is True
    assert any(f["rule_id"] == "R-PE" for f in d["preview_assessment"]["findings"])
    # Hamşira tasdiqlaydi -> saqlanadi
    s = client.post("/api/patients/101/visits", json=d["draft_visit"]).json()
    assert s["zone_before"] == "green" and s["zone_after"] == "red"


def test_name_mismatch_flagged(client, monkeypatch):
    mock_gemini(monkeypatch, gem(NAIMA, name="Boşqa Odam"))
    img = (DEMO / "tahlil_bahromova_naima.jpg").read_bytes()
    d = client.post("/api/patients/101/extract", files={"file": ("n.jpg", img, "image/jpeg")}).json()
    assert d["name_match"] is False


def test_gemini_error_is_502(client, monkeypatch):
    mock_gemini(monkeypatch, {"error": "quota"}, status=429)
    img = (DEMO / "tahlil_bahromova_naima.jpg").read_bytes()
    r = client.post("/api/patients/101/extract", files={"file": ("n.jpg", img, "image/jpeg")})
    assert r.status_code == 502
