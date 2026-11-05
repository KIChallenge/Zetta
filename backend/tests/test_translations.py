"""Translations (spec 11): complete, and never with contact data or numbers the German text does not have."""

import json

import pytest

from backend import pipeline, scripts
from backend.corpus import get_corpus
from backend.translations import LANGUAGES, LOCALES_DIR, all_sources, problems

corpus = get_corpus()
SOURCES = all_sources()


def catalog(code: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_text_is_translated_and_none_is_left_over(code):
    known = set(catalog(code))

    assert not SOURCES - known, "Run scripts/translate.py"
    assert not known - SOURCES, "Run scripts/translate.py"


@pytest.mark.parametrize("code", LANGUAGES)
def test_translations_add_no_contact_data_numbers_or_placeholders(code):
    assert {s: problems(s, t, code) for s, t in catalog(code).items() if problems(s, t, code)} == {}


@pytest.mark.parametrize(
    ("source", "translated", "problem"),
    [
        ("Rufen Sie an.", "Call 01 234 5678.", "numbers differ"),
        ("Fragen Sie nach.", "Ask at info@amt.at.", "contains a new email address"),
        ("Fragen Sie nach.", "See www.amt.at.", "contains a new url"),
        ("Mein Name ist {user.name}.", "My name is Anna.", "placeholders differ"),
        ("Hallo", " ", "empty"),
        ("Kein Kassenvertrag", "No Kassenvertrag", "left a German word"),
        ("Wahlarztpraxis", "Wahlarzt practice", "left a German word"),
        ("Im Spital", "In the Spital", "left a German word"),
    ],
)
def test_the_rules_catch_what_a_careless_llm_might_do(source, translated, problem):
    assert problem in problems(source, translated)


def test_all_shown_corpus_texts_are_sources():
    service = next(s for s in corpus.services if s.id == "doctor_appointment")
    assert {service.title, service.summary, service.steps[0].why} <= SOURCES
    assert "Lebt Ihr Vater allein?" in SOURCES  # a question with its subject filled in


def test_institution_names_stay_german():
    # "Bewegt im Park" is a programme as well: the prompt keeps it German too.
    assert {i.name for i in corpus.institutions.values()} & SOURCES <= {"Bewegt im Park"}


def test_a_rendered_script_also_has_its_corpus_text_for_the_translation():
    service = next(s for s in corpus.services if s.id == "before_discharge")
    step = {"id": "before_discharge.call", "type": "call", "must": [{"id": i.id, "text": i.text} for i in service.steps[0].must_ask],
            "slots": service.steps[0].slots}  # fmt: skip

    plain = scripts.plain(step, scripts.ProfileData(full_name="Anna Berger"), {"subject": "father"}, corpus)

    assert plain["template"]["points"][0]["text"] in SOURCES
    assert plain["slots"]["user.name"] == {"value": "Anna Berger", "gap": ""}
    assert plain["slots"]["subject.relation"]["value"] == "meinen Vater"
    assert plain["slots"]["subject.name"] == {"value": None, "gap": "Name Ihres Vaters"}
    assert pipeline.OUTCOMES["call"]["reached"][0] in SOURCES
