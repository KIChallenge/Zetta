"""Corpus checks (spec 5.2): run in CI, so a broken or stale record never reaches a user."""

import os
from datetime import date

import pytest

from backend import scripts
from backend.corpus import Not, get_corpus
from backend.engine import _order, _step
from backend.facts import FACTS, SENTINELS

corpus = get_corpus()
MAX_AGE_DAYS = int(os.environ.get("CORPUS_MAX_AGE_DAYS", "90"))
SERVICES = {s.id: s for s in corpus.services}
TEMPLATES = [(s, t) for s in corpus.services for t in s.steps]


def conditions():
    """Every condition in the corpus, with where it is."""
    for s in corpus.services:
        yield from ((f"{s.id} trigger", c) for c in s.triggers)
        yield from ((f"{s.id} criterion {c.id}", c.when) for c in s.criteria)
        yield from ((f"{s.id} responsible", r.when) for r in s.responsible if r.when)
        for t in s.steps:
            yield from ((f"{s.id}.{t.id} item {i.id}", i.when) for i in [*t.must_ask, *t.must_include] if i.when)


def test_conditions_use_known_facts_and_values():
    for where, condition in conditions():
        for key, matcher in condition.items():
            assert key in FACTS, where
            values = matcher.not_ if isinstance(matcher, Not) else matcher
            assert set(values) <= set(FACTS[key].values), where


def test_references_resolve():
    for s in corpus.services:
        for rule in s.responsible:
            assert rule.institution in corpus.institutions, s.id
        assert s.responsible[-1].when is None, f"{s.id}: the last responsible rule is the default"
        assert set(s.documents) <= set(corpus.documents), s.id
        assert set(s.forms) <= set(corpus.forms), s.id
        assert set(s.requires) <= set(FACTS), s.id
        ids = [t.id for t in s.steps]
        assert len(ids) == len(set(ids)), s.id
        for t in s.steps:
            assert set(t.after) <= set(ids), f"{s.id}.{t.id}"
            assert set(t.script_facts) <= set(FACTS), f"{s.id}.{t.id}"
            assert not t.form or t.form in corpus.forms, f"{s.id}.{t.id}"
            if t.institution and t.institution != "responsible":
                assert t.institution in corpus.institutions
    for form in corpus.forms.values():
        assert form.submit_to in corpus.institutions, form.id
    for card in corpus.cards.values():
        assert set(card.contacts) <= set(corpus.institutions)


def test_step_channels_exist_or_the_institution_has_none():
    """A missing channel only degrades to "contact not in the Lotse yet" for institutions without channels."""
    for s, t in TEMPLATES:
        if t.type not in ("call", "email"):
            continue
        assert t.institution, f"{s.id}.{t.id}"
        targets = [r.institution for r in s.responsible] if t.institution == "responsible" else [t.institution]
        wanted = "phone" if t.type == "call" else "email"
        for target in targets:
            channels = corpus.institutions[target].channels
            assert not channels or any(
                c.type == wanted and (t.channel is None or c.id == t.channel) for c in channels
            ), f"{s.id}.{t.id} -> {target}"


def test_phone_channels_have_hours():
    for institution in corpus.institutions.values():
        for channel in institution.channels:
            if channel.type == "phone":
                assert channel.hours is not None, f"{institution.id}.{channel.id}: hours or not_stated"


def test_records_have_a_source_and_are_fresh():
    records = [*corpus.institutions.values(), *corpus.documents.values(), *corpus.forms.values(), *corpus.services]
    for record in records:
        assert record.source_url.startswith("https://"), record.id
        age = (date.today() - record.verified_at).days
        assert age <= MAX_AGE_DAYS, f"{record.id} was verified {age} days ago: check it against the source again"


def test_fallback_scripts_pass_validation_with_all_items():
    for s, t in TEMPLATES:
        if t.type not in ("call", "email"):
            continue
        assert t.fallback_script, f"{s.id}.{t.id}"
        assert set(t.have_ready) <= set(t.slots) <= set(scripts.SLOTS), f"{s.id}.{t.id}"
        items = t.must_ask if t.type == "call" else t.must_include
        assert items, f"{s.id}.{t.id}"
        step = {"id": f"{s.id}.{t.id}", "type": t.type, "must": [{"id": i.id} for i in items], "slots": t.slots}
        assert scripts.validate(scripts.fallback(step, corpus), step) == [], f"{s.id}.{t.id}"


def test_required_facts_have_a_question():
    asked = [q.fact_key for q in corpus.questions]
    assert len(asked) == len(set(asked))
    assert set(asked) <= set(FACTS)
    for s in corpus.services:
        assert set(s.requires) <= set(asked), s.id
    for q in corpus.questions:
        for chip in q.chips or []:
            assert chip.value in FACTS[q.fact_key].values or chip.value in SENTINELS, q.fact_key


def test_every_fact_key_is_used():
    """The schema cannot grow without a reason (spec 4 and 16)."""
    used = {q.fact_key for q in corpus.questions}
    used |= {key for _, condition in conditions() for key in condition}
    used |= {key for s in corpus.services for key in s.requires}
    used |= {key for _, t in TEMPLATES for key in t.script_facts}
    assert set(FACTS) == used


def test_step_graphs_are_acyclic():
    for s in corpus.services:
        facts = {"subject": "mother"}
        steps = [_step(s, t, s.responsible[-1].institution, facts, corpus) for t in s.steps]
        _order(steps)  # raises on a cycle


def free_texts():
    for s in corpus.services:
        yield s.id, [s.title, s.summary, s.why or "", s.responsible_note or "", *s.checked_by, *(c.text for c in s.criteria)]
        for t in s.steps:
            fallback = t.fallback_script.model_dump_json() if t.fallback_script else ""
            items = [i.text for i in [*t.must_ask, *t.must_include]]
            yield f"{s.id}.{t.id}", [t.title, t.why, t.text or "", t.done_label or "", fallback, *items]
    for q in corpus.questions:
        yield q.fact_key, [*q.text.values(), q.why_we_ask, *(c.label or "" for c in q.chips or [])]
    for name, card in corpus.cards.items():
        yield name, [card.title, card.text]
    for d in corpus.documents.values():
        yield d.id, [d.title, d.where_to_get, d.notes or ""]


@pytest.mark.parametrize("pattern", ["phone number", "email address", "url"])
def test_free_texts_have_no_contact_data(pattern):
    """Contact data only ever comes from channels."""
    for where, texts in free_texts():
        for text in texts:
            assert not scripts.FORBIDDEN[pattern].search(scripts.SLOT.sub("", text)), f"{where}: {text}"
