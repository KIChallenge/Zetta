from fastapi import APIRouter, HTTPException, Request, Response, status

from backend import forms
from backend.dependencies import COOKIE, CurrentUser, DbSession, set_session_cookie
from backend.guards import PASSWORD_FAILURES
from backend.models import Person, Preference, Profile, User, utcnow
from backend.facts import FACTS
from backend.schemas import (
    DeleteAccountRequest,
    FormDetails,
    PasswordChangeRequest,
    PersonData,
    ProfileData,
    UserResponse,
)
from backend.security import hash_password, verify_password

router = APIRouter(tags=["users"])


def check_password(user: User, password: str) -> None:
    PASSWORD_FAILURES.check(user.id)
    # 403, not 401: the frontend logs out on 401, and the session itself is fine.
    if not verify_password(password, user.password_hash):
        PASSWORD_FAILURES.add(user.id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Wrong password")


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/me/profile")
def get_profile(user: CurrentUser) -> ProfileData:
    profile = ProfileData.model_validate(user.profile) if user.profile else ProfileData()
    return profile.model_copy(update={"phone_calls": user.preference is None or user.preference.phone_calls})


@router.put("/me/profile")
def put_profile(body: ProfileData, user: CurrentUser, db: DbSession) -> ProfileData:
    db.merge(Profile(user_id=user.id, **body.model_dump(exclude={"phone_calls"})))
    db.merge(Preference(user_id=user.id, phone_calls=body.phone_calls))
    db.commit()
    return body


# Your own name and contact details are in the profile; the people rows add what forms ask for beyond that.
OWN_ENTRIES = [e for e, (_, _, fields) in forms.ENTRIES.items() if set(fields) <= set(FormDetails.model_fields)]


def person_view(relation: str, details: dict | None) -> dict:
    """One person for the settings page: every entry with its stored value, editable, and as shown."""
    person = PersonData(**(details or {}))
    shown = forms.details(person)
    return {
        "relation": relation,
        "label": "Sie selbst" if relation == "self" else FACTS["subject"].values[relation],
        "kept": details is not None,
        "entries": [
            {**forms.entry_item(e, forms.ENTRIES[e][1], person), "shown": forms.text(f"x.{e}", shown[e]) if e in shown else ""}
            for e in (OWN_ENTRIES if relation == "self" else forms.ENTRIES)
        ],
    }


def known_relation(relation: str) -> str:
    if relation not in FACTS["subject"].values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    return relation


@router.get("/me/people")
def get_people(user: CurrentUser) -> list[dict]:
    """Every person details can be kept for (the user and each relation), kept or not, for the settings page."""
    kept = {p.relation: p.details for p in user.people}
    return [person_view(relation, kept.get(relation)) for relation in FACTS["subject"].values]


@router.put("/me/people/{relation}")
def put_person(relation: str, body: PersonData, user: CurrentUser, db: DbSession) -> dict:
    """Replaces what is kept for a person, entered in the settings ahead of any form. Nothing left: the row goes."""
    known_relation(relation)
    details = body.model_dump(exclude_defaults=True, include=set(FormDetails.model_fields) if relation == "self" else None)
    row = db.get(Person, (user.id, relation))
    if not details:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(Person(user_id=user.id, relation=relation, details=details, updated_at=utcnow()))
    else:
        row.details, row.updated_at = details, utcnow()
    db.commit()
    return person_view(relation, details or None)


@router.delete("/me/people/{relation}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(relation: str, user: CurrentUser, db: DbSession) -> None:
    row = db.get(Person, (user.id, relation))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    db.delete(row)
    db.commit()


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest, user: CurrentUser, request: Request, response: Response, db: DbSession
) -> None:
    """Ends all other sessions; this browser gets a new cookie and stays signed in."""
    check_password(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    user.revoke_tokens()
    db.commit()
    set_session_cookie(request, response, user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: DeleteAccountRequest, user: CurrentUser, response: Response, db: DbSession) -> None:
    check_password(user, body.password)
    db.delete(user)  # with its profile, chats and their messages (ORM cascade)
    db.commit()
    response.delete_cookie(COOKIE)
