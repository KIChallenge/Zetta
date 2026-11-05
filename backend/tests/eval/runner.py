"""Eval sets (spec 14): offline with the expected facts (tests/test_eval.py), live with the real LLM.

Live run, from backend/ with a .env that has the API key:

    uv run python tests/eval/runner.py            # all splits
    uv run python tests/eval/runner.py held_out   # only measure the held-out set
    uv run python tests/eval/runner.py letters    # the discharge letters in tests/eval/letters/

Prints per case what went wrong and exits non-zero if the held-out set misses the threshold or any
contact data in the output is not from the corpus.
"""

import asyncio
import json
import re
import statistics
import sys
from pathlib import Path

import yaml

from backend import scripts
from backend.corpus import get_corpus
from backend.engine import evaluate
from backend.facts import UNKNOWN, merge
from backend.models import Plan, StepState, utcnow
from backend.pipeline import contact_view, render_plan
from backend.schemas import ProfileData

SETS = Path(__file__).parent
MAX_QUESTIONS = 3
THRESHOLD = 0.8  # open decision (spec 21.1): share of held-out cases that must pass
PROFILE = ProfileData(
    full_name="Anna Berger",
    street="Favoritenstraße 1",
    postal_code="1100",
    city="Wien",
    svnr="1237010180",
    phone="0660 1234567",
    contact_email="anna@example.at",
)
corpus = get_corpus()


def load() -> list[dict]:
    """All eval sets in this folder (one file per scenario)."""
    return [c for f in sorted(SETS.glob("*.yaml")) for c in yaml.safe_load(f.read_text(encoding="utf-8"))["cases"]]


def simulate(case: dict, facts: dict, medical: bool):
    """The chip loop after the first message: answers from the case, "Weiß nicht" for the rest."""
    facts, asked = dict(facts), 0
    while True:
        result = evaluate(facts, corpus, asked=asked, medical=medical)
        if result.kind != "question":
            return result, asked
        facts[result.question] = case.get("answers", {}).get(result.question, UNKNOWN)
        asked += 1


def passed(case: dict, result, asked: int) -> bool:
    if result.kind != case["expect"]:
        return False
    if result.kind != "plan":
        return True
    return asked <= case.get("max_questions", MAX_QUESTIONS) and set(case["services"]) <= {s["id"] for s in result.plan["services"]}


# Hallucination check (spec 14): every phone number, email and URL shown must be in the corpus.
PHONE = re.compile(r"\+?\d[\d \t/()-]{4,}\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://[^\s\"'<>]+")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?")


def _digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone.replace("(0)", ""))
    return "43" + digits[1:] if digits.startswith("0") else digits


def allowed(profile: ProfileData) -> tuple[set[str], set[str]]:
    """Phone numbers (as digits) and other strings the output may contain."""
    phones = {_digits(c.value) for i in corpus.institutions.values() for c in i.channels if c.type == "phone"}
    phones |= {_digits(d.phone) for d in corpus.directory.doctors}
    phones |= {_digits(profile.phone), re.sub(r"\D", "", profile.svnr)}
    texts = {corpus.model_dump_json(), profile.contact_email}
    return phones, texts


def violations(output: object, profile: ProfileData = PROFILE) -> list[str]:
    text = TIMESTAMP.sub("", json.dumps(output, ensure_ascii=False))
    for doctor in corpus.directory.doctors:
        text = text.replace(doctor.address, "")  # house numbers like "12 - 14/3" are not phone numbers
    phones, texts = allowed(profile)
    found = [m for m in URL.findall(text) if not any(m in t for t in texts)]
    text = URL.sub("", text)  # digits in URLs are not phone numbers
    found += [m for m in EMAIL.findall(text) if not any(m in t for t in texts)]
    return found + [m for m in PHONE.findall(text) if _digits(m) not in phones]


def rendered(graph: dict, written: dict[str, dict], facts: dict, now) -> dict:
    plan = Plan(chat_id="eval", version=1, graph=graph)
    states = {k: StepState(chat_id="eval", step_id=k, checks=[], script=v, updated_at=utcnow()) for k, v in written.items()}
    return render_plan(plan, states, PROFILE, facts, now)


async def live(split: str | None) -> int:
    from backend.hours import now
    from backend.llm import Llm

    llm = Llm()
    rows, failures, script_sources = [], 0, []
    for case in load():
        if split and case["split"] != split:
            continue
        extracted = await llm.extract(case["text"], None)
        facts = merge({}, extracted)
        result, asked = simulate(case, facts, extracted["medical_question"])
        ok = passed(case, result, asked)
        wrong = {k: (facts.get(k), v) for k, v in case["facts"].items() if facts.get(k) != v}
        bad: list[str] = []
        if result.kind == "plan":
            steps = [s for s in result.plan["steps"] if scripts.needs_text(s)]
            services = {s["id"]: s["title"] for s in result.plan["services"]}
            written = await scripts.generate(llm, steps, services, "short", corpus)
            script_sources += [w["source"] for w in written.values()]
            bad = violations(rendered(result.plan, written, facts, now()))
        else:
            bad = violations([contact_view(c.model_dump(mode="json", by_alias=True), now())
                              for i in corpus.institutions.values() for c in i.channels])  # fmt: skip
        failures += len(bad)
        rows.append((case, ok, asked))
        print(f"{'ok  ' if ok else 'FAIL'} {case['id']}: {result.kind}, {asked} questions"
              + (f", facts got/expected {wrong}" if wrong else "") + (f", NOT IN CORPUS {bad}" if bad else ""))  # fmt: skip

    code = 0
    for name in ("tuning", "held_out"):
        subset = [(ok, asked) for case, ok, asked in rows if case["split"] == name]
        if not subset:
            continue
        rate = sum(ok for ok, _ in subset) / len(subset)
        median = statistics.median(asked for _, asked in subset)
        print(f"{name}: {rate:.0%} passed ({len(subset)} cases), median {median} questions")
        if name == "held_out" and rate < THRESHOLD:
            code = 1
    if script_sources:
        print(f"scripts: {script_sources.count('llm')}/{len(script_sources)} passed validation (rest: fallback)")
    print(f"hallucination check: {failures} contact details not in the corpus")
    return 1 if failures else code


async def letters() -> int:
    """Each letter must yield exactly its expected recommendations, all with a checked quote."""
    from backend.documents import checked, pdf_text
    from backend.llm import Llm

    raw = Path(__file__).resolve().parents[2] / "data" / "raw"
    failed = 0
    for spec in sorted((SETS / "letters").glob("*.yaml")):
        case = yaml.safe_load(spec.read_text(encoding="utf-8"))
        text = pdf_text((raw / case["file"]).read_bytes())
        found = sorted(i["recommendation"] for i in checked(await Llm().recommendations(text), text))
        ok = found == sorted(case["expect"])
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {spec.stem}: {found}" + ("" if ok else f", expected {sorted(case['expect'])}"))
    return 1 if failed else 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(letters() if arg == "letters" else live(arg)))
