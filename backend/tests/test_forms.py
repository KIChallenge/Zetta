"""Prefilled forms: only the user's own details, in the right fields, and nothing cut off."""

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


def filled(form, profile, facts, kept=None):
    fields = PdfReader(io.BytesIO(forms.fill(form, *forms.people(profile, kept or {}, facts), facts))).get_fields()
    return {name: f.get("/V") for name, f in fields.items() if f.get("/V") not in (None, "", "/Off")}


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
    assert "Vorname" not in values  # 38 characters, the field takes 30
    # Known, so not asked for again: the user writes it in by hand.
    asked = forms.summary(CARE, *forms.people(long, {}, {"subject": "self"}), {"subject": "self"})["ask"]
    assert "name" not in [a["entry"] for a in asked]


def summary(profile, facts, kept=None):
    return forms.summary(CARE, *forms.people(profile, kept or {}, facts), facts)


def test_summary_lists_filled_details_and_asks_for_the_missing_ones():
    partial = PROFILE.model_copy(update={"svnr": "", "contact_email": ""})

    result = summary(partial, {"subject": "self"})

    assert result["filled"] == ["Ihr Name", "Ihre Telefonnummer", "Ihre Adresse"]
    assert [a["label"] for a in result["ask"]] == [
        "Ihre E-Mail-Adresse", "Ihre SV-Nummer", "Ihr Titel", "Ihr Geburtsdatum", "Ihr Geschlecht",
        "Ihr Familienstand", "Ihre Staatsbürgerschaft",
    ]  # fmt: skip
    assert (result["done"], result["total"]) == (7, 14)
    sex = next(a for a in result["ask"] if a["entry"] == "sex")
    assert sex == {
        "who": "user", "entry": "sex", "label": "Ihr Geschlecht", "fields": ["sex"], "values": {"sex": ""},
        "choices": {"sex": {"female": "weiblich", "male": "männlich", "diverse": "divers"}},
    }  # fmt: skip


def test_for_a_relative_the_summary_asks_for_their_details_by_relation():
    result = summary(PROFILE, {"subject": "mother"})

    assert "Name Ihrer Mutter" in [a["label"] for a in result["ask"]]
    assert {a["who"] for a in result["ask"]} == {"user", "subject"}  # the user's title, the mother's details


def test_while_the_subject_is_unknown_only_the_users_details_are_asked_for():
    assert {a["who"] for a in summary(PROFILE, {})["ask"]} <= {"user"}


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


def test_a_choice_the_form_has_no_box_for_is_left_open():
    rehab, facts, kept = corpus.forms["rehab_form"], {"subject": "self"}, {"self": {"sex": "diverse"}}

    assert "Geschlecht" not in filled(rehab, PROFILE, facts, kept)  # only "männlich" and "weiblich"
    assert "sex" not in [a["entry"] for a in forms.summary(rehab, *forms.people(PROFILE, kept, facts), facts)["ask"]]


@pytest.mark.parametrize(("sex", "state"), [("female", "/weiblich"), ("male", "/maennlich"), ("diverse", "/divers/inter/offen")])
def test_radio_buttons_get_the_state_of_the_choice(sex, state):
    values = filled(corpus.forms["fsw_application_form"], ProfileData(), {"subject": "self"}, {"self": {"sex": sex}})

    assert values["Geschlecht KundIn"] == state


def test_nothing_medical_is_ever_filled():
    for form in corpus.forms.values():
        for field in form.fields:
            assert not scripts.MEDICAL.search(field.field), (form.id, field.field)


def test_the_details_that_fill_the_most_fields_are_asked_for_first():
    asked = [a["entry"] for a in summary(ProfileData(), {"subject": "mother"})["ask"]]

    # The address fills street, house number, postal code and city, for the mother and for the user.
    assert asked[:2] == ["address", "address"]
    assert asked.index("name") < asked.index("title")
