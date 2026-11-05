from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
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
    token_version: Mapped["TokenVersion | None"] = relationship(cascade="all, delete-orphan")

    @property
    def version(self) -> int:
        return self.token_version.version if self.token_version else 0

    def revoke_tokens(self) -> None:
        """Ends every token issued so far, on all devices."""
        if self.token_version is None:
            self.token_version = TokenVersion(version=0)
        self.token_version.version += 1


class TokenVersion(Base):
    """Own table, like profiles, so existing databases need no migration. No row: version 0."""

    __tablename__ = "token_versions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


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
    facts: Mapped[list["ChatFact"]] = relationship(cascade="all, delete-orphan")
    plans: Mapped[list["Plan"]] = relationship(cascade="all, delete-orphan")
    step_states: Mapped[list["StepState"]] = relationship(cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    # text | answer (chip) | question | plan | card (boundary, out of scope, general)
    kind: Mapped[str] = mapped_column(String(20), default="text")
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ChatFact(Base):
    __tablename__ = "chat_facts"

    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str | list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(20))  # profile | user_text | chip | document
    # documented_recommendations: recommendation -> the confirmed quote from the letter
    quote: Mapped[dict | None] = mapped_column(JSON, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict] = mapped_column(JSON)  # services, dropped, steps (engine.build_plan)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class StepState(Base):
    """Per chat, not per plan: step ids are stable, so a re-plan keeps what the user did."""

    __tablename__ = "step_states"

    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), primary_key=True)
    step_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(20), default=None)  # done | skipped
    outcome: Mapped[str | None] = mapped_column(String(40), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    checks: Mapped[list] = mapped_column(JSON, default=list)  # ticked checklist items
    script: Mapped[dict | None] = mapped_column(JSON, default=None)  # with placeholders, filled on render
    updated_at: Mapped[datetime] = mapped_column(DateTime)
