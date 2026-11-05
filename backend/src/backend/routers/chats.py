import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import literal_column, select

from backend.database import SessionLocal
from backend.dependencies import CurrentUser, DbSession
from backend.llm import Llm, LlmClient, build_messages
from backend.models import Chat, Message, Profile, utcnow
from backend.schemas import ChatRequest, ChatResponse, MessageRequest, MessageResponse, ProfileData

HISTORY_LIMIT = 40

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


def get_owned_chat(chat_id: str, user: CurrentUser, db: DbSession) -> Chat:
    chat = db.get(Chat, chat_id)
    # Another user's chat looks the same as a missing one, so ids can't be probed.
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


OwnedChat = Annotated[Chat, Depends(get_owned_chat)]


@router.get("")
def list_chats(user: CurrentUser, db: DbSession) -> list[ChatResponse]:
    chats = db.scalars(
        select(Chat)
        .where(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc(), literal_column("chats.rowid").desc())
    )
    return [ChatResponse.model_validate(chat) for chat in chats]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_chat(body: ChatRequest, user: CurrentUser, db: DbSession) -> ChatResponse:
    now = utcnow()
    chat = Chat(user_id=user.id, title=body.title, created_at=now, updated_at=now)
    db.add(chat)
    db.commit()
    return ChatResponse.model_validate(chat)


@router.patch("/{chat_id}")
def rename_chat(body: ChatRequest, chat: OwnedChat, db: DbSession) -> ChatResponse:
    chat.title = body.title
    chat.updated_at = utcnow()
    db.commit()
    return ChatResponse.model_validate(chat)


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
    return [MessageResponse.model_validate(message) for message in messages]


async def generate_title(llm: Llm, text: str) -> str | None:
    # A failed title must not fail the reply: the chat then keeps its title.
    try:
        title = (await llm.title(text)).strip().strip('"„“').strip()
    except Exception:
        logger.exception("Title generation failed")
        return None
    return title[:200] or None


@router.post("/{chat_id}/messages", response_class=EventSourceResponse)
async def send_message(
    body: MessageRequest, owned: OwnedChat, llm: LlmClient
) -> AsyncIterator[ServerSentEvent]:
    # Own session: after a Stop this generator can be closed after the request's session.
    # shortcut: sync SQLite calls block the event loop briefly, move them to a thread under load.
    with SessionLocal() as db:
        chat = db.get_one(Chat, owned.id)
        message = Message(chat_id=chat.id, role="user", text=body.text, created_at=utcnow())
        db.add(message)
        chat.updated_at = message.created_at
        db.commit()
        yield ServerSentEvent(event="message", data=MessageResponse.model_validate(message))

        history = db.scalars(
            select(Message)
            .where(Message.chat_id == chat.id)
            .order_by(literal_column("messages.rowid").desc())
            .limit(HISTORY_LIMIT)
        ).all()[::-1]
        first = len(history) == 1
        title = asyncio.create_task(generate_title(llm, body.text)) if first else None
        text = ""
        try:
            # Read on every message, so the LLM always has the current profile.
            row = db.get(Profile, chat.user_id)
            profile = ProfileData.model_validate(row) if row else ProfileData()
            context = build_messages(profile, [{"role": m.role, "content": m.text} for m in history])
            async with aclosing(llm.reply(context)) as deltas:
                async for delta in deltas:
                    text += delta
                    yield ServerSentEvent(event="delta", data={"text": delta})
            if not text:
                raise RuntimeError("Empty reply")
            if title and (new_title := await title):
                chat.title = new_title
                db.commit()
                yield ServerSentEvent(event="title", data=ChatResponse.model_validate(chat))
        except Exception:
            logger.exception("LLM reply failed")
            # Nothing was answered: drop the question too, so a retry does not save it twice.
            text = ""
            db.delete(message)
            db.commit()
            yield ServerSentEvent(event="error", data={"status": 502, "detail": "LLM reply failed"})
            return
        finally:
            if title:
                title.cancel()
            # Also runs when the client disconnects (Stop), so a partial reply is kept.
            if text:
                reply = Message(chat_id=chat.id, role="assistant", text=text, created_at=utcnow())
                db.add(reply)
                db.commit()
        yield ServerSentEvent(event="done", data=MessageResponse.model_validate(reply))
