from app.rules import Patient, Visit, assess, GREEN, YELLOW, RED

P = Patient(age=27)


def v(**kw):
    base = dict(date="2026-11-01", sbp=115, dbp=72, protein_g_l=0.0, hb_g_l=122, glucose_fasting=4.5)
    base.update(kw)
    return Visit(**base)


def test_normal_is_green():
    a = assess(P, [v()])
    assert a.zone == GREEN and not a.findings


def test_severe_hypertension_red():
    assert assess(P, [v(sbp=165, dbp=100)]).zone == RED


def test_preeclampsia_red():
    a = assess(P, [v(sbp=145, dbp=92, protein_g_l=0.5)])
    assert a.zone == RED and any(f.rule_id == "R-PE" for f in a.findings)


def test_moderate_hypertension_yellow():
    assert assess(P, [v(sbp=145, dbp=92)]).zone == YELLOW


def test_anemia_levels():
    assert assess(P, [v(hb_g_l=100)]).zone == YELLOW
    assert assess(P, [v(hb_g_l=65)]).zone == RED


def test_gdm_yellow_and_overt_red():
    assert assess(P, [v(glucose_fasting=5.4)]).zone == YELLOW
    assert assess(P, [v(glucose_fasting=7.2)]).zone == RED


def test_danger_sign_red():
    assert assess(P, [v(symptoms=["vaginal_bleeding"])]).zone == RED


def test_unknown_never_green():
    a = assess(P, [v(sbp=None, dbp=None)])
    assert a.zone == YELLOW and "qon bosimi" in a.needs_review


def test_unknown_does_not_lower_red():
    a = assess(P, [v(hb_g_l=None, sbp=170, dbp=115)])
    assert a.zone == RED


def test_risk_factor_age():
    assert assess(Patient(age=38), [v()]).zone == YELLOW


def test_hb_trend_raises_zone():
    visits = [v(date="2026-09-01", hb_g_l=125), v(date="2026-09-22", hb_g_l=118),
              v(date="2026-10-13", hb_g_l=112)]
    a = assess(P, visits)
    assert a.trend_raised and a.zone == YELLOW   # 112 özi yaşil, lekin dinamika kötaradi


def test_trend_on_yellow_goes_red():
    visits = [v(date="2026-09-01", hb_g_l=118), v(date="2026-09-22", hb_g_l=110),
              v(date="2026-10-13", hb_g_l=104)]
    assert assess(P, visits).zone == RED


def test_latest_visit_decides():
    visits = [v(date="2026-09-01", sbp=170, dbp=112), v(date="2026-10-01")]
    assert assess(P, visits).zone == GREEN
