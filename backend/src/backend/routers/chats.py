from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import literal_column, select

from backend.dependencies import CurrentUser, DbSession
from backend.models import Chat, Message, utcnow
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    MessageRequest,
    MessageResponse,
    SendMessageResponse,
)

ASSISTANT_REPLY = "TODO"

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


@router.post("/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(body: MessageRequest, chat: OwnedChat, db: DbSession) -> SendMessageResponse:
    now = utcnow()
    message = Message(chat_id=chat.id, role="user", text=body.text, created_at=now)
    db.add(message)
    db.flush()
    db.add(Message(chat_id=chat.id, role="assistant", text=ASSISTANT_REPLY, created_at=now))
    chat.updated_at = now
    db.commit()
    return SendMessageResponse(message=MessageResponse.model_validate(message))
