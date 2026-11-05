"""The fixes from docs/security-review.md: limits, sessions, the PDF worker, redaction and headers."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend import documents, guards
from backend.app import app
from backend.database import engine
from backend.dependencies import COOKIE
from test_chats import PROFILE, anna, create_chat, register, send, to_plan  # noqa: F401 (anna is a fixture)
from test_documents import LETTER, pdf, upload

PASSWORD = "secret-password-123"


def blank_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# Body size (H-2)


def test_large_json_bodies_are_refused_before_they_are_read(client):
    response = client.post("/auth/login", content=b"{" + b" " * guards.MAX_JSON, headers={"Content-Type": "application/json"})

    assert response.status_code == 413


def test_a_chunked_upload_is_stopped_at_the_limit(client, anna):
    chat = create_chat(client, anna)
    body = iter([b"%PDF", b"0" * guards.MAX_UPLOAD])  # no Content-Length: counted while it is read

    response = client.post(f"/chats/{chat['id']}/documents", content=body, headers={**anna, "Content-Type": "application/pdf"})

    assert response.status_code == 413


# PDF parsing (H-1, M-2)


def test_a_pdf_with_too_many_pages_is_not_read(client, anna):
    chat = create_chat(client, anna)

    response = upload(client, anna, chat["id"], blank_pdf(documents.MAX_PAGES + 1))

    assert (response.status_code, response.json()["detail"]) == (422, "Unreadable PDF")


def test_a_pdf_that_takes_too_long_is_stopped(client, anna, monkeypatch):
    monkeypatch.setattr(documents, "PARSE_SECONDS", 0.001)
    chat = create_chat(client, anna)

    assert upload(client, anna, chat["id"], pdf(LETTER)).status_code == 422


def test_the_letter_text_is_capped():
    assert len(documents.pdf_text(pdf("Hauskrankenpflege " * 5000))) == documents.MAX_CHARS


def test_a_quote_is_one_sentence_not_the_whole_letter():
    letter = "Empfohlen wird Hauskrankenpflege. " * 20

    assert documents.checked([{"recommendation": "home_nursing", "quote": letter.strip()}], letter) == []


# Redaction (M-5)


def test_identifiers_in_messages_and_letters_do_not_reach_the_llm(client, anna, llm):
    chat = create_chat(client, anna)
    send(client, anna, chat["id"], "Meine SV-Nummer ist 1237 010180, schreiben Sie an anna@example.at.")
    upload(client, anna, chat["id"], pdf(f"Patientin geb. 01.01.1950, SVNR 1237010180. {LETTER}"))

    sent = json.dumps(llm.calls, ensure_ascii=False)
    assert "[SV-Nummer]" in sent and "[Datum]" in sent
    for leaked in ("1237", "anna@example.at", "01.01.1950"):
        assert leaked not in sent


def test_no_profile_value_reaches_the_llm(client, anna, llm):
    client.put("/me/profile", json=PROFILE, headers=anna)
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    sent = json.dumps(llm.calls, ensure_ascii=False)
    for field in ("full_name", "street", "svnr", "phone", "contact_email"):
        assert PROFILE[field].replace(" ", "") not in sent.replace(" ", ""), field


def test_a_title_with_contact_data_is_not_used(client, anna, llm):
    llm.title_text = "Rufen Sie 0900 123 456 an: bit.ly/x"
    chat = create_chat(client, anna)

    events = send(client, anna, chat["id"])

    assert "title" not in [name for name, _ in events]
    assert client.get("/chats", headers=anna).json()[0]["title"] == chat["title"]


# Rate limits (M-2, M-3)


def test_login_is_blocked_after_five_failures(client):
    register(client, "anna")
    for _ in range(5):
        assert client.post("/auth/login", json={"email": "anna@example.at", "password": "wrong"}).status_code == 401

    response = client.post("/auth/login", json={"email": "anna@example.at", "password": PASSWORD})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(15 * 60)


def test_registrations_are_limited(client, monkeypatch):
    monkeypatch.setattr(guards.REGISTRATIONS, "count", 2)
    register(client, "anna")
    register(client, "bob")

    response = client.post("/auth/register", json={"email": "eve@example.at", "password": PASSWORD, "display_name": "Eve"})

    assert response.status_code == 429


def test_llm_turns_are_limited(client, anna, monkeypatch):
    monkeypatch.setattr(guards.TURNS, "count", 1)
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])

    response = client.post(f"/chats/{chat['id']}/messages", json={"text": "Und weiter?"}, headers=anna)

    assert response.status_code == 429


def test_uploads_are_limited(client, anna, monkeypatch):
    monkeypatch.setattr(guards.UPLOADS, "count", 1)
    chat = create_chat(client, anna)
    upload(client, anna, chat["id"], pdf(LETTER))

    assert upload(client, anna, chat["id"], pdf(LETTER)).status_code == 429


def test_password_checks_are_limited(client, anna):
    wrong = {"current_password": "wrong", "new_password": "new-password-456"}
    for _ in range(5):
        assert client.post("/me/password", json=wrong, headers=anna).status_code == 403

    assert client.post("/me/password", json={**wrong, "current_password": PASSWORD}, headers=anna).status_code == 429


@pytest.mark.parametrize("password", ["123456789", "password123", "Passwort123", "aaaaaaaaaaaa", "ababababab"])
def test_short_or_common_passwords_are_refused(client, password):
    response = client.post("/auth/register", json={"email": "anna@example.at", "password": password, "display_name": "Anna"})

    assert response.status_code == 422


# Sessions (M-4, L-3)


def test_a_password_change_ends_older_tokens(client, anna):
    response = client.post("/me/password", json={"current_password": PASSWORD, "new_password": "new-password-456"}, headers=anna)

    assert response.status_code == 204
    assert client.get("/me", headers=anna).status_code == 401
    assert client.get("/me", headers={"Authorization": f"Bearer {response.cookies[COOKIE]}"}).status_code == 200


def test_logout_ends_the_token(client, anna):
    response = client.post("/auth/logout", headers=anna)

    assert response.status_code == 204
    assert f'{COOKIE}=""' in response.headers["set-cookie"]
    assert client.get("/me", headers=anna).status_code == 401


def test_the_browser_session_is_an_httponly_cookie(client):  # client: a fresh database
    with TestClient(app) as browser:
        response = browser.post("/auth/register", json={"email": "anna@example.at", "password": PASSWORD, "display_name": "Anna"})
        cookie = response.headers["set-cookie"]

        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" not in cookie  # plain http
        assert browser.get("/me").status_code == 200
        # Changes need a header another site cannot send without CORS.
        assert browser.post("/chats", json={"title": "x"}).status_code == 403
        assert browser.post("/chats", json={"title": "x"}, headers={"X-Requested-With": "fetch"}).status_code == 201


def test_the_cookie_is_secure_over_https(client):
    with TestClient(app, base_url="https://testserver") as browser:
        response = browser.post("/auth/register", json={"email": "anna@example.at", "password": PASSWORD, "display_name": "Anna"})

        assert "Secure" in response.headers["set-cookie"]


# Deletion (L-1)


def test_a_deleted_account_cannot_be_read_back_from_the_database_file(client, anna):
    client.put("/me/profile", json=PROFILE, headers=anna)

    client.request("DELETE", "/me", json={"password": PASSWORD}, headers=anna)

    with open(engine.url.database, "rb") as db:
        assert PROFILE["svnr"].replace(" ", "").encode() not in db.read()


# Headers and hosts (M-1, L-2)


def test_every_response_has_the_security_headers(client):
    response = client.get("/me")

    assert response.status_code == 401
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_the_api_map_is_not_published(client):
    assert {client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")} == {404}


def test_other_host_names_are_refused(client):
    assert client.get("/me", headers={"Host": "evil.example"}).status_code == 400
