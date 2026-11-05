"""Hallucination check (spec 14): every phone number, email and URL rendered must exist in the corpus."""

import asyncio
import itertools
from datetime import datetime

from backend import scripts
from backend.corpus import get_corpus
from backend.engine import QUESTION_CAP, evaluate
from backend.facts import FACTS
from backend.hours import VIENNA
from backend.pipeline import institution_view
from eval.runner import rendered, violations

corpus = get_corpus()
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=VIENNA)


class InventingLlm:
    """Writes scripts full of made-up contact data, as a careless LLM might."""

    async def scripts(self, steps, detail):
        out = {}
        for step in steps:
            ids = [i["id"] for i in step["items"]]
            text = "Rufen Sie 01 234 5678 an oder schreiben Sie an info@amt-wien.at, siehe www.amt-wien.at"
            if step["type"] == "call":
                out[step["step_id"]] = {"call": {"opening": text, "points": [{"covers": i, "text": text} for i in ids], "closing": text}}
            else:
                out[step["step_id"]] = {"email": {"subject": "Antrag", "body": text, "covers": ids}}
        return out


def all_plans():
    values = {key: [*fact.values] for key, fact in FACTS.items() if not fact.multi}
    values["district"] = ["1010", "1230", "unknown"]
    letter = [*FACTS["documented_recommendations"].values]
    for subject, payer, help_, alone, goal, recs in itertools.product(
        values["subject"], values["pension_payer"], values["needs_daily_help"], values["lives_alone"],
        [[], ["apply_care_allowance"], ["find_support_services"]], [[], letter],
    ):  # fmt: skip
        facts = {"subject": subject, "pension_payer": payer, "needs_daily_help": help_, "lives_alone": alone,
                 "goal": goal, "documented_recommendations": recs}  # fmt: skip
        quotes = {r: "Laut Brief empfohlen" for r in recs}
        result = evaluate({k: v for k, v in facts.items() if v != []}, corpus, asked=QUESTION_CAP, quotes=quotes)
        if result.plan:
            yield facts, result.plan


def test_doctor_lists_show_only_directory_data():
    for specialty in ["general_practice", "dermatology", "paediatrics"]:
        facts = {"goal": ["doctor_appointment"], "appointment_reason": "check_up", "specialty": specialty,
                 "district": "1100", "preferred_time": "morning"}  # fmt: skip
        plan = evaluate(facts, corpus).plan
        assert violations(rendered(plan, {}, facts, NOW)) == []


def test_plans_show_only_corpus_contact_data_even_if_the_llm_invents_some():
    plans = list(all_plans())
    assert len(plans) > 100
    for facts, graph in plans:
        steps = [s for s in graph["steps"] if scripts.needs_text(s)]
        services = {s["id"]: s["title"] for s in graph["services"]}
        written = asyncio.run(scripts.generate(InventingLlm(), steps, services, "short", corpus))
        assert {w["source"] for w in written.values()} <= {"fallback"}
        assert violations(rendered(graph, written, facts, NOW)) == [], facts


def test_cards_show_only_corpus_contact_data():
    for card in corpus.cards.values():
        assert violations([institution_view(corpus.institutions[i], NOW) for i in card.contacts]) == []


def test_the_check_finds_made_up_data():
    assert violations({"text": "Rufen Sie 01 234 5678 an, info@amt-wien.at, https://amt-wien.at"}) == [
        "https://amt-wien.at", "info@amt-wien.at", "01 234 5678",
    ]  # fmt: skip
