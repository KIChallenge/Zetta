import asyncio
import json
import re

import pytest
from sqlalchemy import func, select

from backend.app import app
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


def parse_events(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def send(client, headers, chat_id, text=QUESTION):
    response = client.post(f"/chats/{chat_id}/messages", json={"text": text}, headers=headers)
    assert response.status_code == 200
    return parse_events(response)


def history(client, headers, chat_id):
    messages = client.get(f"/chats/{chat_id}/messages", headers=headers).json()
    return [(m["role"], m["text"]) for m in messages]


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


def test_send_message_streams_the_reply(client, anna, llm):
    chat = create_chat(client, anna)

    response = client.post(f"/chats/{chat['id']}/messages", json={"text": QUESTION}, headers=anna)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events = parse_events(response)
    assert [name for name, _ in events] == ["message", "delta", "delta", "delta", "title", "done"]
    message, reply = events[0][1], events[-1][1]
    assert set(message) == {"id", "role", "text", "created_at"}
    assert message["role"] == "user"
    assert message["text"] == QUESTION
    assert TIMESTAMP.match(message["created_at"])
    assert [data["text"] for name, data in events if name == "delta"] == llm.deltas
    assert set(reply) == {"id", "role", "text", "created_at"}
    assert reply["role"] == "assistant"
    assert reply["text"] == "Hallo Anna!"
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == [message, reply]


def test_first_message_sets_a_generated_title(client, anna):
    chat = create_chat(client, anna)

    events = dict(send(client, anna, chat["id"]))

    title = events["title"]
    assert title["id"] == chat["id"]
    assert title["title"] == "Pflege für Mama"
    assert title["updated_at"] == events["message"]["created_at"]
    assert client.get("/chats", headers=anna).json() == [title]
    assert "title" not in dict(send(client, anna, chat["id"], "zwei"))


def test_failed_title_keeps_the_chat_title(client, anna, llm):
    llm.title_text = None
    chat = create_chat(client, anna)

    events = send(client, anna, chat["id"])

    assert [name for name, _ in events][-1] == "done"
    assert "title" not in dict(events)
    assert client.get("/chats", headers=anna).json()[0]["title"] == chat["title"]


def test_history_is_sent_oldest_first(client, anna, llm):
    chat = create_chat(client, anna)
    send(client, anna, chat["id"], "eins")
    send(client, anna, chat["id"], "zwei")

    assert llm.histories[-1] == [
        {"role": "user", "content": "eins"},
        {"role": "assistant", "content": "Hallo Anna!"},
        {"role": "user", "content": "zwei"},
    ]
    assert history(client, anna, chat["id"]) == [
        ("user", "eins"),
        ("assistant", "Hallo Anna!"),
        ("user", "zwei"),
        ("assistant", "Hallo Anna!"),
    ]


def test_history_is_capped_at_the_last_40_messages(client, anna, llm):
    chat = create_chat(client, anna)
    for i in range(21):
        send(client, anna, chat["id"], str(i))

    sent = llm.histories[-1]
    assert len(sent) == 40
    assert sent[0] == {"role": "assistant", "content": "Hallo Anna!"}
    assert sent[-1] == {"role": "user", "content": "20"}


@pytest.mark.parametrize(
    ("deltas", "fail"), [([], True), (["Hal"], True), ([], False)], ids=["early", "mid", "empty"]
)
def test_llm_error_sends_an_error_event_and_drops_the_message(client, anna, llm, deltas, fail):
    llm.deltas, llm.fail = deltas, fail
    chat = create_chat(client, anna)

    events = send(client, anna, chat["id"])

    assert events[0][0] == "message"
    assert events[-1] == ("error", {"status": 502, "detail": "LLM reply failed"})
    assert "done" not in dict(events)
    assert history(client, anna, chat["id"]) == []


async def stop_after_first_delta(path, headers):
    """Drive the app like a browser whose user presses Stop once the first delta arrived."""
    got_delta = asyncio.Event()
    request = {"type": "http.request", "body": json.dumps({"text": QUESTION}).encode()}

    async def receive():
        nonlocal request
        if request:
            first, request = request, None
            return first
        await got_delta.wait()
        return {"type": "http.disconnect"}

    async def send_(message):
        if b"event: delta" in message.get("body", b""):
            got_delta.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"authorization", headers["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await asyncio.wait_for(app(scope, receive, send_), timeout=5)


def test_stop_keeps_the_partial_reply(client, anna, llm):
    llm.deltas, llm.hang = ["Hallo"], True
    chat = create_chat(client, anna)

    asyncio.run(stop_after_first_delta(f"/chats/{chat['id']}/messages", anna))

    assert history(client, anna, chat["id"]) == [("user", QUESTION), ("assistant", "Hallo")]


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
