"""The closed fact schema (spec section 4): keys, allowed values, German labels, merge rules.

There is deliberately no key for diagnoses, symptoms, medications or risks.
"""

import re
from dataclasses import dataclass, field

UNKNOWN, DECLINED = "unknown", "declined"
SENTINELS = {UNKNOWN: "Weiß nicht", DECLINED: "Möchte ich nicht sagen"}

# Sources, strongest last: an extraction never overwrites a chip answer or an edit.
SOURCES = ("profile", "user_text", "chip", "document")

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
    extract: bool = True  # False: never taken from chat text (e.g. only from a confirmed letter)
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
            "some": "needs help with some tasks, e.g. shopping or cleaning, or needs help without saying how much",
            "a_lot": "needs care (Pflege), is being cared for by someone, or cannot manage daily life alone",
        },
    ),
    "goal": Fact(
        "Anliegen",
        {
            "apply_care_allowance": "Pflegegeld beantragen",
            "find_support_services": "Hilfe im Alltag finden",
            "in_hospital": "Gerade im Spital: Entlassung und Besuch",
            "after_hospital": "Nach dem Spital: Entlassungsbrief",
            "health_promotion": "Etwas für die Gesundheit tun",
            "child_offers": "Angebote für mein Kind",
            "doctor_appointment": "Arzttermin vereinbaren",
            "financial_help": "Finanzielle Hilfe",
        },
        "What the user wants to achieve. Only goals the user states or clearly implies.",
        multi=True,
        hints={
            "apply_care_allowance": "Pflegegeld: money for people who need care",
            "find_support_services": "help at home, e.g. home help, meals, nursing, someone to accompany",
            "in_hospital": "the person is in hospital now and has not come home yet, even if a discharge date is"
            " already planned (\"wird morgen entlassen\")",
            "after_hospital": "the person has already come home from hospital or already has the discharge letter"
            " (Entlassungsbrief) and asks what to organise now; if coming home is still in the future, use in_hospital"
            " instead, never both",
            "health_promotion": "do something for one's health: exercise, nutrition, check-ups, vaccinations",
            "child_offers": "offers for a child: check-ups, vaccinations, family allowance (Familienbeihilfe), counselling",
            "doctor_appointment": "get an appointment with a doctor",
            "financial_help": "own money problems, low or no income, social assistance (Mindestsicherung); not child benefits",
        },
    ),
    "hospital_topic": Fact(
        "Zum Spitalsaufenthalt",
        {"discharge": "Entlassung", "visit": "Besuch"},
        "What the user asks about a current hospital stay. Only if asked, not if they just mention the stay.",
        multi=True,
        hints={
            "discharge": "when the person will be discharged, how long they stay, or what to organise before they come home",
            "visit": "visiting the person in hospital, e.g. visiting hours or visitor rules",
        },
    ),
    "subject_age_band": Fact(
        "Alter",
        {"0-5": "0 bis 5 Jahre", "6-14": "6 bis 14 Jahre", "15-17": "15 bis 17 Jahre",
         "18-39": "18 bis 39 Jahre", "40-64": "40 bis 64 Jahre", "65+": "65 Jahre oder älter"},
        "Age of the person concerned, as a band. Only if stated.",
    ),
    "interests": Fact(
        "Interessiert an",
        {"exercise": "Bewegung", "nutrition": "Ernährung", "screening": "Vorsorgeuntersuchung", "vaccination": "Impfungen"},
        "Health topics the user is interested in.",
        multi=True,
    ),
    "appointment_reason": Fact(
        "Grund für den Termin",
        {"check_up": "Vorsorge oder Kontrolle", "follow_up": "Nachkontrolle", "acute": "Akute Beschwerden"},
        "Why the user wants a doctor's appointment. acute: current symptoms or complaints.",
    ),
    "specialty": Fact(
        "Fachrichtung",
        {"general_practice": "Allgemeinmedizin", "internal_medicine": "Innere Medizin", "gynaecology": "Frauenheilkunde",
         "paediatrics": "Kinderheilkunde", "dermatology": "Haut", "ophthalmology": "Augen", "ent": "Hals-Nasen-Ohren",
         "orthopaedics": "Orthopädie", "dentistry": "Zahnmedizin"},
        "The medical specialty the user asks for by name. Never derive it from symptoms.",
    ),
    "preferred_time": Fact(
        "Wann am liebsten",
        {"morning": "Vormittags", "afternoon": "Nachmittags", "any": "Egal"},
        "When the user prefers appointments or calls.",
    ),
    "documented_recommendations": Fact(
        "Laut Ihrem Brief",
        {
            "outpatient_rehab": "Ambulante Reha",
            "inpatient_rehab": "Stationäre Reha",
            "follow_up_check": "Kontrolle bei der Hausärztin oder beim Hausarzt",
            "medical_aid": "Heilbehelf oder Hilfsmittel",
            "home_nursing": "Hauskrankenpflege",
            "home_help": "Hilfe im Haushalt und bei der Körperpflege",
            "transport_to_treatment": "Fahrten zur Behandlung",
            "nutrition_counselling": "Ernährungsberatung",
        },
        "Recommendations written in a discharge letter, as confirmed by the user.",
        multi=True,
        extract=False,
        hints={
            "outpatient_rehab": "ambulant rehabilitation",
            "inpatient_rehab": "inpatient (stationär) rehabilitation stay",
            "follow_up_check": "a check-up with the GP or another doctor after discharge",
            "medical_aid": "a medical aid or device (Heilbehelf, Hilfsmittel), e.g. walker, bandage",
            "home_nursing": "nursing care at home (Hauskrankenpflege)",
            "home_help": "help with personal care, shopping, household or meals",
            "transport_to_treatment": "help getting to treatment appointments (transport)",
            "nutrition_counselling": "nutrition counselling (Ernährungsberatung)",
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
            " care services, appointments, preventive check-ups, vaccinations offered, when someone is discharged"
            " from or can be visited in hospital, or what to organise after a hospital stay or discharge letter. Wanting a doctor's appointment is not medical either; it is only"
            " medical if the user asks what is wrong, what to take or what to do about symptoms.",
        }
    }
    for key, fact in FACTS.items():
        if not fact.extract:
            continue
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


def extraction_guide() -> str:
    """The schema's meanings as text: some servers only enforce a schema's shape and never show the model its descriptions."""
    lines = []
    for key, field in extraction_schema()["properties"].items():
        enum = field["items"]["enum"] if "items" in field else next((o["enum"] for o in field.get("anyOf", []) if "enum" in o), [])
        # The description of `district` already says how to write its many values.
        allowed = f" Allowed: {', '.join(enum)}." if enum and key != "district" else ""
        lines.append(f"- {key}: {field['description']}{allowed}")
    return "\n".join(lines)


def merge(current: dict[str, tuple[object, str]], extracted: dict) -> dict[str, object]:
    """Facts from an extraction that may be stored: valid, non-empty, and not overriding a chip answer."""
    goals = extracted.get("goal")
    if isinstance(goals, list) and (extracted.get("hospital_topic") or "in_hospital" in goals):
        # A current stay rules out "after the stay": there is no discharge letter to ask for yet.
        extracted = {**extracted, "goal": [g for g in goals if g != "after_hospital"]}
    return {
        key: value
        for key, value in extracted.items()
        if key in FACTS
        and FACTS[key].extract
        and value not in (None, [])
        and valid(key, value)
        and (key not in current or current[key][1] != "chip")
    }
