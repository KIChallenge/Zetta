"""The doctor directory (spec 12.5): valid data, deterministic ranking, and nothing of it reaches the LLM."""

import json
from datetime import date

import pytest

from backend import engine, scripts
from backend.corpus import get_corpus
from backend.engine import DOCTOR_LIMIT, _contract_rank, _contract_warning, evaluate, find_doctors
from backend.facts import FACTS, VIENNA_POSTAL_CODE

corpus = get_corpus()
DOCTORS = {d.id: d for d in corpus.directory.doctors}
FACTS_FOR_PLAN = {"goal": ["doctor_appointment"], "appointment_reason": "check_up", "preferred_time": "any"}


def plan_for(**facts):
    return evaluate({**FACTS_FOR_PLAN, **facts}, corpus).plan


def call_step(plan):
    return next(s for s in plan["steps"] if s["id"] == "doctor_appointment.call")


def test_the_directory_is_valid_and_fresh():
    assert len(DOCTORS) == len(corpus.directory.doctors)
    for d in corpus.directory.doctors:
        assert d.specialty in FACTS["specialty"].values, d.id
        assert VIENNA_POSTAL_CODE.match(d.postal_code), d.id
        assert d.source_url.startswith("https://praxisplan.at/"), d.id
    assert (date.today() - corpus.directory.scraped_at).days <= 90


def test_every_specialty_with_data_has_practices_with_a_contract():
    for specialty in set(FACTS["specialty"].values) - {"dentistry"}:
        assert [d for d in corpus.directory.doctors if d.specialty == specialty and _contract_rank(d) == 0], specialty


def test_the_call_step_lists_practices_instead_of_the_search_step():
    plan = plan_for(specialty="dermatology", district="1100")
    step = call_step(plan)

    assert [s["id"] for s in plan["steps"]] == ["doctor_appointment.call"]
    assert len(step["doctors"]) == DOCTOR_LIMIT
    assert step["more"]["type"] == "web"
    assert "contact" not in step  # the user picks one from the list


@pytest.mark.parametrize("specialty", ["dentistry", "unknown"])
def test_without_practices_the_plan_keeps_the_search_step(specialty):
    plan = plan_for(specialty=specialty, district="1100")

    assert [s["id"] for s in plan["steps"]] == ["doctor_appointment.find", "doctor_appointment.call"]
    assert "doctors" not in call_step(plan)


def test_contracts_come_first_then_the_district():
    found = find_doctors({"specialty": "general_practice", "district": "1100", "preferred_time": "any"}, corpus)
    records = [DOCTORS[d["id"]] for d in found]

    assert all(_contract_rank(d) == 0 for d in records)
    assert all(d.postal_code == "1100" for d in records)  # 1100 has more than enough of them


def test_a_district_without_enough_contracts_is_filled_from_nearby_not_with_private_practices():
    facts = {"specialty": "ent", "preferred_time": "any"}
    thin = next(
        f"1{n:02d}0"
        for n in range(1, 24)
        if sum(d.specialty == "ent" and d.postal_code == f"1{n:02d}0" and _contract_rank(d) == 0 for d in DOCTORS.values()) == 0
    )
    records = [DOCTORS[d["id"]] for d in find_doctors({**facts, "district": thin}, corpus)]

    assert len(records) == DOCTOR_LIMIT
    assert all(_contract_rank(d) == 0 for d in records)


def test_the_preferred_time_ranks_within_the_district():
    facts = {"specialty": "general_practice", "district": "1100"}
    for time, fits in [("morning", lambda w: w.from_ < "12:00"), ("afternoon", lambda w: w.to > "12:00")]:
        for found in find_doctors({**facts, "preferred_time": time}, corpus):
            assert any(fits(w) for w in DOCTORS[found["id"]].hours)


@pytest.mark.parametrize("specialty", sorted(set(FACTS["specialty"].values) - {"dentistry"}))
def test_a_list_never_shows_the_same_number_twice(specialty):
    for n in range(1, 24):
        found = find_doctors({"specialty": specialty, "district": f"1{n:02d}0", "preferred_time": "any"}, corpus)
        phones = [d["contact"]["value"] for d in found]
        assert len(phones) == len(set(phones)) == DOCTOR_LIMIT


def test_only_practices_that_may_not_take_the_insurance_have_a_warning():
    assert _contract_warning(next(d for d in DOCTORS.values() if "ALLE" in d.insurers)) is None
    private = next(d for d in DOCTORS.values() if not d.insurers)
    assert "Kein Kassenvertrag" in _contract_warning(private)
    partial = next(d for d in DOCTORS.values() if _contract_rank(d) == 1)
    assert partial.insurers[0] in _contract_warning(partial)


def test_a_warning_comes_with_its_source(monkeypatch):
    monkeypatch.setattr(engine, "_contract_rank", lambda d: 2)
    found = find_doctors({"specialty": "ent", "district": "1100", "preferred_time": "any"}, corpus)

    assert all(d["warning"] and d["warning_source"] == corpus.directory.cost_source for d in found)


def test_the_ranking_is_deterministic():
    facts = {"specialty": "ophthalmology", "district": "1050", "preferred_time": "morning"}
    assert find_doctors(facts, corpus) == find_doctors(dict(facts), corpus)


def test_an_unknown_district_still_lists_practices():
    assert len(find_doctors({"specialty": "ent", "district": "unknown"}, corpus)) == DOCTOR_LIMIT


def test_the_llm_never_gets_doctor_data():
    step = call_step(plan_for(specialty="dermatology", district="1100"))
    sent = json.dumps(scripts.llm_input(step, {"doctor_appointment": "Arzttermin"}), ensure_ascii=False)

    for doctor in step["doctors"]:
        assert doctor["name"] not in sent
        assert doctor["address"] not in sent
        assert doctor["contact"]["value"] not in sent


def test_acute_complaints_never_get_a_list():
    assert evaluate({**FACTS_FOR_PLAN, "appointment_reason": "acute", "specialty": "ent"}, corpus).kind == "acute"
