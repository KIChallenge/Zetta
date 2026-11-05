import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from backend import facts

Email = Annotated[EmailStr, AfterValidator(str.lower)]
Password = Annotated[str, Field(min_length=8, max_length=128)]
ChatTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Timestamps are always UTC, but SQLite returns them without a timezone.
Timestamp = Annotated[datetime, PlainSerializer(lambda value: value.strftime("%Y-%m-%dT%H:%M:%SZ"))]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str


class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse


class ChatRequest(BaseModel):
    title: ChatTitle


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: Timestamp
    updated_at: Timestamp
    status: str | None = None  # computed: "3 offene Schritte", "Frage offen", ...


class MessageRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    kind: Literal["text", "answer", "document", "question", "confirm", "plan", "card"]
    text: str
    payload: dict | None
    created_at: Timestamp


class AnswerRequest(BaseModel):
    """A chip answer or a fact edit; the value is checked against the fact schema."""

    fact_key: str
    value: str | list[str]

    @model_validator(mode="after")
    def known(self):
        # A single chip for a list fact (e.g. one goal) is a list of one.
        fact = facts.FACTS.get(self.fact_key)
        if fact and fact.multi and isinstance(self.value, str) and not facts.is_sentinel(self.value):
            self.value = [self.value]
        if not facts.valid(self.fact_key, self.value):
            raise ValueError("unknown fact or value")
        return self


class StepUpdate(BaseModel):
    status: Literal["done", "skipped", "open"] | None = None
    outcome: str | None = Field(None, max_length=40)
    note: str | None = Field(None, max_length=2000)
    checks: list[Annotated[str, Field(max_length=100)]] | None = Field(None, max_length=50)


# Weights of the Austrian check digit (the 4th digit, so its own weight is 0).
SVNR_WEIGHTS = (3, 7, 9, 0, 5, 8, 4, 2, 1, 6)


def check_svnr(value: str) -> str:
    digits = value.replace(" ", "")
    # A sum of 10 (mod 11) matches no digit, so such numbers are invalid.
    if digits and not (
        re.fullmatch("[0-9]{10}", digits)
        and sum(int(d) * w for d, w in zip(digits, SVNR_WEIGHTS)) % 11 == int(digits[3])
    ):
        raise ValueError("must be a valid Austrian social security number")
    return digits


class ProfileData(BaseModel):
    """The user's own details, sent to the LLM. Every field is optional ("" when unset)."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    full_name: str = Field("", max_length=100)
    street: str = Field("", max_length=100)
    postal_code: str = Field("", pattern="^([0-9]{4})?$")
    city: str = Field("", max_length=60)
    svnr: Annotated[str, AfterValidator(check_svnr)] = ""
    phone: str = Field("", max_length=30, pattern="^[0-9 +()-]*$")
    contact_email: Email | Literal[""] = ""
    answer_language: Literal["de", "en", "fr", "cs", "sk", "sl", "tr", "bks", "ro", "pl", "hu", "uk", "ar"] = "de"
    answer_length: Literal["short", "detailed"] = "short"


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: Password


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=128)
