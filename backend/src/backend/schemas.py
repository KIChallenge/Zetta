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
)

Email = Annotated[EmailStr, AfterValidator(str.lower)]
ChatTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Timestamps are always UTC, but SQLite returns them without a timezone.
Timestamp = Annotated[datetime, PlainSerializer(lambda value: value.strftime("%Y-%m-%dT%H:%M:%SZ"))]


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
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


class MessageRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: Timestamp


class SendMessageResponse(BaseModel):
    status: Literal["delivered"] = "delivered"
    message: MessageResponse
