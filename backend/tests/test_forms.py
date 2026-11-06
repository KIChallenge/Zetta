"""Prefilled forms: the person's details in the right fields, and nothing cut off or medical."""

import io

import pytest
from pypdf import PdfReader

from backend import forms, scripts
from backend.corpus import get_corpus
from backend.schemas import PersonData, ProfileData

corpus = get_corpus()
CARE = corpus.forms["care_allowance_form"]
PROFILE = ProfileData(
    full_name="Anna Maria Berger",
    street="Favoritenstraße 12/3/4",
    postal_code="1100",
    city="Wien",
    svnr="1237010180",
    phone="0660 1234567",
    contact_email="anna@example.at",
)


def filled(form, profile, facts, kept=None, answers=None):
    """PDF field -> value of the downloaded form, read back."""
    fields = forms.wizard_fields(form, forms.rows(form, profile, kept or {}, facts, answers or {}))
    pdf = PdfReader(io.BytesIO(forms.pdf(form, fields))).get_fields()
    return {name: f.get("/V") for name, f in pdf.items() if f.get("/V") not in (None, "", "/Off")}


@pytest.mark.parametrize(
    ("street", "expected"),
    [
        ("Favoritenstraße 12/3/4", ("Favoritenstraße", "12/3/4")),
        ("Straße des 1. Mai 5", ("Straße des 1. Mai", "5")),
        ("Am Hof 2 Top 3", ("Am Hof", "2 Top 3")),
        ("Hauptplatz", ("Hauptplatz", "")),
    ],
)
def test_split_street(street, expected):
    assert forms.split_street(street) == expected


def test_split_name_takes_the_last_word_as_the_last_name():
    assert forms.split_name("Anna Maria Berger") == ("Berger", "Anna Maria")
    assert forms.split_name("Berger") == ("Berger", "")


def test_for_themselves_the_applicant_part_is_the_users_profile():
    values = filled(CARE, PROFILE, {"subject": "self"})

    assert values == {
        "VSNR_1": "1237010180",
        "Fam.Name": "Berger",
        "Vorname": "Anna Maria",
        "Adresse Straße": "Favoritenstraße",
        "Hausnummer, Stiege, Tür": "12/3/4",
        "PLZ": "1100",
        "Ort": "Wien",
        "Telefon": "0660 1234567",
        "Email": "anna@example.at",
    }


def test_for_a_relative_only_the_part_of_the_person_filling_in_has_the_users_details():
    values = filled(CARE, PROFILE, {"subject": "mother"})

    assert values == {
        "Familienname andere": "Berger",
        "Vorname andere Person": "Anna Maria",
        "Adresse Straße 1": "Favoritenstraße",
        "Hausnummer, Stiege, Tür2": "12/3/4",
        "PLZ 1": "1100",
        "Ort 1": "Wien",
        "Telefon 1": "0660 1234567",
        "Email2": "anna@example.at",
    }


def test_unknown_subject_fills_nothing_of_the_user():
    assert filled(CARE, PROFILE, {}) == {}


def test_checkboxes_of_the_service_are_ticked():
    values = filled(corpus.forms["fsw_application_form"], ProfileData(), {"subject": "self"})

    assert values == {"Leistungen Pflege und Betreuung": "/Ja", "Pflege und Betreuung zu Hause": "/Ja"}


def test_a_value_longer_than_the_field_is_left_for_the_user():
    long = PROFILE.model_copy(update={"full_name": "Anna Maria Theresia Josefine Katharina Berger"})

    values = filled(CARE, long, {"subject": "self"})

    assert values["Fam.Name"] == "Berger"
    assert "Vorname" not in values  # 38 characters, the field takes 30: the user writes it in by hand
    first = next(r for r in forms.rows(CARE, long, {}, {"subject": "self"}, {}) if r.question.id == "first_name")
    assert (first.value, first.source) == ("", None)


def test_kept_details_of_a_relative_fill_the_form():
    mother = PersonData(
        full_name="Maria Berger", street="Hauptstraße 5", postal_code="1100", city="Wien", birth_date="1948-03-12",
        sex="female", marital_status="widowed", citizenship="austria",
    ).model_dump(exclude_defaults=True)  # fmt: skip

    values = filled(CARE, PROFILE, {"subject": "mother"}, {"mother": mother})

    assert values["Fam.Name"] == "Berger"
    assert values["Geburtsdatum"] == "12.03.1948"
    assert values["Geschlecht"] == "weiblich"
    assert values["Personenstand"] == "/03"
    assert values["Stabü"] == "/01"
    assert values["Familienname andere"] == "Berger"  # the user, filling in for her


def test_a_choice_the_form_has_no_box_or_room_for_is_left_open():
    rehab, facts = corpus.forms["rehab_form"], {"subject": "self"}
    kept = {"self": {"sex": "diverse", "marital_status": "partnership"}}

    values = filled(rehab, PROFILE, facts, kept)

    assert "Geschlecht" not in values  # only "männlich" and "weiblich"
    assert "Personenstand" not in values  # "eingetragene Partnerschaft" does not fit its 15 characters
    offered = {q.id: forms.options(q, forms.max_lengths(rehab.file)) for q in rehab.questions if q.id in ("sex", "marital_status")}
    assert set(offered["sex"]) == {"female", "male"}
    assert "partnership" not in offered["marital_status"] and "married" in offered["marital_status"]


@pytest.mark.parametrize(("sex", "state"), [("female", "/weiblich"), ("male", "/maennlich"), ("diverse", "/divers/inter/offen")])
def test_radio_buttons_get_the_state_of_the_choice(sex, state):
    values = filled(corpus.forms["fsw_application_form"], ProfileData(), {"subject": "self"}, {"self": {"sex": sex}})

    assert values["Geschlecht KundIn"] == state


def test_a_name_the_form_asks_for_twice_is_written_from_the_answers():
    values = filled(corpus.forms["rehab_form"], PROFILE, {"subject": "self"}, answers={"first_name": "Anna"})

    assert (values["Familienname"], values["Vorname"], values["Patient(in)"]) == ("Berger", "Anna", "Berger Anna")
    assert "Patient(in)" not in filled(corpus.forms["rehab_form"], ProfileData(), {"subject": "self"})


@pytest.mark.parametrize("form", [f for f in corpus.forms.values() if f.sections], ids=lambda f: f.id)
def test_nothing_medical_is_ever_asked_or_filled(form):
    for q in form.questions:
        if not q.manual:
            assert not scripts.MEDICAL.search(" ".join([q.label, *q.fields])), (form.id, q.id)
