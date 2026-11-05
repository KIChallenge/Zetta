"""Prefilled forms: only the user's own details, in the right fields, and nothing cut off."""

import io

import pytest
from pypdf import PdfReader

from backend import forms, scripts
from backend.corpus import get_corpus
from backend.schemas import ProfileData

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


def filled(form, profile, facts):
    fields = PdfReader(io.BytesIO(forms.fill(form, profile, facts))).get_fields()
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
    assert "subject.first_name" in forms.values(CARE, long, {"subject": "self"})[2]


def test_summary_lists_used_and_missing_profile_details():
    partial = PROFILE.model_copy(update={"svnr": "", "contact_email": ""})

    assert forms.summary(CARE, partial, {"subject": "self"}) == {
        "filled": ["Ihr Name", "Ihre Telefonnummer", "Ihre Adresse"],
        "missing": ["Ihre E-Mail-Adresse", "Ihre SV-Nummer"],
    }
    # The mother's own details are never in the profile, so they are not reported as missing there.
    assert forms.summary(CARE, partial, {"subject": "mother"})["missing"] == ["Ihre E-Mail-Adresse"]


def test_nothing_medical_is_ever_filled():
    for form in corpus.forms.values():
        for field in form.fields:
            assert not scripts.MEDICAL.search(field.field), (form.id, field.field)
