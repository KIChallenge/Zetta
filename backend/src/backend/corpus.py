"""The curated corpus (spec section 5): YAML files in backend/corpus/, validated by pydantic.

References between records are checked by tests/test_corpus.py.
"""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CLOCK = r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$"


class Model(BaseModel):
    # Typos in the YAML fail loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Not(Model):
    not_: list[str] = Field(alias="not")


# Fact key -> allowed values (fact is, or contains, one of them) or {not: [...]}. All keys must match.
Condition = dict[str, list[str] | Not]


class Window(Model):
    model_config = ConfigDict(populate_by_name=True)

    days: list[Day]
    from_: str = Field(alias="from", pattern=CLOCK)
    to: str = Field(pattern=CLOCK)


class Channel(Model):
    id: str
    type: Literal["phone", "email", "web", "visit"]
    value: str
    label: str | None = None
    hours: list[Window] | Literal["not_stated"] | None = None
    source_url: str | None = None


class Institution(Model):
    id: str
    name: str
    kind: str
    address: str | None = None
    channels: list[Channel]
    source_url: str
    verified_at: date


class Doctor(Model):
    """One practice from corpus/doctors.json, built by scripts/import_doctors.py."""

    id: str
    name: str
    specialty: str  # a value of the `specialty` fact
    postal_code: str
    address: str
    lat: float
    lon: float
    phone: str
    hours: list[Window] | None
    insurers: list[str]  # "ALLE" for all insurers, empty for no contract
    source_url: str


class DoctorDirectory(Model):
    source: str
    cost_source: str  # what a visit without a contract costs
    scraped_at: date
    doctors: list[Doctor]


class Document(Model):
    id: str
    title: str
    where_to_get: str
    notes: str | None = None
    source_url: str
    verified_at: date


class FactValue(Model):
    fact: str  # a chat fact
    map: dict[str, str]  # its value -> the answer


class FormQuestion(Model):
    """One question of a form wizard, in the form's own German wording. See the head of forms.yaml."""

    id: str
    label: str
    kind: Literal["text", "multiline", "date", "number", "choice", "yes_no", "checkbox"] = "text"
    pdf: str | list[str] = []  # a long answer is split over the lines of the paper form
    options: dict[str, str] = {}  # choice: answer -> label
    map: dict[str, str] = {}  # answer -> state of a checkbox or radio button; without it a choice writes its label
    value: str | FactValue | None = None  # the prefill: placeholders, a chat fact or a constant
    when: Condition | list[Condition] | None = None  # a list: any of them
    required: bool = False
    help: str | None = None
    source_url: str | None = None
    suggest: bool = False  # the LLM may draft it
    manual: bool = False  # always on paper: never prefilled, stored or sent to the LLM
    page: int | None = None
    point: int | None = None

    @property
    def fields(self) -> list[str]:
        return [self.pdf] if isinstance(self.pdf, str) else self.pdf


class FormSection(Model):
    id: str
    title: str  # the station on the wizard's progress line
    heading: str | None = None
    page: int | None = None
    point: int | None = None
    when: Condition | None = None  # facts only
    questions: list[FormQuestion]


class Check(Model):
    when: Condition | list[Condition]  # over chat facts and answers; a list: any of them
    text: str


class Fill(Model):
    field: str  # a PDF field the form asks for twice, e.g. a name
    value: str  # from other answers: "{last_name} {first_name}"


class Form(Model):
    id: str
    title: str
    url: str
    online_url: str | None = None
    file: str | None = None  # the blank PDF in corpus/forms; with `sections` the user fills it in with the wizard
    sections: list[FormSection] = []
    checks: list[Check] = []
    fills: list[Fill] = []
    submit_to: str
    source_url: str
    verified_at: date

    @property
    def questions(self) -> list[FormQuestion]:
        return [q for s in self.sections for q in s.questions]


class Item(Model):
    id: str
    text: str
    when: Condition | None = None


class Point(Model):
    covers: str
    text: str


class CallScript(Model):
    opening: str
    points: list[Point]
    closing: str


class EmailScript(Model):
    subject: str
    body: str
    covers: list[str]


class Outcome(Model):
    id: str
    label: str
    effect: Literal["done", "keep"]  # keep: the step stays open, e.g. to call again


class StepTemplate(Model):
    id: str
    type: Literal["call", "email", "form", "info", "wait", "documents", "upload", "book"]
    title: str
    why: str
    institution: str | None = None  # an institution id, or "responsible"
    contact_label: str | None = None  # a call/email to someone outside the corpus, e.g. the user's own doctor
    channel: str | None = None
    form: str | None = None
    after: list[str] = []
    text: str | None = None
    done_label: str | None = None
    # list: shows the matching practices from the directory. fallback: only shown when there are none.
    directory: Literal["list", "fallback"] | None = None
    must_ask: list[Item] = []  # call
    must_include: list[Item] = []  # email
    slots: list[str] = []
    have_ready: list[str] = []
    script_facts: list[str] = []
    fallback_script: CallScript | EmailScript | None = None
    outcomes: list[Outcome] = []  # empty: the defaults for the step type
    unlocked_by: str | None = None  # "<template id>:<outcome id>": shown only after that outcome


class Rule(Model):
    when: Condition | None = None
    institution: str


class Criterion(Model):
    id: str
    text: str
    when: Condition


class Season(Model):
    """A yearly date range, e.g. June to September, as month-day strings."""

    from_: str = Field(alias="from", pattern=r"^\d{2}-\d{2}$")
    to: str = Field(pattern=r"^\d{2}-\d{2}$")
    label: str  # e.g. "von Juni bis September"


class Service(Model):
    id: str
    title: str
    summary: str
    priority: int
    triggers: list[Condition]
    requires: list[str]
    responsible: list[Rule]  # empty: no institution is responsible (e.g. the user's own doctor)
    responsible_note: str | None = None
    responsible_source: str | None = None
    criteria: list[Criterion] = []
    checked_by: list[str] = []
    documents: list[str] = []
    forms: list[str] = []
    available: list[Season] = []  # empty: all year
    quotes: list[str] = []  # documented recommendations whose letter quotes the plan shows
    why: str | None = None
    source_url: str
    verified_at: date
    steps: list[StepTemplate]


class Chip(Model):
    value: str
    label: str | None = None


class Question(Model):
    fact_key: str
    text: dict[Literal["self", "other"], str]
    why_we_ask: str
    chips: list[Chip] | None = None
    multi: bool = False  # several chips can be picked


class Card(Model):
    title: str
    text: str
    contacts: list[str]


class Corpus(Model):
    institutions: dict[str, Institution]
    documents: dict[str, Document]
    forms: dict[str, Form]
    services: list[Service]
    questions: list[Question]
    cards: dict[Literal["boundary", "out_of_scope", "general"], Card]
    directory: DoctorDirectory

    def question(self, fact_key: str) -> Question:
        return next(q for q in self.questions if q.fact_key == fact_key)


def load(directory: Path = CORPUS_DIR) -> Corpus:
    def read(name: str):
        return yaml.safe_load((directory / f"{name}.yaml").read_text(encoding="utf-8"))

    def by_id(name: str) -> dict:
        records = read(name)
        ids = [record["id"] for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate ids in {name}.yaml")
        return {record["id"]: record for record in records}

    return Corpus(
        institutions=by_id("institutions"),
        documents=by_id("documents"),
        forms=by_id("forms"),
        services=read("services"),
        questions=read("questions"),
        cards=read("cards"),
        directory=json.loads((directory / "doctors.json").read_text(encoding="utf-8")),
    )


@cache
def get_corpus() -> Corpus:
    return load()
