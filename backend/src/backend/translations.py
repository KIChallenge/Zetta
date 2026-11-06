"""The interface in other languages: every German text a user can see, and the rules its translation must follow.

German stays the source everywhere: the corpus, the database and the API. The frontend looks each text up in
frontend/src/locales/<language>.json, built by scripts/translate.py. Nothing is translated at runtime, so the LLM
cannot put new contact data in front of a user.
"""

import re
from pathlib import Path

from backend import scripts
from backend.corpus import get_corpus
from backend.facts import DISTRICTS, FACTS, SENTINELS, SUBJECT_WORDS

LANGUAGES = {"en": "English", "fr": "French", "cs": "Czech", "sk": "Slovak", "sl": "Slovenian"}
FRONTEND_SRC = Path(__file__).resolve().parents[3] / "frontend" / "src"
LOCALES_DIR = FRONTEND_SRC / "locales"

# Texts from the backend's code. Those with variable parts are patterns in frontend/src/i18n.ts.
FROM_CODE = (
    "Hier ist Ihr Plan.",
    "Ihr Plan steht weiter oben. Unter „Mehr dazu“ steht bei jedem Thema, worum es geht.",
    "Dabei kann der Lotse leider nicht helfen. Er kennt Pflege, Nachsorge nach dem Spital, Vorsorge, Impfungen,"
    " Kinder, Arzttermine und Mindestsicherung in Wien.",
    "Dabei kann der Lotse leider nicht helfen. Er kennt Pflege, Nachsorge nach dem Spital, Vorsorge, Impfungen,"
    " Kinder, Arzttermine und Mindestsicherung in Wien. Ihr Plan steht weiter oben.",
    "Das steht in Ihrem Dokument. Stimmt das?",
    "In Ihrem Dokument habe ich keine Empfehlung gefunden, zu der der Lotse helfen kann.",
    "Erledigt",
    "Wartet auf Rückmeldung",
    "1 offener Schritt",
    "Alle Kassen",
    "Wahlarztpraxis, kein Kassenvertrag",
    "Kein Kassenvertrag: Sie zahlen die Behandlung zuerst selbst und bekommen meist nur einen Teil zurück.",
    "Eine Ordination aus der Liste",
    "Alles geklärt",
    "Sie melden sich bei mir",
    "Nicht erreicht",
    "E-Mail gesendet",
    "Antrag eingereicht",
    "Alles beisammen",
    "Gelesen",
    "Hochgeladen",
    "Termin vereinbart",
)
MARKED = re.compile(r"(?<![\w.$])[tk]\(\s*'((?:[^'\\]|\\.)*)'")
PLACEHOLDER = re.compile(r"\{[a-z_.]+\}")
NUMBER = re.compile(r"\d+")
# Words a reader cannot understand, which an LLM tends to leave in German. Other official terms stay in brackets.
UNTRANSLATED = re.compile(r"Kasse\b|Kassenvertrag|Kassenvertr|Wahlarzt|rund um die Uhr", re.I)
HOSPITAL = re.compile(r"\bSpital", re.I)


def corpus_sources() -> set[str]:
    """Everything shown from the corpus. Names of institutions and forms stay German: users need them on the phone."""
    corpus = get_corpus()
    found: set[str] = set(FROM_CODE) | set(SENTINELS.values())
    for fact in FACTS.values():
        found.add(fact.label)
        found |= {label for label in fact.values.values() if not any(d in label for d in DISTRICTS)}
    # Someone asking for themselves gets the "self" text of a question and the user's own labels for gaps.
    others = [words for subject, words in SUBJECT_WORDS.items() if subject != "self"]
    found |= {words[1] for words in SUBJECT_WORDS.values()}  # {subject.relation}
    found |= {label for label in scripts.SLOTS.values() if label and "{gen}" not in label}
    found |= {label.format(gen=words[2]) for label in scripts.SLOTS.values() if "{gen}" in label for words in others}
    for question in corpus.questions:
        found.add(question.text["self"])
        found |= {question.text["other"].replace("{subject.ihr}", words[0]) for words in others}
        found.add(question.why_we_ask)
        found |= {chip.label for chip in question.chips or [] if chip.label}
    for card in corpus.cards.values():
        found |= {card.title, card.text}
    for institution in corpus.institutions.values():
        found |= {channel.label for channel in institution.channels if channel.label}
    for document in corpus.documents.values():
        found |= {document.title, document.where_to_get, *([document.notes] if document.notes else [])}
    for service in corpus.services:
        found |= {service.title, service.summary, *service.checked_by, *(c.text for c in service.criteria)}
        found |= {season.label for season in service.available}
        found |= {text for text in (service.responsible_note, service.why) if text}
        for step in service.steps:
            found |= {step.title, step.why}
            found |= {text for text in (step.text, step.done_label, step.contact_label) if text}
            found |= {outcome.label for outcome in step.outcomes}
            script = step.fallback_script
            if script is None:
                continue
            if hasattr(script, "points"):
                found |= {script.opening, script.closing, *(point.text for point in script.points)}
            else:
                found |= {script.subject, script.body}
    return found


def frontend_sources() -> set[str]:
    """Everything marked with t('...') or k('...') in the frontend's code."""
    found: set[str] = set()
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix in (".ts", ".vue"):
            found |= {m.replace("\\'", "'") for m in MARKED.findall(path.read_text(encoding="utf-8"))}
    return found


def all_sources() -> set[str]:
    return {text for text in corpus_sources() | frontend_sources() if text.strip()}


def problems(source: str, translated: str, language: str = "") -> list[str]:
    """Reasons to reject a translation (spec 11): nothing may appear that the German text does not contain."""
    errors = []
    if UNTRANSLATED.search(translated) or (language != "sl" and HOSPITAL.search(translated)):  # "spital" is Slovenian
        errors.append("left a German word")
    if not translated.strip():
        errors.append("empty")
    if sorted(PLACEHOLDER.findall(source)) != sorted(PLACEHOLDER.findall(translated)):
        errors.append("placeholders differ")
    if sorted(NUMBER.findall(source)) != sorted(NUMBER.findall(translated)):
        errors.append("numbers differ")
    for name in ("email address", "url"):
        pattern = scripts.FORBIDDEN[name]
        if pattern.search(translated) and not pattern.search(source):
            errors.append(f"contains a new {name}")
    return errors
