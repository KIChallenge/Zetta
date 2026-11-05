"""Script validation (spec 8.3), filling (8.4) and the fallback. No real LLM."""

import asyncio

import pytest

from backend import scripts
from backend.corpus import get_corpus
from backend.engine import evaluate
from backend.schemas import ProfileData

corpus = get_corpus()
FACTS = {"subject": "mother", "needs_daily_help": "a_lot", "district": "1100", "pension_payer": "pv", "lives_alone": "yes"}
STEPS = {s["id"]: s for s in evaluate(FACTS, corpus).plan["steps"]}
CALL = STEPS["care_allowance.call"]
EMAIL = STEPS["home_care_fsw.send_application"]
PROFILE = ProfileData(full_name="Anna Berger", phone="0660 1234567", contact_email="anna@example.at", svnr="1237010180")


def call(**changes):
    script = {
        "opening": "Guten Tag, mein Name ist {user.name}. Ich rufe für {subject.relation} an.",
        "points": [{"covers": i["id"], "text": "Wie geht das?"} for i in CALL["must"]],
        "closing": "Danke. Sie erreichen mich unter {user.phone}.",
    }
    return {"call": {**script, **changes}}


def test_a_valid_script_passes():
    assert scripts.validate(call(), CALL) == []


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"points": []}, "does not cover"),
        ({"points": [{"covers": "made_up", "text": "x"}] + call()["call"]["points"]}, "covers unknown items"),
        ({"closing": "Rufen Sie mich an: 0660 1234567"}, "phone number"),
        ({"closing": "Die Nummer ist +43 5 0303."}, "phone number"),
        ({"closing": "Schreiben Sie an anna@example.at"}, "email address"),
        ({"closing": "Mehr auf www.pv.at"}, "url"),
        ({"closing": "Mehr auf pv.at"}, "url"),
        ({"closing": "Ich zahle 206,20 Euro"}, "amount"),
        ({"closing": "Der Termin ist am 12.3."}, "date"),
        ({"closing": "Konto AT61 1904 3002 3457 3201"}, "iban"),
        ({"opening": "Meine Mutter hat Demenz."}, "medical wording"),
        ({"opening": "Sie nimmt viele Medikamente."}, "medical wording"),
        ({"opening": "Mein Name ist {user.iban}."}, "unknown placeholders"),
        ({"opening": "x" * 301}, "longer than"),
    ],
)
def test_invalid_scripts_are_rejected(changes, error):
    assert any(error in e for e in scripts.validate(call(**changes), CALL))


def test_a_call_script_is_not_accepted_for_an_email_step():
    assert scripts.validate(call(), EMAIL) == ["not a script for a email step"]


def test_fill_uses_the_profile_and_shows_gaps():
    rendered = scripts.render(call(), CALL, PROFILE, FACTS)
    assert rendered["opening"] == "Guten Tag, mein Name ist Anna Berger. Ich rufe für meine Mutter an."
    assert rendered["closing"] == "Danke. Sie erreichen mich unter 0660 1234567."
    assert rendered["have_ready"] == [{"label": "SV-Nummer Ihrer Mutter", "value": None}]


def test_missing_profile_values_become_visible_gaps():
    rendered = scripts.render(call(), CALL, ProfileData(), {**FACTS, "subject": "father"})
    assert rendered["opening"] == "Guten Tag, mein Name ist [Ihr Name]. Ich rufe für meinen Vater an."
    assert {"label": "Ihre Telefonnummer", "value": None} in rendered["have_ready"]


def test_for_oneself_the_subject_is_the_user():
    rendered = scripts.render(call(), CALL, PROFILE, {**FACTS, "subject": "self"})
    assert rendered["have_ready"] == [{"label": "Ihre SV-Nummer", "value": "1237 010180"}]


def test_fallback_drops_points_that_do_not_apply():
    own = {s["id"]: s for s in evaluate({**FACTS, "subject": "self"}, corpus).plan["steps"]}["care_allowance.call"]
    script = scripts.fallback(own, corpus)
    assert "relative_applies" not in [p["covers"] for p in script["call"]["points"]]
    assert scripts.validate(script, own) == []


class Llm:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def scripts(self, steps, detail):
        self.calls.append([s["step_id"] for s in steps])
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def generate(llm):
    return asyncio.run(scripts.generate(llm, [CALL, EMAIL], {"care_allowance": "Pflegegeld", "home_care_fsw": "FSW"}, "short", corpus))


def email():
    covers = [i["id"] for i in EMAIL["must"]]
    return {"email": {"subject": "Antrag", "body": "Sehr geehrte Damen und Herren, ... {user.name}", "covers": covers}}


def test_generate_uses_valid_llm_output():
    result = generate(Llm({CALL["id"]: call(), EMAIL["id"]: email()}))
    assert {k: v["source"] for k, v in result.items()} == {CALL["id"]: "llm", EMAIL["id"]: "llm"}


def test_generate_retries_only_rejected_steps_once_then_falls_back():
    bad = call(closing="Rufen Sie 01 24524 an")
    llm = Llm({CALL["id"]: bad, EMAIL["id"]: email()}, {CALL["id"]: bad})
    result = generate(llm)
    assert llm.calls == [[CALL["id"], EMAIL["id"]], [CALL["id"]]]
    assert result[CALL["id"]] == {**scripts.fallback(CALL, corpus), "source": "fallback"}
    assert result[EMAIL["id"]]["source"] == "llm"


def test_generate_falls_back_when_the_llm_is_down():
    result = generate(Llm(RuntimeError("down"), RuntimeError("down")))
    assert {v["source"] for v in result.values()} == {"fallback"}
    for step in (CALL, EMAIL):
        assert scripts.validate(result[step["id"]], step) == []


def test_llm_input_has_no_contact_data_and_no_personal_values():
    sent = scripts.llm_input(CALL, {"care_allowance": "Pflegegeld"})
    assert set(sent) == {"step_id", "type", "service", "institution", "items", "placeholders", "facts"}
    assert sent["institution"] == "Pensionsversicherung (PV), Landesstelle Wien"
    assert sent["facts"] == {"subject": "mother", "pension_payer": "pv"}
