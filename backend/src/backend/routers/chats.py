import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from backend import pipeline
from backend.database import SessionLocal
from backend.dependencies import CurrentUser, DbSession
from backend.facts import FACTS, value_label
from backend.llm import Llm, LlmClient
from backend.models import Chat, Message, StepState, utcnow
from backend.schemas import (
    AnswerRequest,
    ChatRequest,
    ChatResponse,
    MessageRequest,
    MessageResponse,
    StepUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


def get_owned_chat(chat_id: str, user: CurrentUser, db: DbSession) -> Chat:
    chat = db.get(Chat, chat_id)
    # Another user's chat looks the same as a missing one, so ids can't be probed.
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


OwnedChat = Annotated[Chat, Depends(get_owned_chat)]


def chat_response(db: Session, chat: Chat) -> ChatResponse:
    return ChatResponse.model_validate(chat).model_copy(update={"status": pipeline.chat_status(db, chat.id)})


@router.get("")
def list_chats(user: CurrentUser, db: DbSession) -> list[ChatResponse]:
    # shortcut: the status costs a few queries per chat; batch them if chat lists get long.
    chats = db.scalars(
        select(Chat)
        .where(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc(), literal_column("chats.rowid").desc())
    )
    return [chat_response(db, chat) for chat in chats]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_chat(body: ChatRequest, user: CurrentUser, db: DbSession) -> ChatResponse:
    now = utcnow()
    chat = Chat(user_id=user.id, title=body.title, created_at=now, updated_at=now)
    db.add(chat)
    db.commit()
    return chat_response(db, chat)


@router.patch("/{chat_id}")
def rename_chat(body: ChatRequest, chat: OwnedChat, db: DbSession) -> ChatResponse:
    chat.title = body.title
    chat.updated_at = utcnow()
    db.commit()
    return chat_response(db, chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat: OwnedChat, db: DbSession) -> None:
    db.delete(chat)
    db.commit()


@router.get("/{chat_id}/messages")
def list_messages(chat: OwnedChat, db: DbSession) -> list[MessageResponse]:
    # Ordered by rowid: a message and its reply share a timestamp.
    messages = db.scalars(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(literal_column("messages.rowid"))
    )
    return [pipeline.message_response(message) for message in messages]


@router.get("/{chat_id}/state")
def get_state(chat: OwnedChat, db: DbSession) -> dict:
    """The fact chips and the latest plan with current step states."""
    return {"facts": pipeline.fact_list(pipeline.fact_rows(db, chat.id)), "plan": pipeline.current_plan(db, chat)}


async def generate_title(llm: Llm, text: str) -> str | None:
    # A failed title must not fail the reply: the chat then keeps its title.
    try:
        title = (await llm.title(text)).strip().strip('"„“').strip()
    except Exception:
        logger.exception("Title generation failed")
        return None
    return title[:200] or None


async def turn(chat_id: str, llm: Llm, message: Message, **kwargs) -> AsyncIterator[ServerSentEvent]:
    """Saves the user's message, then streams the pipeline's events (pipeline.respond)."""
    # Own session: after a Stop this generator can be closed after the request's session.
    # shortcut: sync SQLite calls block the event loop briefly, move them to a thread under load.
    with SessionLocal() as db:
        chat = db.get_one(Chat, chat_id)
        message.chat_id, message.role, message.created_at = chat.id, "user", utcnow()
        db.add(message)
        chat.updated_at = message.created_at
        db.commit()
        yield ServerSentEvent(event="message", data=pipeline.message_response(message))

        first = db.scalar(select(func.count()).select_from(Message).where(Message.chat_id == chat.id)) == 1
        title = asyncio.create_task(generate_title(llm, message.text)) if first else None
        try:
            async for event in pipeline.respond(db, chat, llm, **kwargs):
                if event.event == "done" and title and (new_title := await title):
                    chat.title = new_title
                    db.commit()
                    yield ServerSentEvent(event="title", data=chat_response(db, chat))
                yield event
        except Exception:
            logger.exception("Reply failed")
            # Nothing was answered: drop the question too, so a retry does not save it twice.
            db.rollback()
            db.delete(message)
            db.commit()
            yield ServerSentEvent(event="error", data={"status": 502, "detail": "Reply failed"})
        finally:
            if title:
                title.cancel()


@router.post("/{chat_id}/messages", response_class=EventSourceResponse)
async def send_message(body: MessageRequest, owned: OwnedChat, llm: LlmClient) -> AsyncIterator[ServerSentEvent]:
    async for event in turn(owned.id, llm, Message(kind="text", text=body.text), text=body.text):
        yield event


@router.post("/{chat_id}/answers", response_class=EventSourceResponse)
async def answer(
    body: AnswerRequest, owned: OwnedChat, db: DbSession, llm: LlmClient
) -> AsyncIterator[ServerSentEvent]:
    """A chip answer, or an edited fact chip: sets the fact directly, without the LLM."""
    question = pipeline.pending_question(db, owned.id)
    label = value_label(body.fact_key, body.value)
    if question and question.payload["fact_key"] == body.fact_key:
        label = next((c["label"] for c in question.payload["chips"] if c["value"] == body.value), label)
    else:
        label = f"{FACTS[body.fact_key].label}: {label}"
    message = Message(kind="answer", text=label, payload={"fact_key": body.fact_key, "value": body.value})
    async for event in turn(owned.id, llm, message, answer=(body.fact_key, body.value)):
        yield event


@router.patch("/{chat_id}/steps/{step_id}")
def update_step(step_id: str, body: StepUpdate, chat: OwnedChat, db: DbSession) -> dict:
    """Check off a step, record an outcome or a note, tick checklist items. Returns the whole plan."""
    plan = pipeline.latest_plan(db, chat.id)
    step = next((s for s in plan.graph["steps"] if s["id"] == step_id), None) if plan else None
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Step not found")
    state = db.get(StepState, (chat.id, step_id))
    if state is None:
        state = StepState(chat_id=chat.id, step_id=step_id, checks=[])
        db.add(state)
    if body.outcome is not None:
        outcome = pipeline.OUTCOMES[step["type"]].get(body.outcome)
        if outcome is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown outcome")
        state.outcome = body.outcome
        state.status = "done" if outcome[1] == "done" else None
    if body.status is not None:
        state.status = None if body.status == "open" else body.status
        if body.status == "open":
            state.outcome = None
    if body.note is not None:
        state.note = body.note.strip() or None
    if body.checks is not None:
        allowed = {d["id"] for d in step.get("documents", [])} | {i["id"] for i in step.get("must", [])}
        if not set(body.checks) <= allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown checklist item")
        state.checks = list(dict.fromkeys(body.checks))
    state.updated_at = utcnow()
    db.commit()
    return pipeline.current_plan(db, chat)
