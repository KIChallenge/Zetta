import re
from datetime import date, datetime
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
# The most used passwords of 10 or more characters: the first ones an attacker tries.
COMMON_PASSWORDS = {
    "1234567890", "0123456789", "0987654321", "1111111111", "123456789a", "1q2w3e4r5t", "qwertyuiop", "qwertzuiop",
    "password12", "password123", "password1234", "passwort123", "passwort1234", "hallo12345", "iloveyou12",
    "abcdefghij", "abcd123456", "asdfghjkl1", "a123456789", "1234567890a",
}


def not_common(value: str) -> str:
    if value.lower() in COMMON_PASSWORDS or len(set(value)) < 4:
        raise ValueError("is too common")
    return value


Password = Annotated[str, Field(min_length=10, max_length=128), AfterValidator(not_common)]
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


class Contact(BaseModel):
    """A person's name and contact details. Never sent to the LLM: they only fill placeholders after it. "" when unset."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    full_name: str = Field("", max_length=100)
    street: str = Field("", max_length=100)
    postal_code: str = Field("", pattern="^([0-9]{4})?$")
    city: str = Field("", max_length=60)
    svnr: Annotated[str, AfterValidator(check_svnr)] = ""
    phone: str = Field("", max_length=30, pattern="^[0-9 +()-]*$")
    contact_email: Email | Literal[""] = ""


class ProfileData(Contact):
    """The user's own details and settings."""

    answer_language: Literal["de", "en", "fr", "cs", "sk", "sl", "tr", "bks", "ro", "pl", "hu", "uk", "ar"] = "de"
    answer_length: Literal["short", "detailed"] = "short"


# Choices of the form details: value -> how it is written on a form.
SEX = {"female": "weiblich", "male": "männlich", "diverse": "divers"}
MARITAL_STATUS = {
    "single": "ledig", "married": "verheiratet", "widowed": "verwitwet", "divorced": "geschieden",
    "partnership": "eingetragene Partnerschaft", "former_partnership": "ehemalige eingetragene Partnerschaft",
}  # fmt: skip
CITIZENSHIP = {"austria": "Österreich", "other": "Andere"}
HEALTH_INSURER = {"oegk": "Österreichische Gesundheitskasse", "bvaeb": "BVAEB", "svs": "SVS", "kfa": "KFA Wien"}
CHOICES = {"sex": SEX, "marital_status": MARITAL_STATUS, "citizenship": CITIZENSHIP, "health_insurer": HEALTH_INSURER}


def past_date(value: str) -> str:
    if value and not (date(1900, 1, 1) <= date.fromisoformat(value) <= date.today()):
        raise ValueError("must be a date in the past")
    return value


def choice(values: dict[str, str]):
    def known(value: str) -> str:
        if value and value not in values:
            raise ValueError("unknown value")
        return value

    return Annotated[str, AfterValidator(known)]


class FormDetails(BaseModel):
    """Further details some application forms ask for. Never medical: no diagnoses, care needs or aids."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field("", max_length=30)
    birth_date: Annotated[str, Field(pattern=r"^(\d{4}-\d{2}-\d{2})?$"), AfterValidator(past_date)] = ""
    sex: choice(SEX) = ""
    marital_status: choice(MARITAL_STATUS) = ""
    citizenship: choice(CITIZENSHIP) = ""
    health_insurer: choice(HEALTH_INSURER) = ""


class PersonData(Contact, FormDetails):
    """Everything known about one person for the forms: the user, or a relative the user applies for."""


class FormRequest(BaseModel):
    """Details typed into a form card. Only the ones entered are sent; "remember" keeps them for later forms."""

    user: PersonData = PersonData()
    subject: PersonData = PersonData()
    remember: bool = True


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: Password


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=128)
