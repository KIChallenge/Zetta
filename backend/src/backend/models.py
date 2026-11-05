from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))

    # Deleted by the ORM with the user: SQLite does not enforce foreign keys by default.
    profile: Mapped["Profile | None"] = relationship(cascade="all, delete-orphan")
    chats: Mapped[list["Chat"]] = relationship(cascade="all, delete-orphan")


class Profile(Base):
    """Details the user entered about themselves. Own table, so existing databases need no migration."""

    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    street: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(4))
    city: Mapped[str] = mapped_column(String(60))
    svnr: Mapped[str] = mapped_column(String(10))
    phone: Mapped[str] = mapped_column(String(30))
    contact_email: Mapped[str] = mapped_column(String(320))
    answer_language: Mapped[str] = mapped_column(String(3))
    answer_length: Mapped[str] = mapped_column(String(10))


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    # Deleted by the ORM: SQLite does not enforce foreign keys by default.
    messages: Mapped[list["Message"]] = relationship(cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
