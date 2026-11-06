"""Prefilled application forms: the blank PDF from corpus/forms with the user's details in its fields.

Which field gets what is corpus data (forms.yaml). Only the profile, the details kept from form cards and the chat's
facts go in: never medical details, signatures, application dates, consents or anything the user still has to
decide. The filled PDF is built on request and not stored.
"""

import io
import re
from datetime import date
from collections import Counter
from functools import cache
from typing import NamedTuple

from pypdf import PdfReader, PdfWriter

from backend.corpus import CORPUS_DIR, Form
from backend.engine import check
from backend.facts import FACTS, subject_words
from backend.schemas import CHOICES, Contact, PersonData, ProfileData
from backend.scripts import SLOT

FORMS_DIR = CORPUS_DIR / "forms"
# The house number starts at the last part that is only numbers, letters, slashes and dashes: "Straße des 1. Mai 5".
HOUSE = re.compile(r"^(.+?)\s+(\d[\d\sA-Za-z/-]*)$")
# What a form card asks for: entry -> (label for the user, label for someone else, the PersonData fields it sets).
ENTRIES = {
    "name": ("Ihr Name", "Name", ["full_name"]),
    "phone": ("Ihre Telefonnummer", "Telefonnummer", ["phone"]),
    "email": ("Ihre E-Mail-Adresse", "E-Mail-Adresse", ["contact_email"]),
    "address": ("Ihre Adresse", "Adresse", ["street", "postal_code", "city"]),
    "svnr": ("Ihre SV-Nummer", "SV-Nummer", ["svnr"]),
    "title": ("Ihr Titel", "Titel", ["title"]),
    "birth_date": ("Ihr Geburtsdatum", "Geburtsdatum", ["birth_date"]),
    "sex": ("Ihr Geschlecht", "Geschlecht", ["sex"]),
    "marital_status": ("Ihr Familienstand", "Familienstand", ["marital_status"]),
    "citizenship": ("Ihre Staatsbürgerschaft", "Staatsbürgerschaft", ["citizenship"]),
    "health_insurer": ("Ihre Krankenkasse", "Krankenkasse", ["health_insurer"]),
}
# Detail of a placeholder -> the entry it comes from.
FROM = {
    "name": "name", "last_name": "name", "first_name": "name",
    "address": "address", "street": "address", "house": "address", "postal_code": "address", "city": "address",
    "svnr": "svnr", "phone": "phone", "email": "email", "title": "title", "birth_date": "birth_date",
    "birth_year": "birth_date", "sex": "sex", "marital_status": "marital_status", "citizenship": "citizenship",
    "health_insurer": "health_insurer",
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


def details(p: PersonData) -> dict[str, str]:
    """Detail -> value of one person. Choices stay codes; text fields get their label (`text`)."""
    last, first = split_name(p.full_name)
    street, house = split_street(p.street)
    place = f"{p.postal_code} {p.city}".strip()
    born = date.fromisoformat(p.birth_date) if p.birth_date else None
    values = {
        "name": p.full_name,
        "last_name": last,
        "first_name": first,
        "address": ", ".join(x for x in (p.street, place) if x),
        "street": street,
        "house": house,
        "postal_code": p.postal_code,
        "city": p.city,
        "svnr": p.svnr,
        "phone": p.phone,
        "email": p.contact_email,
        "title": p.title,
        "birth_date": born.strftime("%d.%m.%Y") if born else "",
        "birth_year": str(born.year) if born else "",
        **{key: getattr(p, key) for key in CHOICES},
    }
    return {k: v for k, v in values.items() if v}


def people(profile: ProfileData, kept: dict[str, dict], facts: dict) -> tuple[PersonData, PersonData | None]:
    """(the user, the person the chat is about): the user from the profile and their own kept details, a relative
    from what was kept for that relation. None while it is not known who the chat is about."""
    user = PersonData(**profile.model_dump(include=set(Contact.model_fields)), **kept.get("self", {}))
    subject = facts.get("subject")
    if subject == "self":
        return user, user
    if subject in FACTS["subject"].values:
        return user, PersonData(**kept.get(subject, {}))
    return user, None


def known(user: PersonData, subject: PersonData | None) -> dict[str, str]:
    """Placeholder -> value."""
    values = {f"user.{k}": v for k, v in details(user).items()}
    if subject is not None:
        values |= {f"subject.{k}": v for k, v in details(subject).items()}
    return values


def text(slot: str, value: str) -> str:
    detail = slot.split(".")[1]
    return CHOICES[detail][value] if detail in CHOICES else value


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


class Filled(NamedTuple):
    fields: dict[str, str]  # PDF field -> value
    used: set[str]  # placeholders that went in
    absent: Counter[str]  # placeholders without a value -> how many fields wait for them
    done: int  # fields with the person's details that are filled
    total: int  # fields with the person's details that apply


def values(form: Form, user: PersonData, subject: PersonData | None, facts: dict) -> Filled:
    """The fields that apply. One that is too long or has a choice the form lacks stays for the user to write."""
    have = known(user, subject)
    limits = max_lengths(form.file) if form.file else {}
    out = Filled({}, set(), Counter(), 0, 0)
    for field in form.fields:
        if field.when and check(field.when, facts) is not True:
            continue
        slots = SLOT.findall(field.value)
        out = out._replace(total=out.total + bool(slots))
        if absent := [s for s in slots if s not in have]:
            out.absent.update(absent)
            continue
        if field.map:
            # A checkbox or radio button: the state for the person's choice, e.g. {subject.sex} -> /weiblich.
            value = field.map.get(have[slots[0]])
            if value is None:
                continue
        else:
            value = SLOT.sub(lambda m: text(m[1], have[m[1]]), field.value)
            # Cut off, a name or number would be wrong on the form: the user writes it in by hand instead.
            if len(value) > limits.get(field.field, len(value)):
                continue
        out.fields[field.field] = value
        out.used.update(slots)
        out = out._replace(done=out.done + bool(slots))
    return out


def summary(form: Form, user: PersonData, subject: PersonData | None, facts: dict) -> dict:
    """For the form card: which details are in the PDF, and the ones still missing, to be asked for right there."""
    result = values(form, user, subject, facts)
    gen = subject_words(facts)[2]

    def entries(slots: set[str]) -> list[tuple[str, str]]:
        # The user's own details and the subject's are the same person when the user asks for themselves. While it
        # is not known who the chat is about, there is no one to keep the subject's details for.
        self = facts.get("subject") == "self"
        found = {("user" if s.startswith("user.") or self else "subject", FROM[s.split(".")[1]]) for s in slots}
        whose = ("user", "subject") if subject is not None else ("user",)
        return [(who, e) for who in whose for e in ENTRIES if (who, e) in found]

    def label(who: str, entry: str) -> str:
        own, noun, _ = ENTRIES[entry]
        return own if who == "user" else f"{noun} {gen}"

    weight = Counter()
    for slot, n in result.absent.items():
        weight.update({e: n for e in entries({slot})})
    # The details that fill the most fields first: the card shows a few, the next forms ask for the rest.
    ask = sorted(entries(set(result.absent)), key=lambda e: weight[e], reverse=True)
    person = {"user": user, "subject": subject}
    return {
        "filled": [label(*e) for e in entries(result.used) if e not in ask],
        "ask": [{"who": who, **entry_item(entry, label(who, entry), person[who])} for who, entry in ask],
        "done": result.done,
        "total": result.total,
    }


def entry_item(entry: str, label: str, person: PersonData) -> dict:
    """An entry as the form card and the settings page ask for it, with what is known already."""
    fields = ENTRIES[entry][2]
    return {
        "entry": entry,
        "label": label,
        "fields": fields,
        "values": {f: getattr(person, f) for f in fields},
        "choices": {f: CHOICES[f] for f in fields if f in CHOICES},
    }


def fill(form: Form, user: PersonData, subject: PersonData | None, facts: dict) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(FORMS_DIR / form.file))
    writer.update_page_form_field_values(None, values(form, user, subject, facts).fields, auto_regenerate=False)
    # Viewers draw the fields from their values, so the filled text is shown in every viewer.
    writer.set_need_appearances_writer(True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
