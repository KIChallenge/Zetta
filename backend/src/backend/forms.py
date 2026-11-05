"""Prefilled application forms: the blank PDF from corpus/forms with the user's own details in its fields.

Which field gets what is corpus data (forms.yaml). Only the profile and the chat's facts go in: never medical
details, signatures, dates, consents or anything the user still has to decide. The filled PDF is built on request
and not stored.
"""

import io
import re
from functools import cache

from pypdf import PdfReader, PdfWriter

from backend.corpus import CORPUS_DIR, Form
from backend.engine import check
from backend.schemas import ProfileData
from backend.scripts import SLOT, SLOTS

FORMS_DIR = CORPUS_DIR / "forms"
# The house number starts at the last part that is only numbers, letters, slashes and dashes: "Straße des 1. Mai 5".
HOUSE = re.compile(r"^(.+?)\s+(\d[\d\sA-Za-z/-]*)$")
# Detail -> the profile entry it comes from, by its label in scripts.SLOTS.
FROM = {
    "name": "user.name", "last_name": "user.name", "first_name": "user.name",
    "address": "user.address", "street": "user.address", "house": "user.address",
    "postal_code": "user.address", "city": "user.address",
    "svnr": "user.svnr", "phone": "user.phone", "email": "user.email",
}  # fmt: skip
DETAILS = {f"{who}.{detail}" for who in ("user", "subject") for detail in FROM}


def split_name(full_name: str) -> tuple[str, str]:
    """(last name, first names): the last word is taken as the last name. The user checks it on the form."""
    first, _, last = full_name.strip().rpartition(" ")
    return last, first


def split_street(street: str) -> tuple[str, str]:
    """(street, house number with staircase and door), or the whole text as the street."""
    match = HOUSE.match(street.strip())
    return (match[1], match[2]) if match else (street.strip(), "")


def details(profile: ProfileData, facts: dict) -> dict[str, str]:
    """Placeholder -> value. The profile is the user's; it describes the subject only when they ask for themselves."""
    last, first = split_name(profile.full_name)
    street, house = split_street(profile.street)
    place = f"{profile.postal_code} {profile.city}".strip()
    own = {
        "name": profile.full_name,
        "last_name": last,
        "first_name": first,
        "address": ", ".join(p for p in (profile.street, place) if p),
        "street": street,
        "house": house,
        "postal_code": profile.postal_code,
        "city": profile.city,
        "svnr": profile.svnr,
        "phone": profile.phone,
        "email": profile.contact_email,
    }
    values = {f"user.{k}": v for k, v in own.items()}
    if facts.get("subject") == "self":
        values |= {f"subject.{k}": v for k, v in own.items()}
    return {k: v for k, v in values.items() if v}


@cache
def max_lengths(file: str) -> dict[str, int]:
    """Full field name -> its character limit. The limit can sit on the widget or on any parent field."""
    found = {}
    for page in PdfReader(FORMS_DIR / file).pages:
        for annot in page.get("/Annots") or []:
            node, names, limit = annot.get_object(), [], None
            while node is not None:
                if "/T" in node:
                    names.insert(0, node["/T"])
                limit = limit or node.get("/MaxLen")
                node = node["/Parent"].get_object() if "/Parent" in node else None
            if names and limit:
                found[".".join(names)] = int(limit)
    return found


def values(form: Form, profile: ProfileData, facts: dict) -> tuple[dict[str, str], set[str], set[str]]:
    """(PDF field -> value, placeholders used, placeholders the profile lacks), for the fields that apply."""
    known = details(profile, facts)
    limits = max_lengths(form.file) if form.file else {}
    filled, used, missing = {}, set(), set()
    for field in form.fields:
        if field.when and check(field.when, facts) is not True:
            continue
        slots = SLOT.findall(field.value)
        if absent := [s for s in slots if s not in known]:
            missing |= set(absent)
            continue
        value = SLOT.sub(lambda m: known[m[1]], field.value)
        # Cut off, a name or number would be wrong on the form: the user writes it in by hand instead.
        if len(value) > limits.get(field.field, len(value)):
            missing |= set(slots)
            continue
        filled[field.field] = value
        used |= set(slots)
    return filled, used, missing


def summary(form: Form, profile: ProfileData, facts: dict) -> dict:
    """For the form card: which of the user's details are in the PDF, and which the profile still lacks."""
    _, used, missing = values(form, profile, facts)

    def labels(slots: set[str]) -> list[str]:
        # Details of someone else than the user never come from the profile, so they are not "missing" there.
        found = {FROM[s.split(".")[1]] for s in slots if s.startswith("user.") or facts.get("subject") == "self"}
        return [SLOTS[s] for s in SLOTS if s in found]

    return {"filled": labels(used), "missing": labels(missing - used)}


def fill(form: Form, profile: ProfileData, facts: dict) -> bytes:
    filled, _, _ = values(form, profile, facts)
    writer = PdfWriter(clone_from=PdfReader(FORMS_DIR / form.file))
    writer.update_page_form_field_values(None, filled, auto_regenerate=False)
    # Viewers draw the fields from their values, so the filled text is shown in every viewer.
    writer.set_need_appearances_writer(True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
