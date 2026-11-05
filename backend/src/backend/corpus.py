"""The curated corpus (spec section 5): YAML files in backend/corpus/, validated by pydantic.

References between records are checked by tests/test_corpus.py.
"""

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


class Document(Model):
    id: str
    title: str
    where_to_get: str
    notes: str | None = None
    source_url: str
    verified_at: date


class Form(Model):
    id: str
    title: str
    url: str
    online_url: str | None = None
    svbox_file: str | None = None
    submit_to: str
    source_url: str
    verified_at: date


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


class StepTemplate(Model):
    id: str
    type: Literal["call", "email", "form", "info", "wait", "documents", "upload"]
    title: str
    why: str
    institution: str | None = None  # an institution id, or "responsible"
    contact_label: str | None = None  # a call/email to someone outside the corpus, e.g. the user's own doctor
    channel: str | None = None
    form: str | None = None
    after: list[str] = []
    text: str | None = None
    done_label: str | None = None
    must_ask: list[Item] = []  # call
    must_include: list[Item] = []  # email
    slots: list[str] = []
    have_ready: list[str] = []
    script_facts: list[str] = []
    fallback_script: CallScript | EmailScript | None = None


class Rule(Model):
    when: Condition | None = None
    institution: str


class Criterion(Model):
    id: str
    text: str
    when: Condition


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
    )


@cache
def get_corpus() -> Corpus:
    return load()
