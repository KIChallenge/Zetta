import re

import pytest
from sqlalchemy import func, select

from backend.database import SessionLocal
from backend.models import Message

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
QUESTION = "Meine Mutter kommt allein nicht mehr zurecht. Was kann ich tun?"


def register(client, name):
    response = client.post(
        "/auth/register",
        json={
            "email": f"{name}@example.at",
            "password": "secret-password-123",
            "display_name": name,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def anna(client):
    return register(client, "anna")


@pytest.fixture
def bob(client):
    return register(client, "bob")


def create_chat(client, headers, title="Hilfe für meine Mutter"):
    return client.post("/chats", json={"title": title}, headers=headers).json()


def assert_error(response, status, detail=None):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"status", "detail"}
    assert body["status"] == status
    if detail is not None:
        assert body["detail"] == detail


def test_create_chat(client, anna):
    response = client.post("/chats", json={"title": "Hilfe für meine Mutter"}, headers=anna)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "title", "created_at", "updated_at"}
    assert body["title"] == "Hilfe für meine Mutter"
    assert TIMESTAMP.match(body["created_at"])
    assert body["updated_at"] == body["created_at"]


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_create_chat_rejects_invalid_title(client, anna, title):
    assert_error(client.post("/chats", json={"title": title}, headers=anna), 422)


def test_list_chats_returns_same_shape_after_reload(client, anna):
    chat = create_chat(client, anna)

    response = client.get("/chats", headers=anna)

    assert response.status_code == 200
    assert response.json() == [chat]


def test_list_chats_is_empty_for_new_user(client, anna):
    assert client.get("/chats", headers=anna).json() == []


def test_list_chats_newest_first(client, anna):
    first = create_chat(client, anna, "first")
    second = create_chat(client, anna, "second")

    assert [c["id"] for c in client.get("/chats", headers=anna).json()] == [
        second["id"],
        first["id"],
    ]


def test_rename_moves_chat_to_top(client, anna):
    first = create_chat(client, anna, "first")
    second = create_chat(client, anna, "second")

    client.patch(f"/chats/{first['id']}", json={"title": "renamed"}, headers=anna)

    assert [c["id"] for c in client.get("/chats", headers=anna).json()] == [
        first["id"],
        second["id"],
    ]


def test_send_message_moves_chat_to_top(client, anna):
    first = create_chat(client, anna, "first")
    second = create_chat(client, anna, "second")

    client.post(f"/chats/{first['id']}/messages", json={"text": QUESTION}, headers=anna)

    assert [c["id"] for c in client.get("/chats", headers=anna).json()] == [
        first["id"],
        second["id"],
    ]


def test_list_chats_only_returns_own_chats(client, anna, bob):
    create_chat(client, anna)

    assert client.get("/chats", headers=bob).json() == []


def test_rename_chat(client, anna):
    chat = create_chat(client, anna)

    response = client.patch(f"/chats/{chat['id']}", json={"title": "Pflegegeld Mama"}, headers=anna)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == chat["id"]
    assert body["title"] == "Pflegegeld Mama"
    assert body["created_at"] == chat["created_at"]
    assert TIMESTAMP.match(body["updated_at"])


def test_rename_chat_rejects_invalid_title(client, anna):
    chat = create_chat(client, anna)

    assert_error(client.patch(f"/chats/{chat['id']}", json={"title": " "}, headers=anna), 422)


def test_delete_chat_removes_it_and_its_messages(client, anna):
    chat = create_chat(client, anna)
    kept = create_chat(client, anna, "kept")
    client.post(f"/chats/{chat['id']}/messages", json={"text": QUESTION}, headers=anna)
    client.post(f"/chats/{kept['id']}/messages", json={"text": QUESTION}, headers=anna)

    response = client.delete(f"/chats/{chat['id']}", headers=anna)

    assert response.status_code == 204
    assert response.content == b""
    assert [c["id"] for c in client.get("/chats", headers=anna).json()] == [kept["id"]]
    assert_error(client.get(f"/chats/{chat['id']}/messages", headers=anna), 404, "Chat not found")
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 2
    assert len(client.get(f"/chats/{kept['id']}/messages", headers=anna).json()) == 2


def test_send_message_returns_only_the_user_message(client, anna):
    chat = create_chat(client, anna)

    response = client.post(f"/chats/{chat['id']}/messages", json={"text": QUESTION}, headers=anna)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"status", "message"}
    assert body["status"] == "delivered"
    assert set(body["message"]) == {"id", "role", "text", "created_at"}
    assert body["message"]["role"] == "user"
    assert body["message"]["text"] == QUESTION
    assert TIMESTAMP.match(body["message"]["created_at"])


def test_every_message_is_answered_with_todo_oldest_first(client, anna):
    chat = create_chat(client, anna)
    url = f"/chats/{chat['id']}/messages"
    sent = [client.post(url, json={"text": text}, headers=anna).json() for text in ("eins", "zwei")]

    response = client.get(url, headers=anna)

    assert response.status_code == 200
    messages = response.json()
    assert [(m["role"], m["text"]) for m in messages] == [
        ("user", "eins"),
        ("assistant", "TODO"),
        ("user", "zwei"),
        ("assistant", "TODO"),
    ]
    assert messages[0] == sent[0]["message"]
    assert messages[2] == sent[1]["message"]


def test_messages_of_new_chat_are_empty(client, anna):
    chat = create_chat(client, anna)

    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


@pytest.mark.parametrize("text", ["", "   ", "x" * 10001])
def test_send_message_rejects_invalid_text(client, anna, text):
    chat = create_chat(client, anna)

    response = client.post(f"/chats/{chat['id']}/messages", json={"text": text}, headers=anna)

    assert_error(response, 422)
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


def chat_requests(chat_id):
    return [
        ("PATCH", f"/chats/{chat_id}", {"title": "x"}),
        ("DELETE", f"/chats/{chat_id}", None),
        ("GET", f"/chats/{chat_id}/messages", None),
        ("POST", f"/chats/{chat_id}/messages", {"text": "x"}),
    ]


def test_unknown_chat_returns_404(client, anna):
    for method, url, body in chat_requests("no-such-chat"):
        response = client.request(method, url, json=body, headers=anna)
        assert_error(response, 404, "Chat not found")


def test_other_users_chat_returns_404_and_is_unchanged(client, anna, bob):
    chat = create_chat(client, anna)

    for method, url, body in chat_requests(chat["id"]):
        response = client.request(method, url, json=body, headers=bob)
        assert_error(response, 404, "Chat not found")

    assert client.get("/chats", headers=anna).json() == [chat]
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


def test_chat_endpoints_require_a_token(client):
    requests = [("GET", "/chats", None), ("POST", "/chats", {"title": "x"})]
    for method, url, body in requests + chat_requests("any"):
        assert_error(client.request(method, url, json=body), 401)
