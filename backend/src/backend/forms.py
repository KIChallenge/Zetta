"""Prefilled application forms: the blank PDF from corpus/forms with the user's details and answers in its fields.

Which field gets what is corpus data (forms.yaml). The wizard asks for the whole form, section by section, and fills
in what it can: the profile, the details kept for a person, the chat's facts and what the user answers. Never medical
details, signatures, application dates or consents: those are manual and stay on paper. The filled PDF is built on
request and not stored.
"""

import io
import re
from datetime import date
from functools import cache
from typing import NamedTuple

from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter

from backend.corpus import CORPUS_DIR, Condition, FactValue, Form, FormQuestion, FormSection, Not
from backend.engine import check
from backend.facts import FACTS, value_label
from backend.schemas import CHOICES, Contact, PersonData, ProfileData
from backend.scripts import SLOT

FORMS_DIR = CORPUS_DIR / "forms"
# The house number starts at the last part that is only numbers, letters, slashes and dashes: "Straße des 1. Mai 5".
HOUSE = re.compile(r"^(.+?)\s+(\d[\d\sA-Za-z/-]*)$")
# A person's details as the settings page asks for them: entry -> (label for the user, label for someone else, the
# PersonData fields it sets).
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


def entry_item(entry: str, label: str, person: PersonData) -> dict:
    """An entry as the settings page asks for it, with what is known already."""
    fields = ENTRIES[entry][2]
    return {
        "entry": entry,
        "label": label,
        "fields": fields,
        "values": {f: getattr(person, f) for f in fields},
        "choices": {f: CHOICES[f] for f in fields if f in CHOICES},
    }


def pdf(form: Form, fields: dict[str, str]) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(FORMS_DIR / form.file))
    writer.update_page_form_field_values(None, fields, auto_regenerate=False)
    # Viewers draw the fields from their values, so the filled text is shown in every viewer.
    writer.set_need_appearances_writer(True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ---- The wizard: the whole form, section by section (forms.yaml `sections`) ----

EMPTY = "empty"  # an unanswered question, in `when` and `checks`
YES_NO = {"yes": "Ja", "no": "Nein"}
CHOICE_KINDS = ("choice", "yes_no", "checkbox")
DETAIL = re.compile(r"^\{(user|subject)\.([a-z_]+)\}$")
FILL = re.compile(r"\{([a-z_]+)\}")  # a question's answer in `fills`
PAPER_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
# A detail typed into the wizard -> the PersonData field it is validated as and kept in.
PERSON = {
    "name": "full_name", "svnr": "svnr", "postal_code": "postal_code", "city": "city", "phone": "phone", "email": "contact_email",
    "title": "title", "birth_date": "birth_date", "sex": "sex", "marital_status": "marital_status",
    "citizenship": "citizenship",
}  # fmt: skip
MAX_ANSWER = 1000


def holds(when: Condition | list[Condition] | None, state: dict) -> bool:
    """Shown: no condition, or one of them known to be true."""
    conditions = when if isinstance(when, list) else [when] if when else []
    return not conditions or any(check(c, state) is True for c in conditions)


def detail(q: FormQuestion) -> tuple[str, str] | None:
    """(whose, detail) of a question that is exactly one of a person's details, e.g. ("subject", "svnr")."""
    match = DETAIL.match(q.value) if isinstance(q.value, str) else None
    return (match[1], match[2]) if match else None


def options(q: FormQuestion, limits: dict[str, int] | None = None) -> dict[str, str]:
    """The answers offered. With a `map` only those the form has a box for, with `limits` (a text field) only those
    whose label fits: the others are written in by hand."""
    if q.kind == "yes_no":
        found = YES_NO
    elif q.kind == "checkbox":
        found = {"yes": q.label}
    else:
        found = q.options or CHOICES.get((detail(q) or ("", ""))[1], {})
    if q.map:
        return {k: v for k, v in found.items() if k in q.map}
    if limits is not None:
        return {k: v for k, v in found.items() if lines(v, [limits.get(f) for f in q.fields])}
    return found


def paper_date(value: str) -> date | None:
    match = PAPER_DATE.match(value)
    try:
        return date(int(match[3]), int(match[2]), int(match[1])) if match else None
    except ValueError:
        return None


def lines(value: str, limits: list[int | None]) -> list[str] | None:
    """An answer over the lines of the paper form, word by word; None if it does not fit."""
    if len(limits) == 1:
        return [value] if limits[0] is None or len(value) <= limits[0] else None
    out = [""]
    for word in re.sub(r"\s*\n\s*", ", ", value).split():
        line = f"{out[-1]} {word}".strip()
        if limits[len(out) - 1] is None or len(line) <= limits[len(out) - 1]:
            out[-1] = line
        elif len(out) < len(limits) and (limits[len(out)] is None or len(word) <= limits[len(out)]):
            out.append(word)
        else:
            return None
    return out


def origins(profile: ProfileData, kept: dict[str, dict], facts: dict) -> dict[str, str]:
    """Placeholder -> "profile" or "kept": where a person's detail comes from, for the note beside the question."""
    relation = facts.get("subject")
    own = kept.get("self", {})
    out = {}
    for detail_, entry in FROM.items():
        fields = ENTRIES[entry][2]
        mine = "kept" if any(f in own for f in fields) else "profile"
        out[f"user.{detail_}"] = mine
        out[f"subject.{detail_}"] = mine if relation == "self" else "kept"
    return out


class Row(NamedTuple):
    question: FormQuestion
    section: FormSection
    value: str  # "" when empty
    source: str | None  # answer | profile | kept | fact | constant
    label: str | None  # for a fact: its value, e.g. "Pension von der PV"
    shown: bool  # its `when` holds: shown, checked and filled in


def prefill(q: FormQuestion, have: dict[str, str], origin: dict[str, str], facts: dict, limits: dict[str, int]):
    """(value, source, label) from the profile, the kept details, a chat fact or a constant; None if unknown."""
    if isinstance(q.value, FactValue):
        fact = facts.get(q.value.fact)
        value = q.value.map.get(fact) if isinstance(fact, str) else None
        return (value, "fact", value_label(q.value.fact, fact)) if value else None
    if not q.value:
        return None
    slots = SLOT.findall(q.value)
    if not slots:
        return q.value, "constant", None
    if any(s not in have for s in slots):
        return None
    single = detail(q)
    if single and single[1] in CHOICES:
        value = have[slots[0]]  # the code, e.g. "female"
        if value not in options(q, limits):
            return None
    else:
        value = SLOT.sub(lambda m: text(m[1], have[m[1]]), q.value)
        if lines(value, [limits.get(f) for f in q.fields]) is None:
            return None
    return value, "kept" if any(origin[s] == "kept" for s in slots) else "profile", None


def rows(form: Form, profile: ProfileData, kept: dict[str, dict], facts: dict, answers: dict[str, str]) -> list[Row]:
    """Every question of the sections that apply, except the manual ones, with its value, in the form's order."""
    have = known(*people(profile, kept, facts))
    origin = origins(profile, kept, facts)
    limits = max_lengths(form.file)
    state, out = dict(facts), []
    for section in form.sections:
        if section.when and check(section.when, facts) is not True:
            continue
        for q in section.questions:
            if q.manual:
                continue
            if q.id in answers:
                value, source, label = answers[q.id], "answer", None
            else:
                value, source, label = prefill(q, have, origin, facts, limits) or ("", None, None)
            shown = holds(q.when, state)
            if shown:
                state[q.id] = value or EMPTY
            out.append(Row(q, section, value, source, label, shown))
    return out


def findings(form: Form, found: list[Row], facts: dict) -> list[dict]:
    """What the review lists: required questions still open, then the form's checks that hold."""
    state = facts | {r.question.id: r.value or EMPTY for r in found if r.shown}
    missing = [
        {"kind": "missing", "question": r.question.id, "section": r.section.id, "label": r.question.label}
        for r in found
        if r.shown and r.question.required and not r.value
    ]
    return missing + [{"kind": "check", "text": c.text} for c in form.checks if holds(c.when, state)]


def progress(found: list[Row]) -> dict:
    required = [r for r in found if r.shown and r.question.required]
    return {"done": sum(bool(r.value) for r in required), "total": len(required)}


def condition_view(when: Condition | list[Condition] | None) -> list[dict]:
    conditions = when if isinstance(when, list) else [when] if when else []
    return [{k: {"not": v.not_} if isinstance(v, Not) else v for k, v in c.items()} for c in conditions]


def wizard(form: Form, profile: ProfileData, kept: dict[str, dict], facts: dict, answers: dict[str, str]) -> dict:
    """The wizard's model: each section with its questions, values and their source, the parts to fill in by hand
    and the review's findings. Values only go to the user, never to the LLM."""
    found = rows(form, profile, kept, facts, answers)
    limits = max_lengths(form.file)
    used = {key for r in found for c in condition_view(r.question.when) for key in c}

    def view(r: Row) -> dict:
        q, room = r.question, [limits.get(f) for f in r.question.fields]
        return {
            "id": q.id,
            "label": q.label,
            "kind": q.kind,
            "options": options(q, limits) if q.kind in CHOICE_KINDS else {},
            "help": q.help,
            "source_url": q.source_url,
            "required": q.required,
            "suggest": q.suggest,
            "max": None if None in room else sum(room) + len(room) - 1,
            "detail": (detail(q) or (None, None))[1],
            "when": condition_view(q.when),
            "value": r.value,
            "source": r.source,
            "source_label": r.label,
        }

    sections = [
        {
            "id": s.id, "title": s.title, "heading": s.heading, "page": s.page, "point": s.point,
            "questions": [view(r) for r in found if r.section is s],
        }
        for s in form.sections
    ]  # fmt: skip
    applies = {r.section.id for r in found}
    return {
        "sections": [s for s in sections if s["questions"]],
        "manual": [
            {"label": q.label, "page": q.page or s.page, "point": q.point or s.point}
            for s in form.sections
            if s.id in applies or not s.when
            for q in s.questions
            if q.manual
        ],
        "facts": {k: v for k, v in facts.items() if k in used},
        "findings": findings(form, found, facts),
        "progress": progress(found),
    }


def clean(form: Form, answers: dict[str, str]) -> dict[str, str]:
    """The answers as they are stored. ValueError with the question's id for the first one that is not valid."""
    questions = {q.id: q for q in form.questions if not q.manual}
    limits = max_lengths(form.file)
    out = {}
    for qid, raw in answers.items():
        q = questions.get(qid)
        if q is None:
            raise ValueError(qid)
        if q.kind == "multiline":
            value = "\n".join(" ".join(line.split()) for line in raw.strip().splitlines() if line.strip())
        else:
            value = " ".join(raw.split())
        whose = detail(q)
        if whose and whose[1] == "svnr":
            value = value.replace(" ", "")
        if value and not valid(q, value, limits):
            raise ValueError(qid)
        out[qid] = value
    return out


def valid(q: FormQuestion, value: str, limits: dict[str, int]) -> bool:
    if len(value) > MAX_ANSWER or any(ord(c) < 32 and c != "\n" for c in value):
        return False
    if q.kind in CHOICE_KINDS:
        return value in options(q, limits)
    if q.kind == "date" and paper_date(value) is None or q.kind == "number" and not value.isdigit():
        return False
    whose = detail(q)
    if whose and whose[1] in PERSON:
        try:
            PersonData(**{PERSON[whose[1]]: iso(value) if whose[1] == "birth_date" else value})
        except ValidationError:
            return False
    return lines(value, [limits.get(f) for f in q.fields]) is not None


def iso(paper: str) -> str:
    day = paper_date(paper)
    return day.isoformat() if day else paper


def merged(stored: dict[str, str], new: dict[str, str], prefills: list[Row]) -> dict[str, str]:
    """The stored answers with the new ones. A new answer equal to its prefill is dropped: the profile, the kept
    details or the chat stay its source."""
    before = {r.question.id: r.value for r in prefills}
    keep = {k: v for k, v in new.items() if k not in before or v != before[k]}
    return {k: v for k, v in stored.items() if k not in new} | keep


def entered(found: list[Row]) -> dict[str, dict]:
    """"user"/"subject" -> the person's details typed into the wizard, as PersonData fields, to keep them. Combined
    details like an address on one line are not kept: they cannot be split back."""
    out: dict[str, dict] = {"user": {}, "subject": {}}
    values = {detail(r.question): r for r in found if detail(r.question)}
    for (whose, name), r in values.items():
        if r.source != "answer":
            continue
        if name in PERSON:
            out[whose][PERSON[name]] = iso(r.value) if name == "birth_date" else r.value
        pair = {"last_name": ("first_name", "last_name"), "first_name": ("first_name", "last_name"),
                "street": ("street", "house"), "house": ("street", "house")}.get(name)  # fmt: skip
        if pair:
            parts = [values[(whose, p)].value if (whose, p) in values else "" for p in pair]
            out[whose]["full_name" if name in ("last_name", "first_name") else "street"] = " ".join(p for p in parts if p)
    return out


def wizard_fields(form: Form, found: list[Row]) -> dict[str, str]:
    """PDF field -> value for the questions shown. Manual questions are never in `found`, so they stay empty."""
    limits = max_lengths(form.file)
    out = {}
    for r in found:
        q = r.question
        if not (r.shown and r.value and q.fields):
            continue
        if q.map:
            if state := q.map.get(r.value):
                out[q.fields[0]] = state
        elif q.kind in CHOICE_KINDS:
            if label := options(q, limits).get(r.value):
                out[q.fields[0]] = label
        else:
            out |= dict(zip(q.fields, lines(r.value, [limits.get(f) for f in q.fields]) or []))
    answered = {r.question.id: r.value for r in found if r.shown and r.value}
    for fill in form.fills:
        names = FILL.findall(fill.value)
        value = FILL.sub(lambda m: answered.get(m[1], ""), fill.value)
        if all(n in answered for n in names) and lines(value, [limits.get(fill.field)]):
            out[fill.field] = value
    return out


def llm_question(q: FormQuestion) -> dict:
    """A question as the LLM sees it. Options of a person's details (e.g. sex) are left out with their answers."""
    out = {"id": q.id, "label": q.label, "kind": q.kind}
    if q.kind in CHOICE_KINDS and not detail(q):
        out["options"] = options(q)
    return out | ({"help": q.help} if q.help else {})


def llm_form(form: Form, found: list[Row], facts: dict) -> dict:
    """The form as the LLM sees it: the questions and help texts of the sections that apply, and the labels of the
    chat facts the form depends on. Never a value typed in or prefilled, never a manual question."""
    whens = [s.when for s in form.sections] + [c.when for c in form.checks] + [r.question.when for r in found]
    keys = {k for when in whens for c in condition_view(when) for k in c}
    keys |= {r.question.value.fact for r in found if isinstance(r.question.value, FactValue)}
    return {
        "form": form.title,
        "sections": [
            {"title": s.title, "heading": s.heading, "questions": [llm_question(r.question) for r in found if r.section is s]}
            for s in form.sections
            if any(r.section is s for r in found)
        ],
        "facts": [f"{FACTS[k].label}: {value_label(k, facts[k])}" for k in FACTS if k in keys and k in facts],
    }


def llm_answers(found: list[Row]) -> dict[str, str]:
    """The chosen options of the questions shown: codes like "yes", never a person's details or free text."""
    return {
        r.question.id: r.value
        for r in found
        if r.shown and r.value and r.question.kind in CHOICE_KINDS and not detail(r.question)
    }
