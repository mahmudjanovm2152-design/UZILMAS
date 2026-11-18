"""Jonli zanjir: har bir böğin töğri holatni körsatadi."""
from datetime import date, datetime

from app import chain, rules

TODAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 12, 0, 0)
P = {"nurse": "Hamşira A", "family_doctor": "Dr. B", "status": "active"}


def _a(zone_visit):
    return rules.assess(rules.Patient(age=26), [rules.Visit(date="2026-11-15", **zone_visit)])


def visits(d="2026-11-15"):
    return [{"date": d}]


GREEN = dict(sbp=115, dbp=75, hb_g_l=120)
RED = dict(sbp=165, dbp=112, hb_g_l=120)


def st(ch):
    return {x["key"]: x["status"] for x in ch["links"]}


def test_green_patient_whole_chain_ok():
    ch = chain.build(P, visits(), _a(GREEN), [], TODAY, NOW)
    assert ch["status"] == "ok"
    assert st(ch) == {"nurse": "ok", "assess": "ok", "specialist": "skip", "hospital": "next", "doctor": "next"}


def test_overdue_visit_breaks_chain():
    ch = chain.build(P, visits("2026-10-01"), _a(GREEN), [], TODAY, NOW)
    assert ch["status"] == "broken" and ch["break_at"] == "Patronaj taşrifi"


def test_red_without_alert_is_broken():
    ch = chain.build(P, visits(), _a(RED), [], TODAY, NOW)
    assert st(ch)["specialist"] == "broken"


def test_red_alert_waiting_then_overdue_then_ack():
    al = {"id": 1, "kind": "red_zone", "acknowledged_at": None, "escalated_at": None, "due_at": "2026-11-17 12:05:00"}
    assert st(chain.build(P, visits(), _a(RED), [al], TODAY, NOW))["specialist"] == "wait"
    al["due_at"] = "2026-11-17 11:00:00"
    assert st(chain.build(P, visits(), _a(RED), [al], TODAY, NOW))["specialist"] == "broken"
    al.update(acknowledged_at="2026-11-17 11:30:00", acknowledged_by="Mutaxassis")
    ch = chain.build(P, visits(), _a(RED), [al], TODAY, NOW)
    assert st(ch)["specialist"] == "ok" and ch["status"] == "ok"


def test_discharged_without_active_call_is_broken():
    p = dict(P, status="discharged", discharged_at="2026-11-16 10:00:00")
    ch = chain.build(p, visits(), _a(GREEN), [], TODAY, NOW)
    assert st(ch)["hospital"] == "ok" and st(ch)["doctor"] == "broken"


def test_missing_bp_waits_for_review():
    a = rules.assess(rules.Patient(age=26), [rules.Visit(date="2026-11-15", hb_g_l=120)])
    ch = chain.build(P, visits(), a, [], TODAY, NOW)
    assert st(ch)["assess"] == "wait"
