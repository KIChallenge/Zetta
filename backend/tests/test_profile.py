import pytest
from sqlalchemy import func, select

from backend.database import SessionLocal
from backend.models import Chat, Message, Person, Profile, User, utcnow
from test_chats import assert_error, create_chat, register, send

PASSWORD = "secret-password-123"
EMPTY = {
    "full_name": "",
    "street": "",
    "postal_code": "",
    "city": "",
    "svnr": "",
    "phone": "",
    "contact_email": "",
    "answer_language": "de",
    "answer_length": "short",
    "phone_calls": True,
}
ANNA = {
    **EMPTY,
    "full_name": "Anna Huber",
    "street": "Favoritenstraße 12/3",
    "postal_code": "1100",
    "city": "Wien",
    "svnr": "1237010180",
    "phone": "+43 (660) 123-4567",
    "contact_email": "anna.huber@example.at",
}


@pytest.fixture
def anna(client):
    return register(client, "anna")


@pytest.fixture
def bob(client):
    return register(client, "bob")


def put(client, headers, profile):
    return client.put("/me/profile", json=profile, headers=headers)


def test_new_user_has_an_empty_profile(client, anna):
    response = client.get("/me/profile", headers=anna)

    assert response.status_code == 200
    assert response.json() == EMPTY


def test_put_profile_saves_and_returns_it(client, anna):
    response = put(client, anna, {**ANNA, "answer_language": "en", "answer_length": "detailed"})

    assert response.status_code == 200
    saved = {**ANNA, "answer_language": "en", "answer_length": "detailed"}
    assert response.json() == saved
    assert client.get("/me/profile", headers=anna).json() == saved


def test_put_profile_replaces_the_whole_profile(client, anna):
    put(client, anna, ANNA)

    put(client, anna, {**EMPTY, "city": "Wien"})

    assert client.get("/me/profile", headers=anna).json() == {**EMPTY, "city": "Wien"}


def test_put_profile_normalizes_input(client, anna):
    response = put(
        client, anna, {**ANNA, "svnr": " 1237 010180 ", "full_name": "  Anna Huber ", "contact_email": "Anna@Example.at"}
    )

    body = response.json()
    assert body["svnr"] == "1237010180"
    assert body["full_name"] == "Anna Huber"
    assert body["contact_email"] == "anna@example.at"


def test_profiles_are_per_user(client, anna, bob):
    put(client, anna, ANNA)

    assert client.get("/me/profile", headers=bob).json() == EMPTY


def test_phone_calls_can_be_turned_off_and_on_again(client, anna):
    put(client, anna, {**ANNA, "phone_calls": False})

    assert client.get("/me/profile", headers=anna).json() == {**ANNA, "phone_calls": False}
    put(client, anna, ANNA)
    assert client.get("/me/profile", headers=anna).json() == ANNA


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("svnr", "1234010180"),  # wrong check digit
        ("svnr", "1000000003"),  # check sum 10: no digit is valid
        ("svnr", "123701018"),
        ("svnr", "12370101800"),
        ("svnr", "1237-010180"),
        ("postal_code", "110"),
        ("postal_code", "11000"),
        ("postal_code", "abcd"),
        ("contact_email", "not-an-email"),
        ("phone", "0660 123 abc"),
        ("phone", "1" * 31),
        ("full_name", "x" * 101),
        ("street", "x" * 101),
        ("city", "x" * 61),
        ("answer_language", "xx"),
        ("answer_length", "long"),
    ],
)
def test_put_profile_rejects_invalid_values(client, anna, field, value):
    put(client, anna, ANNA)

    assert_error(put(client, anna, {**ANNA, field: value}), 422)
    assert client.get("/me/profile", headers=anna).json() == ANNA


def test_own_postal_code_answers_the_district_question(client, anna, llm):
    put(client, anna, ANNA)
    llm.facts = {"subject": "self", "goal": ["apply_care_allowance"]}
    chat = create_chat(client, anna)

    events = dict(send(client, anna, chat["id"], "Ich möchte Pflegegeld beantragen"))

    district = next(f for f in events["facts"] if f["key"] == "district")
    assert (district["value"], district["source"]) == ("1100", "profile")
    assert events["done"]["payload"]["fact_key"] == "pension_payer"


def test_without_phone_calls_the_plan_writes_an_email_instead_of_a_call(client, anna, llm):
    put(client, anna, {**ANNA, "phone_calls": False})
    llm.facts = {"subject": "self", "goal": ["apply_care_allowance"], "pension_payer": "pv"}
    chat = create_chat(client, anna)

    events = dict(send(client, anna, chat["id"], "Ich möchte Pflegegeld beantragen"))

    step = next(s for s in events["plan"]["steps"] if s["id"] == "care_allowance.call")
    assert (step["type"], step["contact"]["value"]) == ("email", "pva-lsw@pv.at")
    assert {"subject", "body"} <= set(step["script"])


def test_one_call_can_be_switched_to_an_email_and_back(client, anna, llm):
    put(client, anna, ANNA)
    llm.facts = {"subject": "self", "goal": ["apply_care_allowance"], "pension_payer": "pv"}
    chat = create_chat(client, anna)
    events = dict(send(client, anna, chat["id"], "Ich möchte Pflegegeld beantragen"))
    call = next(s for s in events["plan"]["steps"] if s["id"] == "care_allowance.call")
    assert (call["type"], call["switchable"], call["by_email"]) == ("call", True, False)
    url = f"/chats/{chat['id']}/steps/care_allowance.call"

    plan = client.patch(url, json={"by_email": True}, headers=anna).json()

    step = next(s for s in plan["steps"] if s["id"] == "care_allowance.call")
    assert (step["type"], step["by_email"], step["contact"]["value"]) == ("email", True, "pva-lsw@pv.at")
    assert "anna.huber@example.at" in step["script"]["body"]  # the corpus email, filled in
    assert step["outcomes"][0]["id"] == "sent"
    plan = client.patch(url, json={"by_email": False}, headers=anna).json()
    step = next(s for s in plan["steps"] if s["id"] == "care_allowance.call")
    assert (step["type"], step["by_email"], "opening" in step["script"]) == ("call", False, True)


def test_a_step_without_an_email_version_cannot_be_switched(client, anna, llm):
    put(client, anna, ANNA)
    llm.facts = {"subject": "self", "goal": ["apply_care_allowance"], "pension_payer": "pv"}
    chat = create_chat(client, anna)
    send(client, anna, chat["id"], "Ich möchte Pflegegeld beantragen")

    assert_error(client.patch(f"/chats/{chat['id']}/steps/care_allowance.info", json={"by_email": True}, headers=anna), 422)


def test_a_relatives_district_is_not_taken_from_the_profile(client, anna, llm):
    put(client, anna, ANNA)
    llm.facts = {"subject": "mother", "goal": ["apply_care_allowance"]}
    chat = create_chat(client, anna)

    events = dict(send(client, anna, chat["id"]))

    assert "district" not in [f["key"] for f in events["facts"]]
    assert events["done"]["payload"]["fact_key"] == "district"


def test_the_plan_intro_follows_the_answer_language(client, anna, llm):
    put(client, anna, {**ANNA, "answer_language": "en"})
    llm.facts = {"subject": "self", "goal": ["apply_care_allowance"], "pension_payer": "pv"}
    chat = create_chat(client, anna)

    send(client, anna, chat["id"])

    assert next(value for method, value in llm.calls if method == "intro")["language"] == "en"


def test_change_password(client, anna):
    response = client.post(
        "/me/password", json={"current_password": PASSWORD, "new_password": "new-password-456"}, headers=anna
    )

    assert response.status_code == 204
    login = {"email": "anna@example.at"}
    assert client.post("/auth/login", json={**login, "password": "new-password-456"}).status_code == 200
    assert client.post("/auth/login", json={**login, "password": PASSWORD}).status_code == 401


def test_change_password_with_wrong_current_password(client, anna):
    response = client.post(
        "/me/password", json={"current_password": "wrong", "new_password": "new-password-456"}, headers=anna
    )

    assert_error(response, 403, "Wrong password")
    assert client.post("/auth/login", json={"email": "anna@example.at", "password": PASSWORD}).status_code == 200


def test_change_password_rejects_short_new_password(client, anna):
    response = client.post("/me/password", json={"current_password": PASSWORD, "new_password": "short"}, headers=anna)

    assert_error(response, 422)


def counts():
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(t)) for t in (User, Profile, Chat, Message, Person)]


def test_delete_account_removes_all_its_data(client, anna, bob):
    for headers in (anna, bob):
        put(client, headers, ANNA)
        send(client, headers, create_chat(client, headers)["id"])
        with SessionLocal() as db:
            user_id = client.get("/me", headers=headers).json()["id"]
            db.add(Person(user_id=user_id, relation="mother", details={"birth_date": "1948-03-12"}, updated_at=utcnow()))
            db.commit()
    assert counts() == [2, 2, 2, 4, 2]

    response = client.request("DELETE", "/me", json={"password": PASSWORD}, headers=anna)

    assert response.status_code == 204
    assert counts() == [1, 1, 1, 2, 1]
    assert_error(client.get("/me", headers=anna), 401)
    assert client.get("/me/profile", headers=bob).json() == ANNA


def test_delete_account_with_wrong_password(client, anna):
    response = client.request("DELETE", "/me", json={"password": "wrong"}, headers=anna)

    assert_error(response, 403, "Wrong password")
    assert client.get("/me", headers=anna).status_code == 200


def test_profile_endpoints_require_a_token(client):
    requests = [
        ("GET", "/me/profile", None),
        ("PUT", "/me/profile", EMPTY),
        ("POST", "/me/password", {"current_password": "x", "new_password": "y" * 10}),
        ("DELETE", "/me", {"password": "x"}),
    ]
    for method, url, body in requests:
        assert_error(client.request(method, url, json=body), 401)
