"""One turn (spec section 3): user text or chip answer -> facts -> engine -> question | plan | card."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi.sse import ServerSentEvent
from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from backend import scripts
from backend.corpus import Corpus, Institution, get_corpus
from backend.engine import DONE, evaluate, statuses, visible
from backend.facts import FACTS, SENTINELS, VIENNA_POSTAL_CODE, merge, subject_words, value_label
from backend.hours import now as vienna_now
from backend.hours import reachable, summary
from backend.llm import Llm
from backend.models import Chat, ChatFact, Message, Plan, Profile, StepState, utcnow
from backend.schemas import MessageResponse, ProfileData

logger = logging.getLogger(__name__)

# Outcome id -> (label, effect). "keep" leaves the step open, e.g. to call again in the next window.
OUTCOMES = {
    "call": {"reached": ("Alles geklärt", "done"), "callback": ("Sie melden sich bei mir", "done"),
             "not_reached": ("Nicht erreicht", "keep")},
    "email": {"sent": ("E-Mail gesendet", "done")},
    "form": {"submitted": ("Antrag eingereicht", "done")},
    "documents": {"ready": ("Alles beisammen", "done")},
    "wait": {"received": ("Erledigt", "done")},
    "info": {"read": ("Gelesen", "done")},
    "upload": {"uploaded": ("Hochgeladen", "done")},
    "book": {"booked": ("Termin vereinbart", "done")},
}  # fmt: skip


def outcomes_of(step: dict) -> dict[str, tuple[str, str]]:
    """Outcome id -> (label, effect): from the corpus step, else the defaults for its type."""
    if "outcomes" in step:
        return {o["id"]: (o["label"], o["effect"]) for o in step["outcomes"]}
    return OUTCOMES[step["type"]]


def shown(plan: Plan, states: dict[str, StepState]) -> list[dict]:
    return visible(plan.graph["steps"], {k: s.outcome for k, s in states.items()})


def profile_of(db: Session, user_id: str) -> ProfileData:
    row = db.get(Profile, user_id)
    return ProfileData.model_validate(row) if row else ProfileData()


def fact_rows(db: Session, chat_id: str) -> dict[str, ChatFact]:
    return {f.key: f for f in db.scalars(select(ChatFact).where(ChatFact.chat_id == chat_id))}


def chips(key: str) -> list[dict]:
    return [{"value": v, "label": label} for v, label in [*FACTS[key].values.items(), *SENTINELS.items()]]


def fact_list(rows: dict[str, ChatFact]) -> list[dict]:
    """The "Verstanden" chips: what the plan is based on, each editable."""
    return [
        {
            "key": key,
            "label": FACTS[key].label,
            "value": rows[key].value,
            "value_label": value_label(key, rows[key].value),
            "source": rows[key].source,
            "chips": chips(key),
        }
        for key in FACTS
        if key in rows
    ]


def set_fact(db: Session, chat_id: str, rows: dict[str, ChatFact], key: str, value, source: str) -> None:
    row = rows.get(key)
    if row is None:
        row = rows[key] = ChatFact(chat_id=chat_id, key=key)
        db.add(row)
    row.value, row.source, row.updated_at = value, source, utcnow()


def assistant_messages(db: Session, chat_id: str, limit: int = 10) -> list[Message]:
    """Newest first."""
    return list(db.scalars(
        select(Message)
        .where(Message.chat_id == chat_id, Message.role == "assistant")
        .order_by(literal_column("messages.rowid").desc())
        .limit(limit)
    ))  # fmt: skip


def pending_question(db: Session, chat_id: str) -> Message | None:
    last = assistant_messages(db, chat_id, 1)
    return last[0] if last and last[0].kind == "question" else None


def questions_asked(db: Session, chat_id: str) -> int:
    """Questions since the last plan or card, for the question cap."""
    asked = 0
    for message in assistant_messages(db, chat_id, 20):
        if message.kind != "question":
            break
        asked += 1
    return asked


def contact_view(channel: dict, now: datetime) -> dict:
    view = {k: channel.get(k) for k in ("type", "value", "label", "source_url")}
    if channel["type"] == "phone":
        digits = "".join(c for c in channel["value"].replace("(0)", "") if c.isdigit() or c == "+")
        # Austrian numbers with a leading 0 get the country code; short codes like 1450 stay as they are.
        view["href"] = "tel:" + ("+43" + digits[1:] if digits.startswith("0") else digits)
    elif channel["type"] == "email":
        view["href"] = "mailto:" + channel["value"]
    elif channel["type"] == "web":
        view["href"] = channel["value"]
    hours = channel.get("hours")
    if isinstance(hours, list):
        view["hours"] = summary(hours)
        view["reachable"] = reachable(hours, now)
    return view


def institution_view(institution: Institution, now: datetime) -> dict:
    return {
        "name": institution.name,
        "address": institution.address,
        "channels": [contact_view(c.model_dump(mode="json", by_alias=True), now) for c in institution.channels],
        "source_url": institution.source_url,
    }


def message_response(message: Message, corpus: Corpus | None = None, now: datetime | None = None) -> MessageResponse:
    """Card contacts are stored as ids and expanded here, so hours and "jetzt erreichbar" are current."""
    payload = message.payload
    if message.kind == "card" and payload:
        corpus, now = corpus or get_corpus(), now or vienna_now()
        payload = {
            **payload,
            "contacts": [institution_view(corpus.institutions[i], now) for i in payload["contacts"]],
        }
    return MessageResponse.model_validate(message).model_copy(update={"payload": payload})


def latest_plan(db: Session, chat_id: str) -> Plan | None:
    return db.scalar(select(Plan).where(Plan.chat_id == chat_id).order_by(Plan.version.desc()).limit(1))


def step_states(db: Session, chat_id: str) -> dict[str, StepState]:
    return {s.step_id: s for s in db.scalars(select(StepState).where(StepState.chat_id == chat_id))}


def status_text(steps: list[dict], status: dict[str, str]) -> str:
    """For the chat sidebar: "3 offene Schritte", "Wartet auf Rückmeldung" or "Erledigt"."""
    open_ = [s for s in steps if status[s["id"]] not in DONE]
    if not open_:
        return "Erledigt"
    if all(s["type"] == "wait" for s in open_ if status[s["id"]] == "available"):
        return "Wartet auf Rückmeldung"
    return "1 offener Schritt" if len(open_) == 1 else f"{len(open_)} offene Schritte"


def chat_status(db: Session, chat_id: str) -> str | None:
    if plan := latest_plan(db, chat_id):
        states = step_states(db, chat_id)
        steps = shown(plan, states)
        return status_text(steps, statuses(steps, {k: s.status for k, s in states.items()}))
    return "Frage offen" if pending_question(db, chat_id) else None


def render_plan(plan: Plan, states: dict[str, StepState], profile: ProfileData, facts: dict, now: datetime) -> dict:
    steps = shown(plan, states)
    status = statuses(steps, {k: s.status for k, s in states.items()})
    out = []
    for step in steps:
        state = states.get(step["id"])
        view = {
            k: v for k, v in step.items() if k not in ("slots", "have_ready", "script_facts", "must", "outcomes")
        }
        view["status"] = status[step["id"]]
        view["outcome"] = state.outcome if state else None
        view["note"] = state.note if state else None
        view["checks"] = state.checks if state else []
        view["updated_at"] = state.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if state else None
        labels = outcomes_of(step)
        view["outcomes"] = [{"id": k, "label": label} for k, (label, _) in labels.items()]
        if len(labels) == 1 and step.get("done_label"):
            view["outcomes"][0]["label"] = step["done_label"]
        if "contact" in step:
            view["contact"] = contact_view(step["contact"], now)
        if scripts.needs_text(step) and state and state.script:
            view["script"] = scripts.render(state.script, step, profile, facts)
            view["script"]["source"] = state.script["source"]
        out.append(view)
    return {
        "version": plan.version,
        "services": plan.graph["services"],
        "dropped": plan.graph["dropped"],
        "steps": out,
        "status": status_text(steps, status),
    }


def current_plan(db: Session, chat: Chat) -> dict | None:
    plan = latest_plan(db, chat.id)
    if plan is None:
        return None
    facts = {k: r.value for k, r in fact_rows(db, chat.id).items()}
    return render_plan(plan, step_states(db, chat.id), profile_of(db, chat.user_id), facts, vienna_now())


def question_message(chat_id: str, key: str, facts: dict, corpus: Corpus) -> Message:
    question = corpus.question(key)
    text = question.text["self" if facts.get("subject") == "self" else "other"]
    options = (
        [{"value": c.value, "label": c.label or value_label(key, c.value)} for c in question.chips]
        if question.chips
        else chips(key)
    )
    return Message(
        chat_id=chat_id,
        role="assistant",
        kind="question",
        text=text.replace("{subject.ihr}", subject_words(facts)[0]),
        payload={"fact_key": key, "chips": options, "why": question.why_we_ask, "multi": question.multi},
        created_at=utcnow(),
    )


async def intro(llm: Llm, graph: dict, facts: dict, language: str) -> str | None:
    """1-2 sentences without data; None if the LLM fails or the text breaks the rules."""
    request = {
        "person": facts.get("subject"),
        "topics": [{"title": s["title"], "may_apply": s["eligibility"]} for s in graph["services"]],
    }
    try:
        text = (await llm.intro(request, language)).strip()
    except Exception:
        logger.exception("Plan intro failed")
        return None
    if errors := scripts.check_text(text, "intro", []):
        logger.warning("Plan intro rejected: %s", "; ".join(errors))
        return None
    return text


async def respond(
    db: Session, chat: Chat, llm: Llm, *, text: str | None = None, answer: tuple | None = None
) -> AsyncIterator[ServerSentEvent]:
    """`answer`: (fact key, value, source, letter quotes or None) of a chip or confirmed letter items."""
    # Yields `facts`, then `plan` for a plan, then `done` with the saved assistant message.
    corpus = get_corpus()
    rows = fact_rows(db, chat.id)
    medical = False
    if answer:
        key, value, source, quote = answer
        set_fact(db, chat.id, rows, key, value, source)
        rows[key].quote = quote
    else:
        question = pending_question(db, chat.id)
        try:
            extracted = await llm.extract(text, question.text if question else None)
        except Exception:
            # The chips still lead to a plan without the LLM (spec 17).
            logger.exception("Fact extraction failed")
            extracted = {}
        medical = extracted.get("medical_question") is True
        for key, value in merge({k: (r.value, r.source) for k, r in rows.items()}, extracted).items():
            set_fact(db, chat.id, rows, key, value, "user_text")
    profile = profile_of(db, chat.user_id)
    facts = {k: r.value for k, r in rows.items()}
    # Someone asking for themselves has already said where they live in their profile.
    if facts.get("subject") == "self" and "district" not in facts and VIENNA_POSTAL_CODE.match(profile.postal_code):
        set_fact(db, chat.id, rows, "district", profile.postal_code, "profile")
        facts["district"] = profile.postal_code
    db.commit()
    yield ServerSentEvent(event="facts", data=fact_list(rows))

    letter = rows.get("documented_recommendations")
    quotes = (letter.quote or {}) if letter else {}
    result = evaluate(facts, corpus, asked=questions_asked(db, chat.id), medical=medical, quotes=quotes)
    if result.kind == "question":
        reply = question_message(chat.id, result.question, facts, corpus)
    elif result.kind != "plan":
        card = corpus.cards[result.kind]
        reply = Message(
            chat_id=chat.id,
            role="assistant",
            kind="card",
            text=card.text,
            payload={"card": result.kind, "title": card.title, "contacts": card.contacts},
            created_at=utcnow(),
        )
    else:
        graph = result.plan
        latest = latest_plan(db, chat.id)
        plan = Plan(chat_id=chat.id, version=latest.version + 1 if latest else 1, graph=graph, created_at=utcnow())
        states = step_states(db, chat.id)
        detail = profile.answer_length
        todo = []
        # Saved with the corpus scripts first, so a lost connection still leaves a complete plan.
        for step in filter(scripts.needs_text, graph["steps"]):
            key = scripts.inputs_hash(step, detail)
            state = states.get(step["id"])
            if state and state.script and state.script["hash"] == key and state.script["source"] == "llm":
                continue
            if state is None:
                state = states[step["id"]] = StepState(chat_id=chat.id, step_id=step["id"], checks=[])
                db.add(state)
            state.script = {**scripts.fallback(step, corpus), "source": "fallback", "hash": key}
            state.updated_at = utcnow()
            todo.append(step)
        titles = ", ".join(s["title"] for s in graph["services"])
        reply = Message(
            chat_id=chat.id,
            role="assistant",
            kind="plan",
            text=f"Hier ist Ihr Plan mit den nächsten Schritten: {titles}.",
            payload={"version": plan.version},
            created_at=utcnow(),
        )
        db.add_all([plan, reply])
        db.commit()

        services = {s["id"]: s["title"] for s in graph["services"]}
        intro_task = asyncio.create_task(intro(llm, graph, facts, profile.answer_language))
        try:
            written = await scripts.generate(llm, todo, services, detail, corpus) if todo else {}
            reply.text = await intro_task or reply.text
        finally:
            intro_task.cancel()
        for step in todo:
            states[step["id"]].script = {**written[step["id"]], "hash": scripts.inputs_hash(step, detail)}
        db.commit()
        yield ServerSentEvent(event="plan", data=render_plan(plan, states, profile, facts, vienna_now()))

    if reply not in db:
        db.add(reply)
        db.commit()
    yield ServerSentEvent(event="done", data=message_response(reply, corpus))
