"""Engine table tests (spec 14): facts -> result kind, next question, services, step ids. No LLM."""

import pytest

from backend.corpus import get_corpus
from backend.engine import QUESTION_CAP, check, evaluate, statuses

corpus = get_corpus()
MOTHER = {"subject": "mother", "needs_daily_help": "a_lot"}
ALL_KNOWN = {**MOTHER, "district": "1100", "pension_payer": "pv", "lives_alone": "yes"}
CARE_STEPS = [
    "care_allowance.info",
    "care_allowance.call",
    "documents",
    "care_allowance.submit",
    "care_allowance.assessment",
    "care_allowance.decision",
    "care_allowance.clarify",  # hidden until the decision is "rejected"
]
HOME_STEPS = ["home_care_fsw.call", "home_care_fsw.send_application", "home_care_fsw.assessment"]
CARER_STEPS = ["carer_support.info", "carer_support.request_talk"]


@pytest.mark.parametrize(
    ("facts", "kind", "question"),
    [
        ({}, "question", "goal"),
        ({"goal": "unknown"}, "general", None),
        ({"subject": "mother"}, "question", "goal"),
        (MOTHER, "question", "district"),
        ({**MOTHER, "district": "1100"}, "question", "pension_payer"),
        ({**MOTHER, "district": "1100", "pension_payer": "pv"}, "question", "lives_alone"),
        (ALL_KNOWN, "plan", None),
        ({**MOTHER, "district": "outside_vienna"}, "out_of_scope", None),
        ({"goal": ["apply_care_allowance"]}, "question", "subject"),
        ({"goal": ["find_support_services"], "subject": "self", "district": "1020"}, "question", "lives_alone"),
        # "Weiß nicht" counts as answered: the loop always ends.
        ({**MOTHER, "district": "unknown", "pension_payer": "declined", "lives_alone": "unknown"}, "plan", None),
    ],
)
def test_next_result(facts, kind, question):
    result = evaluate(facts, corpus)
    assert (result.kind, result.question) == (kind, question)


def test_medical_question_returns_the_boundary_card_whatever_else_is_known():
    assert evaluate(ALL_KNOWN, corpus, medical=True).kind == "boundary"


def test_question_cap_builds_the_plan_with_what_is_known():
    result = evaluate(MOTHER, corpus, asked=QUESTION_CAP)
    assert result.kind == "plan"
    services = {s["id"]: s for s in result.plan["services"]}
    assert services["care_allowance"]["eligibility"] == "possible"
    assert services["care_allowance"]["criteria"] == [{"text": "Gewöhnlicher Aufenthalt in Österreich", "state": "unknown"}]


def test_question_cap_without_any_candidate_gives_the_general_card():
    assert evaluate({}, corpus, asked=QUESTION_CAP).kind == "general"


@pytest.mark.parametrize(
    ("facts", "steps"),
    [
        (ALL_KNOWN, CARE_STEPS + HOME_STEPS + CARER_STEPS),
        ({"subject": "self", "goal": ["apply_care_allowance"], "district": "1010", "pension_payer": "none"}, CARE_STEPS),
        (
            {"subject": "father", "goal": ["find_support_services"], "district": "1210", "lives_alone": "no"},
            ["home_care_fsw.call", "documents", *HOME_STEPS[1:]],
        ),
    ],
)
def test_plan_steps(facts, steps):
    assert [s["id"] for s in evaluate(facts, corpus).plan["steps"]] == steps


def test_shared_document_steps_are_merged_into_one_checklist():
    steps = {s["id"]: s for s in evaluate(ALL_KNOWN, corpus).plan["steps"]}
    documents = steps["documents"]
    assert documents["services"] == ["care_allowance", "home_care_fsw"]
    assert [d["id"] for d in documents["documents"]] == [
        "medical_reports", "photo_id", "citizenship_proof", "income_proof", "rent_proof", "care_expenses_proof",
    ]  # fmt: skip
    assert steps["home_care_fsw.send_application"]["after"] == ["home_care_fsw.call", "documents"]


@pytest.mark.parametrize(
    ("payer", "institution", "call_type"),
    [("pv", "pva_vienna", "call"), ("none", "pva_vienna", "call"), ("unknown", "pva_vienna", "call"),
     ("bvaeb", "bvaeb", "info"), ("svs", "svs", "info")],
)  # fmt: skip
def test_care_allowance_goes_to_the_institution_that_pays_the_pension(payer, institution, call_type):
    steps = {s["id"]: s for s in evaluate({**ALL_KNOWN, "pension_payer": payer}, corpus).plan["steps"]}
    call = steps["care_allowance.call"]
    assert call["institution"]["id"] == institution
    # No curated contact: the step names the institution but shows no invented number.
    assert call["type"] == call_type
    assert ("contact" in call) == (call_type == "call")


def test_call_items_that_do_not_apply_are_left_out():
    own = evaluate({**ALL_KNOWN, "subject": "self"}, corpus).plan["steps"]
    call = next(s for s in own if s["id"] == "care_allowance.call")
    assert "relative_applies" not in [i["id"] for i in call["must"]]


def test_criteria_states():
    assert check({"district": ["1100"]}, {"district": "1100"}) is True
    assert check({"district": ["1100"]}, {"district": "1010"}) is False
    assert check({"district": ["1100"]}, {}) is None
    assert check({"district": ["1100"]}, {"district": "unknown"}) is None
    assert check({"goal": ["apply_care_allowance"]}, {"goal": ["find_support_services", "apply_care_allowance"]})
    # Any known mismatch decides, even if another fact is unknown.
    assert check({"subject": ["mother"], "district": ["1100"]}, {"subject": "father"}) is False


def test_statuses_follow_the_after_edges():
    steps = evaluate(ALL_KNOWN, corpus).plan["steps"]
    status = statuses(steps, {})
    assert status["care_allowance.call"] == "available"
    assert status["care_allowance.submit"] == "blocked"
    status = statuses(steps, {"care_allowance.call": "done", "documents": "skipped"})
    assert status["care_allowance.call"] == "done"
    assert status["care_allowance.submit"] == "available"
    assert status["care_allowance.assessment"] == "blocked"


def test_after_a_hospital_stay_the_plan_asks_for_the_letter_until_it_is_confirmed():
    facts = {"subject": "self", "goal": ["after_hospital"], "district": "1100"}
    assert [s["id"] for s in evaluate(facts, corpus).plan["steps"]] == ["after_hospital.upload"]

    plan = evaluate({**facts, "documented_recommendations": ["inpatient_rehab"]}, corpus, quotes={"inpatient_rehab": "Reha empfohlen"}).plan
    assert [s["id"] for s in plan["services"]] == ["rehab"]
    assert plan["services"][0]["quotes"] == ["Reha empfohlen"]
    assert "contact" not in next(s for s in plan["steps"] if s["id"] == "rehab.call_doctor")


def test_seasonal_offers_are_dropped_outside_their_season():
    from datetime import date

    facts = {"subject": "self", "interests": ["exercise"], "district": "1100"}
    winter = evaluate(facts, corpus, today=date(2026, 11, 5)).plan
    assert winter["services"] == [] and winter["dropped"][0]["reason"] == "Gibt es nur von Juni bis September."
    summer = evaluate(facts, corpus, today=date(2027, 6, 1)).plan
    assert [s["id"] for s in summer["services"]] == ["bewegt_im_park"]
    assert summer["steps"][0]["contact"]["value"] == "https://www.bewegt-im-park.at/"


def test_an_acute_appointment_gets_the_boundary_card():
    assert evaluate({"goal": ["doctor_appointment"], "appointment_reason": "acute"}, corpus).kind == "boundary"


def test_broad_goals_ask_their_questions_first():
    assert evaluate({"goal": ["health_promotion"], "subject": "self"}, corpus).question == "interests"
    assert evaluate({"goal": ["child_offers"], "subject": "child"}, corpus).question == "district"
