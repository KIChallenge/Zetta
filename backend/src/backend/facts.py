"""The closed fact schema (spec section 4): keys, allowed values, German labels, merge rules.

There is deliberately no key for diagnoses, symptoms, medications or risks.
"""

import re
from dataclasses import dataclass, field

UNKNOWN, DECLINED = "unknown", "declined"
SENTINELS = {UNKNOWN: "Weiß nicht", DECLINED: "Möchte ich nicht sagen"}

# Sources, strongest last: an extraction never overwrites a chip answer or an edit.
SOURCES = ("profile", "user_text", "chip")

DISTRICTS = [
    "Innere Stadt", "Leopoldstadt", "Landstraße", "Wieden", "Margareten", "Mariahilf", "Neubau",
    "Josefstadt", "Alsergrund", "Favoriten", "Simmering", "Meidling", "Hietzing", "Penzing",
    "Rudolfsheim-Fünfhaus", "Ottakring", "Hernals", "Währing", "Döbling", "Brigittenau", "Floridsdorf",
    "Donaustadt", "Liesing",
]  # fmt: skip


@dataclass(frozen=True)
class Fact:
    label: str
    values: dict[str, str]  # value -> German label
    description: str  # for the extraction prompt
    multi: bool = False
    hints: dict[str, str] = field(default_factory=dict)  # value -> extra meaning for the LLM


FACTS: dict[str, Fact] = {
    "subject": Fact(
        "Für wen",
        {
            "self": "Für mich selbst",
            "mother": "Mutter",
            "father": "Vater",
            "partner": "Partner:in",
            "child": "Kind",
            "other_relative": "Andere Angehörige",
        },
        "The person who needs the help or service: the user themselves or a relative.",
    ),
    "district": Fact(
        "Bezirk",
        {
            **{f"1{n:02d}0": f"{n}., {name}" for n, name in enumerate(DISTRICTS, start=1)},
            "outside_vienna": "Außerhalb von Wien",
        },
        "Where the person who needs help lives: a Vienna postal code (district 1 = 1010, district 10 = 1100,"
        " district 23 = 1230) or outside_vienna for any place outside Vienna.",
    ),
    "pension_payer": Fact(
        "Pension",
        {
            "pv": "Pension von der PV",
            "bvaeb": "Pension von der BVAEB",
            "svs": "Pension von der SVS",
            "none": "Keine Pension",
        },
        "Which institution pays the pension of the person who needs help, or none if they get no pension.",
        hints={
            "pv": "Pensionsversicherung (PVA), most employees' pensions",
            "bvaeb": "civil servants, railway or mining",
            "svs": "self-employed, farmers",
        },
    ),
    "lives_alone": Fact(
        "Lebt allein",
        {"yes": "Ja", "no": "Nein"},
        "Whether the person who needs help lives alone. Only if stated.",
    ),
    "needs_daily_help": Fact(
        "Hilfe im Alltag",
        {"none": "Keine", "some": "Etwas", "a_lot": "Viel"},
        "How much help in daily life the person needs, as reported by the user (not assessed).",
        hints={
            "none": "manages daily life alone",
            "some": "needs help with some tasks, e.g. shopping or cleaning",
            "a_lot": "needs care (Pflege), is being cared for by someone, or cannot manage daily life alone",
        },
    ),
    "goal": Fact(
        "Anliegen",
        {"apply_care_allowance": "Pflegegeld beantragen", "find_support_services": "Hilfe im Alltag finden"},
        "What the user wants to achieve. Only goals the user states or clearly implies.",
        multi=True,
        hints={
            "apply_care_allowance": "Pflegegeld: money for people who need care",
            "find_support_services": "help at home, e.g. home help, meals, nursing, someone to accompany",
        },
    ),
}

VIENNA_POSTAL_CODE = re.compile(r"^1(0[1-9]|1\d|2[0-3])0$")

# Wording per subject: questions ("Ihre Mutter"), scripts after "für" ("meine Mutter"), gaps ("Name Ihrer Mutter").
SUBJECT_WORDS = {
    "self": ("Sie", "mich", ""),  # gaps use the user's own labels
    "mother": ("Ihre Mutter", "meine Mutter", "Ihrer Mutter"),
    "father": ("Ihr Vater", "meinen Vater", "Ihres Vaters"),
    "partner": ("Ihre Partnerin bzw. Ihr Partner", "meine Partnerin bzw. meinen Partner", "Ihrer Partnerin bzw. Ihres Partners"),
    "child": ("Ihr Kind", "mein Kind", "Ihres Kindes"),
    "other_relative": ("Ihre Angehörige bzw. Ihr Angehöriger", "eine Angehörige bzw. einen Angehörigen", "der betroffenen Person"),
    None: ("die betroffene Person", "die betroffene Person", "der betroffenen Person"),
}  # fmt: skip


def subject_words(facts: dict) -> tuple[str, str, str]:
    """(question nominative, script accusative, gap genitive) for the chat's subject."""
    return SUBJECT_WORDS.get(facts.get("subject"), SUBJECT_WORDS[None])


def is_sentinel(value: object) -> bool:
    return isinstance(value, str) and value in SENTINELS


def valid(key: str, value: object) -> bool:
    fact = FACTS.get(key)
    if fact is None:
        return False
    if is_sentinel(value):
        return True
    if fact.multi:
        return isinstance(value, list) and bool(value) and all(v in fact.values for v in value)
    return value in fact.values


def value_label(key: str, value: object) -> str:
    if is_sentinel(value):
        return SENTINELS[value]
    values = FACTS[key].values
    return ", ".join(values[v] for v in value) if isinstance(value, list) else values[value]


def extraction_schema() -> dict:
    """JSON schema for structured output: every fact key, nullable, plus the medical-question flag."""
    properties: dict[str, dict] = {
        "medical_question": {
            "type": "boolean",
            "description": "True if the user asks for medical advice: symptoms, diagnoses, medication, dosage,"
            " treatment, health risks or an emergency. False for questions about benefits, applications,"
            " care services or appointments.",
        }
    }
    for key, fact in FACTS.items():
        hints = "; ".join(f"{v}: {h}" for v, h in fact.hints.items())
        description = fact.description + (f" Values: {hints}." if hints else "")
        if fact.multi:
            properties[key] = {
                "type": "array",
                "items": {"type": "string", "enum": list(fact.values)},
                "description": description + " Empty if none.",
            }
        else:
            properties[key] = {
                "anyOf": [{"type": "string", "enum": [*fact.values, *SENTINELS]}, {"type": "null"}],
                "description": description
                + f" {UNKNOWN} if the user says they don't know, {DECLINED} if they don't want to say,"
                " null if not mentioned.",
            }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def merge(current: dict[str, tuple[object, str]], extracted: dict) -> dict[str, object]:
    """Facts from an extraction that may be stored: valid, non-empty, and not overriding a chip answer."""
    return {
        key: value
        for key, value in extracted.items()
        if key in FACTS
        and value not in (None, [])
        and valid(key, value)
        and (key not in current or current[key][1] != "chip")
    }
