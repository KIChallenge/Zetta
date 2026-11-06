"""The deterministic engine (spec section 6): pure functions over (facts, corpus). No I/O, no LLM."""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from backend.corpus import Channel, Condition, Corpus, Doctor, Not, Service, StepTemplate
from backend.facts import is_sentinel

QUESTION_CAP = 4
DOCTOR_LIMIT = 5
# Asked when nothing matches yet, so a vague first message (or a failed extraction) still leads somewhere.
ENTRY_FACT = "goal"
# Fact values that mean "this is acute": the acute card, never a plan (spec 10).
ACUTE = {"appointment_reason": "acute"}
DONE = ("done", "skipped")
# A call step that stays a call although the user does not want calls (no curated email for it).
NO_PHONE_NOTE = (
    "Zetta kennt dafür keinen anderen Weg als einen Anruf. "
    "Eine Person, der Sie vertrauen, kann mit diesem Text für Sie anrufen."
)


@dataclass
class Result:
    kind: str  # boundary | acute | out_of_scope | general | question | plan
    question: str | None = None  # fact key
    plan: dict | None = None


def _value(facts: dict, key: str) -> list | None:
    value = facts.get(key)
    if value is None or value == [] or is_sentinel(value):
        return None
    return value if isinstance(value, list) else [value]


def check(condition: Condition, facts: dict) -> bool | None:
    """True or False, or None while a fact it needs is unknown. Any False decides."""
    result: bool | None = True
    for key, matcher in condition.items():
        values = _value(facts, key)
        if values is None:
            result = None
            continue
        if isinstance(matcher, Not):
            ok = not set(values) & set(matcher.not_)
        else:
            ok = bool(set(values) & set(matcher))
        if not ok:
            return False
    return result


def candidates(facts: dict, corpus: Corpus) -> list[Service]:
    return [s for s in corpus.services if any(check(t, facts) for t in s.triggers)]


def next_question(services: list[Service], facts: dict, corpus: Corpus) -> str | None:
    """The missing fact most candidates need; ties go to the order in questions.yaml."""
    missing = Counter(key for s in services for key in s.requires if key not in facts)
    if not missing:
        return None
    order = [q.fact_key for q in corpus.questions]
    return min(missing, key=lambda key: (-missing[key], order.index(key)))


def evaluate(
    facts: dict,
    corpus: Corpus,
    asked: int = 0,
    medical: bool = False,
    quotes: dict[str, str] | None = None,
    today: date | None = None,
    phone_calls: bool = True,
) -> Result:
    """`asked`: questions since the last plan or card, for the cap. `quotes`: confirmed letter quotes.
    `phone_calls`: False if the user does not want calls, so they become emails where the corpus has one."""
    # Before the medical check: acute complaints are usually flagged as a medical question too.
    if any(facts.get(k) == v for k, v in ACUTE.items()):
        return Result("acute")
    if medical:
        return Result("boundary")
    if facts.get("district") == "outside_vienna":
        return Result("out_of_scope")
    found = candidates(facts, corpus)
    can_ask = asked < QUESTION_CAP
    if not found:
        if can_ask and ENTRY_FACT not in facts:
            return Result("question", question=ENTRY_FACT)
        return Result("general")
    if can_ask and (key := next_question(found, facts, corpus)):
        return Result("question", question=key)
    plan = build_plan(found, facts, corpus, quotes or {}, today or date.today(), phone_calls)
    if not plan["services"] and not plan["dropped"]:
        return Result("general")  # only hubs matched, and their answers led nowhere
    return Result("plan", plan=plan)


def eligibility(service: Service, facts: dict) -> tuple[str, list[dict]]:
    """likely (all criteria met), possible (some unknown) or not_met (any not met)."""
    rows = []
    for criterion in service.criteria:
        state = check(criterion.when, facts)
        rows.append({"text": criterion.text, "state": {True: "met", False: "not_met", None: "unknown"}[state]})
    states = {row["state"] for row in rows}
    return ("not_met" if "not_met" in states else "possible" if "unknown" in states else "likely"), rows


def responsible(service: Service, facts: dict) -> str | None:
    # The last rule has no `when` and is the default (checked by the corpus tests).
    return next((r.institution for r in service.responsible if r.when is None or check(r.when, facts)), None)


# What a call step's email version replaces when the user picks it (pipeline.effective).
EMAIL_FIELDS = ("type", "title", "contact", "must", "slots", "have_ready")


def _email_version(template: StepTemplate, institution_id: str | None, corpus: Corpus) -> StepTemplate | None:
    """The call as an email, if the corpus has one and the institution a curated address for it."""
    alt = template.by_email
    if alt is None:
        return None
    target = corpus.institutions[institution_id if template.institution == "responsible" else template.institution]
    if not any(c.type == "email" and (alt.channel is None or c.id == alt.channel) for c in target.channels):
        return None
    return template.model_copy(update={
        "type": "email", "title": alt.title, "channel": alt.channel, "slots": alt.slots,
        "have_ready": [s for s in template.have_ready if s in alt.slots], "must_include": alt.must_include,
        "by_email": None,
    })  # fmt: skip


def _step(
    service: Service, template: StepTemplate, institution_id: str | None, facts: dict, corpus: Corpus, phone_calls: bool = True
) -> dict:
    if email := _email_version(template, institution_id, corpus):
        written = _step(service, email, institution_id, facts, corpus)
        if not phone_calls:
            return written
        step = _step(service, template.model_copy(update={"by_email": None}), institution_id, facts, corpus)
        if step["type"] == "call":
            step["email"] = {k: written[k] for k in EMAIL_FIELDS}
        return step
    step = {
        "id": f"{service.id}.{template.id}",
        "service": service.id,
        "type": template.type,
        "title": template.title,
        "why": template.why,
        "after": [f"{service.id}.{a}" for a in template.after],
        "text": template.text,
        "done_label": template.done_label,
    }
    if template.outcomes:
        step["outcomes"] = [o.model_dump() for o in template.outcomes]
    if template.unlocked_by:
        step["unlocked_by"] = f"{service.id}.{template.unlocked_by}"
    if template.type == "documents":
        step["documents"] = [corpus.documents[d].model_dump(mode="json") for d in service.documents]
    if template.form:
        form = corpus.forms[template.form]
        step["form"] = {"id": form.id, "title": form.title, "url": form.url, "online_url": form.online_url}
    if template.contact_label:
        # Someone the user knows, like their own doctor: a script, but never a number from the system.
        step["institution"] = {"id": None, "name": template.contact_label, "address": None}
        _must(step, template, facts)
    elif template.institution:
        institution = corpus.institutions[
            institution_id if template.institution == "responsible" else template.institution
        ]
        step["institution"] = {"id": institution.id, "name": institution.name, "address": institution.address}
        if template.type in ("call", "email", "book"):
            wanted = {"call": "phone", "email": "email", "book": "web"}[template.type]
            channel = next(
                (c for c in institution.channels
                 if c.type == wanted and (template.channel is None or c.id == template.channel)),
                None,
            )  # fmt: skip
            if channel is None:
                # Never guess contact data: without a curated channel the step only names the institution.
                step["type"] = "info"
                step["text"] = (
                    f"Wenden Sie sich an: {institution.name}. Die Kontaktdaten sind in Zetta noch nicht hinterlegt."
                )
                return step
            step["contact"] = channel.model_dump(mode="json", by_alias=True)
            step["contact"]["source_url"] = channel.source_url or institution.source_url
            if template.type != "book":
                _must(step, template, facts)
    if not phone_calls and step["type"] == "call":
        step["phone_note"] = NO_PHONE_NOTE
    return step


def _must(step: dict, template: StepTemplate, facts: dict) -> None:
    items = template.must_ask if template.type == "call" else template.must_include
    # An item is left out only when its condition is known to be false.
    step["must"] = [{"id": i.id, "text": i.text} for i in items if i.when is None or check(i.when, facts) is not False]
    step["slots"] = template.slots
    step["have_ready"] = template.have_ready
    step["script_facts"] = {k: facts[k] for k in template.script_facts if k in facts}


def _contract_rank(doctor: Doctor) -> int:
    """Most people are insured with the ÖGK: its contracts first, a practice without any contract last."""
    if {"ALLE", "ÖGK"} & set(doctor.insurers):
        return 0
    return 1 if doctor.insurers else 2


def _contract(doctor: Doctor) -> str:
    if "ALLE" in doctor.insurers:
        return "Alle Kassen"
    return f"Kassen: {', '.join(doctor.insurers)}" if doctor.insurers else "Wahlarztpraxis, kein Kassenvertrag"


def _contract_warning(doctor: Doctor) -> str | None:
    """What the user pays attention to before calling a practice that may not take their insurance."""
    if _contract_rank(doctor) == 0:
        return None
    if doctor.insurers:
        return f"Vertrag nur mit: {', '.join(doctor.insurers)}. Bei einer anderen Kasse zahlen Sie die Behandlung zuerst selbst."
    return "Kein Kassenvertrag: Sie zahlen die Behandlung zuerst selbst und bekommen meist nur einen Teil zurück."


def _fits_time(doctor: Doctor, preferred: str | None) -> bool:
    """Whether the stated opening hours suit the preferred time; unknown hours never do."""
    hours = doctor.hours or []
    if preferred == "morning":
        return any(w.from_ < "12:00" for w in hours)
    if preferred == "afternoon":
        return any(w.to > "12:00" for w in hours)
    return bool(hours)


def find_doctors(facts: dict, corpus: Corpus) -> list[dict]:
    """The best practices for the chosen specialty: by contract, district, preferred time, then distance."""
    specialty = _value(facts, "specialty")
    if not specialty:
        return []  # Zetta never chooses a specialty for the user
    doctors = corpus.directory.doctors
    district = (_value(facts, "district") or [None])[0]
    time = (_value(facts, "preferred_time") or [None])[0]
    nearby = [d for d in doctors if d.postal_code == district]
    # The middle of the district's practices: good enough to rank neighbouring districts, no geocoding needed.
    lat = sum(d.lat for d in nearby) / len(nearby) if nearby else 0
    lon = sum(d.lon for d in nearby) / len(nearby) if nearby else 0

    def rank(d: Doctor) -> tuple:
        distance = (d.lat - lat) ** 2 + (d.lon - lon) ** 2 if nearby else 0
        return (_contract_rank(d), d.postal_code != district, not _fits_time(d, time), distance, d.id)

    # A group practice lists each doctor with the same number: one call, so one entry.
    by_phone: dict[str, Doctor] = {}
    for doctor in sorted((d for d in doctors if d.specialty == specialty[0]), key=rank):
        by_phone.setdefault(doctor.phone, doctor)
    return [
        {
            "id": d.id,
            "name": d.name,
            "address": d.address,
            "contract": _contract(d),
            "warning": _contract_warning(d),
            "warning_source": corpus.directory.cost_source if _contract_rank(d) else None,
            "contact": Channel(id=d.id, type="phone", value=d.phone, hours=d.hours, source_url=d.source_url).model_dump(
                mode="json", by_alias=True
            ),
        }
        for d in list(by_phone.values())[:DOCTOR_LIMIT]
    ]


def _order(steps: list[dict]) -> list[dict]:
    """Topological order, keeping the corpus order where the edges allow it."""
    ids = {s["id"] for s in steps}
    placed: set[str] = set()
    ordered: list[dict] = []
    while len(ordered) < len(steps):
        ready = [s for s in steps if s["id"] not in placed and all(a in placed or a not in ids for a in s["after"])]
        if not ready:
            raise ValueError("Step graph has a cycle")
        ordered.append(ready[0])
        placed.add(ready[0]["id"])
    return ordered


def _directory_step(service: Service, role: str) -> StepTemplate:
    return next(t for t in service.steps if t.directory == role)


def in_season(service: Service, today: date) -> bool:
    day = today.strftime("%m-%d")
    return not service.available or any(s.from_ <= day <= s.to for s in service.available)


def build_plan(
    services: list[Service],
    facts: dict,
    corpus: Corpus,
    quotes: dict[str, str] | None = None,
    today: date | None = None,
    phone_calls: bool = True,
) -> dict:
    kept, dropped, steps = [], [], []
    for service in sorted(services, key=lambda s: s.priority):
        if not in_season(service, today or date.today()):
            seasons = ", ".join(s.label for s in service.available)
            dropped.append({"id": service.id, "title": service.title, "reason": f"Gibt es nur {seasons}."})
            continue
        state, criteria = eligibility(service, facts)
        if state == "not_met":
            failed = next(c["text"] for c in criteria if c["state"] == "not_met")
            dropped.append({"id": service.id, "title": service.title, "reason": f"Voraussetzung nicht erfüllt: {failed}"})
            continue
        # An upload step is only shown until its result (the confirmed letter) is known.
        doctors = find_doctors(facts, corpus) if any(t.directory for t in service.steps) else []
        templates = [
            t
            for t in service.steps
            if not (t.type == "upload" and _value(facts, "documented_recommendations"))
            and not (t.directory == "fallback" and doctors)
        ]
        if not templates:
            continue
        institution_id = responsible(service, facts)
        kept.append({
            "id": service.id,
            "title": service.title,
            "summary": service.summary,
            "eligibility": state,
            "criteria": criteria,
            "checked_by": service.checked_by,
            "responsible": corpus.institutions[institution_id].name if institution_id else None,
            "quotes": [quotes[r] for r in service.quotes if quotes and r in quotes],
            "responsible_note": service.responsible_note,
            "responsible_source": service.responsible_source,
            "source_url": service.source_url,
        })
        steps += [_step(service, t, institution_id, facts, corpus, phone_calls) for t in templates]
        if doctors:
            step = next(s for s in steps if s["id"] == f"{service.id}.{_directory_step(service, 'list').id}")
            step["doctors"] = doctors
            step["doctors_source"] = {"url": corpus.directory.source, "scraped_at": corpus.directory.scraped_at.isoformat()}
            step["institution"]["name"] = "Eine Ordination aus der Liste"
            # The search the list comes instead of stays available, for anyone who wants more to choose from.
            search = _step(service, _directory_step(service, "fallback"), institution_id, facts, corpus, phone_calls)
            step["more"] = search.get("contact")

    # Document steps of several services become one checklist (spec 6.4).
    collect = [s for s in steps if s["type"] == "documents"]
    if collect:
        merged = {**collect[0], "id": "documents", "services": [s["service"] for s in collect], "documents": []}
        for s in collect:
            merged["documents"] += [d for d in s["documents"] if d not in merged["documents"]]
        old = {s["id"] for s in collect}
        steps = [merged if s is collect[0] else s for s in steps if s is collect[0] or s["id"] not in old]
        for s in steps:
            s["after"] = list(dict.fromkeys("documents" if a in old else a for a in s["after"]))
    return {"services": kept, "dropped": dropped, "steps": _order(steps)}


def visible(steps: list[dict], outcomes: dict[str, str | None]) -> list[dict]:
    """Steps of a branch appear only after the outcome that opens them (spec 7.3)."""
    reached = {f"{step}:{outcome}" for step, outcome in outcomes.items() if outcome}
    return [s for s in steps if s.get("unlocked_by", "") in reached or "unlocked_by" not in s]


def statuses(steps: list[dict], stored: dict[str, str | None]) -> dict[str, str]:
    """done/skipped as stored; otherwise available once every predecessor is done or skipped."""
    ids = {s["id"] for s in steps}
    finished = {i for i, status in stored.items() if status in DONE}
    return {
        s["id"]: stored.get(s["id"])
        if stored.get(s["id"]) in DONE
        else "available"
        if all(a in finished or a not in ids for a in s["after"])
        else "blocked"
        for s in steps
    }
