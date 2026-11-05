"""Speaking scripts and emails (spec section 8): placeholders only, validated, corpus fallback.

The LLM never sees personal values. It writes {user.name}; `fill` puts the value in at render time.
"""

import hashlib
import json
import logging
import re

from backend.corpus import Corpus
from backend.facts import subject_words
from backend.schemas import ProfileData

logger = logging.getLogger(__name__)

SLOT = re.compile(r"\{([a-z_]+\.[a-z_]+)\}")
# Slot -> gap label; {gen} becomes "Ihrer Mutter" etc.
SLOTS = {
    "user.name": "Ihr Name",
    "user.phone": "Ihre Telefonnummer",
    "user.email": "Ihre E-Mail-Adresse",
    "user.address": "Ihre Adresse",
    "user.svnr": "Ihre SV-Nummer",
    "subject.name": "Name {gen}",
    "subject.svnr": "SV-Nummer {gen}",
    "subject.relation": "",  # always has a value
}

# Contact data, dates and amounts only ever come from the corpus or the profile (8.3).
FORBIDDEN = {
    "phone number": re.compile(r"\+?\d[\d \t/()-]{4,}\d|\d{3,}"),
    "email address": re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),
    "url": re.compile(r"https?://|www\.|\b[\w-]+\.(at|com|org|net|eu|de|info)\b", re.I),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}\s?\d{4}"),
    "date": re.compile(
        r"\b\d{1,2}\.\s?\d{1,2}\.|\b\d{1,2}\.\s?(Jänner|Januar|Februar|März|April|Mai|Juni|Juli|August|"
        r"September|Oktober|November|Dezember)",
        re.I,
    ),
    "amount": re.compile(r"[€$]|\b(EUR|Euro)\b", re.I),
}
# Diagnosis and medication wording (spec 10). Scripts are about administration only.
MEDICAL = re.compile(
    r"diagnos|symptom|medikament|tablette|dosis|dosier|\bmg\b|krebs|tumor|demenz|alzheimer|parkinson|"
    r"schlaganfall|herzinfarkt|diabetes|depression|schmerz|insulin|chemo|bestrahlung|blutdruck|blutwert|"
    r"infektion|fieber|therapie",
    re.I,
)
LIMITS = {"opening": 300, "point": 300, "closing": 300, "subject": 150, "body": 2000, "intro": 120}


def slot_values(profile: ProfileData, facts: dict) -> dict[str, str | None]:
    place = f"{profile.postal_code} {profile.city}".strip()
    svnr = profile.svnr and f"{profile.svnr[:4]} {profile.svnr[4:]}"
    values = {
        "user.name": profile.full_name,
        "user.phone": profile.phone,
        "user.email": profile.contact_email,
        "user.address": ", ".join(p for p in (profile.street, place) if p),
        "user.svnr": svnr,
        "subject.relation": subject_words(facts)[1],
        "subject.name": "",
        "subject.svnr": "",
    }
    if facts.get("subject") == "self":
        values["subject.name"], values["subject.svnr"] = values["user.name"], values["user.svnr"]
    return {k: v or None for k, v in values.items()}


def gap(slot: str, facts: dict) -> str:
    if facts.get("subject") == "self" and slot.startswith("subject."):
        slot = slot.replace("subject.", "user.")
    return "[" + SLOTS[slot].format(gen=subject_words(facts)[2]) + "]"


def fill(text: str, values: dict[str, str | None], facts: dict) -> str:
    return SLOT.sub(lambda m: values.get(m[1]) or gap(m[1], facts), text)


def texts(script: dict) -> list[tuple[str, str]]:
    """(limit name, text) pairs of a call or email script."""
    if "call" in script:
        call = script["call"]
        return [("opening", call["opening"]), *(("point", p["text"]) for p in call["points"]), ("closing", call["closing"])]
    email = script["email"]
    return [("subject", email["subject"]), ("body", email["body"])]


def check_text(text: str, limit: str, slots: list[str]) -> list[str]:
    errors = [f"contains a {name}" for name, pattern in FORBIDDEN.items() if pattern.search(SLOT.sub("", text))]
    if MEDICAL.search(text):
        errors.append("contains medical wording")
    if len(text) > LIMITS[limit]:
        errors.append(f"{limit} longer than {LIMITS[limit]} characters")
    if unknown := set(SLOT.findall(text)) - set(slots):
        errors.append(f"unknown placeholders {sorted(unknown)}")
    if not text.strip():
        errors.append(f"empty {limit}")
    return errors


def validate(script: dict, step: dict) -> list[str]:
    """Reasons to reject a script for this step; empty if it may be used."""
    if ("call" in script) != (step["type"] == "call"):
        return [f"not a script for a {step['type']} step"]
    must = {item["id"] for item in step["must"]}
    if "call" in script:
        covered = [p["covers"] for p in script["call"]["points"]]
    else:
        covered = script["email"]["covers"]
    errors = []
    if missing := must - set(covered):
        errors.append(f"does not cover {sorted(missing)}")
    if extra := set(covered) - must:
        errors.append(f"covers unknown items {sorted(extra)}")
    for limit, text in texts(script):
        errors += check_text(text, limit, step["slots"])
    return errors


def fallback(step: dict, corpus: Corpus) -> dict:
    """The corpus script, without points for items that do not apply (e.g. "as a relative" for oneself)."""
    service_id, template_id = step["id"].split(".")
    service = next(s for s in corpus.services if s.id == service_id)
    template = next(t for t in service.steps if t.id == template_id)
    script = template.fallback_script.model_dump()
    must = {item["id"] for item in step["must"]}
    if step["type"] == "call":
        script["points"] = [p for p in script["points"] if p["covers"] in must]
        return {"call": script}
    script["covers"] = [c for c in script["covers"] if c in must]
    return {"email": script}


def inputs_hash(step: dict, detail: str) -> str:
    """Scripts are regenerated only when what the LLM gets for this step changes (8.5)."""
    key = [step["id"], step["type"], step["must"], step["slots"], step["script_facts"], step.get("institution"), detail]
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def llm_input(step: dict, services: dict[str, str]) -> dict:
    """What the LLM gets for one step: no contact data, no personal values."""
    return {
        "step_id": step["id"],
        "type": step["type"],
        "service": services[step["service"]],
        "institution": step["institution"]["name"],
        "items": step["must"],
        "placeholders": step["slots"],
        "facts": step["script_facts"],
    }


def needs_text(step: dict) -> bool:
    return step["type"] in ("call", "email")


def render(script: dict, step: dict, profile: ProfileData, facts: dict) -> dict:
    """The script with personal values filled in, plus what to have ready."""
    values = slot_values(profile, facts)
    used = set(SLOT.findall(json.dumps(script, ensure_ascii=False)))
    ready = list(dict.fromkeys([*step["have_ready"], *(s for s in step["slots"] if s in used)]))
    have_ready = [
        {"label": gap(s, facts)[1:-1], "value": values[s]}
        for s in ready
        if s in step["have_ready"] or values[s] is None
    ]
    if "call" in script:
        call = script["call"]
        out = {
            "opening": fill(call["opening"], values, facts),
            "points": [{"covers": p["covers"], "text": fill(p["text"], values, facts)} for p in call["points"]],
            "closing": fill(call["closing"], values, facts),
        }
    else:
        email = script["email"]
        out = {"subject": fill(email["subject"], values, facts), "body": fill(email["body"], values, facts)}
    return {**out, "have_ready": [h for h in have_ready if h["label"]]}


def plain(step: dict, profile: ProfileData, facts: dict, corpus: Corpus) -> dict | None:
    """The corpus script with its placeholders still in, for the frontend to show next to its translation."""
    values = slot_values(profile, facts)
    try:
        script = fallback(step, corpus)
    except StopIteration:  # an old plan whose step is no longer in the corpus: shown in German only
        return None
    return {
        "template": script.get("call") or script["email"],
        "slots": {s: {"value": values[s], "gap": gap(s, facts)[1:-1] if values[s] is None else ""} for s in step["slots"]},
    }


async def generate(llm, steps: list[dict], services: dict[str, str], detail: str, corpus: Corpus) -> dict[str, dict]:
    """One batched LLM call for all steps; rejected ones are retried once, then get the corpus fallback."""
    result: dict[str, dict] = {}
    pending = steps
    for _ in range(2):
        if not pending:
            break
        try:
            out = await llm.scripts([llm_input(s, services) for s in pending], detail)
        except Exception:
            logger.exception("Script generation failed")
            out = {}
        failed = []
        for step in pending:
            script = out.get(step["id"])
            errors = validate(script, step) if script else ["missing"]
            if errors:
                # Logged for corpus and prompt work (8.3).
                logger.warning("Script for %s rejected: %s", step["id"], "; ".join(errors))
                failed.append(step)
            else:
                result[step["id"]] = {**script, "source": "llm"}
        pending = failed
    for step in pending:
        result[step["id"]] = {**fallback(step, corpus), "source": "fallback"}
    return result
