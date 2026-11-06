"""Discharge letters (spec 9 and 21.2): quote check, upload, confirm, plan with quotes. No real LLM."""

import pytest

from backend.documents import checked, pdf_text
from test_chats import (  # noqa: F401 (anna is a fixture)
    MOTHER, anna, answer, assert_error, create_chat, parse_events, reply, send, steps_of,
)

LETTER = (
    "Empfohlen werden: Mobile Hauskrankenpflege zur Unterstützung bei pflegerischen Aufgaben. "
    "Empfehlung: Prüfung einer stationären onkologischen Rehabilitation nach Abschluss der Strahlentherapie. "
    "Regelmäßige Blutdruckmessungen und Überprüfung der antihypertensiven Therapie."
)


def pdf(text: str) -> bytes:
    """A minimal one-page PDF with `text` (Helvetica, WinAnsi), enough for pypdf."""
    stream = f"BT /F1 9 Tf 20 800 Td ({text}) Tj ET".encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2000 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def test_pdf_text():
    assert "Hauskrankenpflege" in pdf_text(pdf(LETTER))


def test_only_quotes_that_are_in_the_letter_are_kept():
    items = [
        {"recommendation": "home_nursing", "quote": "Mobile Hauskrankenpflege zur Unterstützung"},
        # Line breaks, hyphens and case in the PDF text do not matter.
        {"recommendation": "inpatient_rehab", "quote": "PRÜFUNG einer stationären\nonkologischen Rehabilitation"},
        {"recommendation": "medical_aid", "quote": "Ein Rollator wird dringend empfohlen"},  # made up
        {"recommendation": "home_nursing", "quote": "Mobile Hauskrankenpflege zur Unterstützung bei"},  # duplicate
        {"recommendation": "blood_pressure", "quote": "Regelmäßige Blutdruckmessungen"},  # no such value
        {"recommendation": "home_help", "quote": "Therapie"},  # too short to prove anything
    ]
    assert [i["recommendation"] for i in checked(items, LETTER)] == ["home_nursing", "inpatient_rehab"]
    bullet = [{"recommendation": "home_nursing", "quote": "• Mobile Hauskrankenpflege"}]
    assert checked(bullet, LETTER)[0]["quote"] == "Mobile Hauskrankenpflege"


def upload(client, headers, chat_id, data, name="Entlassungsbrief.pdf"):
    return client.post(
        f"/chats/{chat_id}/documents",
        content=data,
        headers={**headers, "Content-Type": "application/pdf", "X-Filename": name},
    )


def test_upload_confirm_and_plan_with_quotes(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])
    llm.letter_items = [
        {"recommendation": "inpatient_rehab", "quote": "Prüfung einer stationären onkologischen Rehabilitation"},
        {"recommendation": "home_nursing", "quote": "Mobile Hauskrankenpflege"},
        {"recommendation": "follow_up_check", "quote": "Kontrolle beim Hausarzt in einer Woche"},  # not in the letter
    ]

    response = upload(client, anna, chat["id"], pdf(LETTER))

    assert response.status_code == 201
    document, confirm = response.json()
    assert (document["kind"], document["text"]) == ("document", "Entlassungsbrief.pdf")
    assert confirm["kind"] == "confirm"
    assert [i["recommendation"] for i in confirm["payload"]["items"]] == ["inpatient_rehab", "home_nursing"]
    assert confirm["payload"]["items"][0]["label"] == "Stationäre Reha"
    assert LETTER not in str(client.get(f"/chats/{chat['id']}/messages", headers=anna).json())

    events = answer(client, anna, chat["id"], "documented_recommendations", ["inpatient_rehab"])
    assert events[0][1]["text"] == "Stimmt so"
    for key, value in [("district", "1100"), ("pension_payer", "pv")]:
        events = answer(client, anna, chat["id"], key, value)
    events = answer(client, anna, chat["id"], "lives_alone", "yes")

    plan = dict(events)["plan"]
    services = {s["id"]: s for s in plan["services"]}
    assert services["rehab"]["quotes"] == ["Prüfung einer stationären onkologischen Rehabilitation"]
    assert "home_nursing_medical" not in services  # not confirmed
    call = steps_of(plan)["rehab.call_doctor"]
    assert call["institution"]["name"] == "Ihre behandelnde Ärztin oder Ihr behandelnder Arzt"
    assert "contact" not in call  # the user's own doctor: no number from the system
    assert call["script"]["opening"]

    # Changed later under "Verstanden": a fact edit, not the confirm card's answer.
    events = answer(client, anna, chat["id"], "documented_recommendations", "home_nursing")
    assert events[0][1]["text"] == "Laut Ihrem Dokument: Hauskrankenpflege"


def test_unoffered_recommendations_cannot_be_confirmed(client, anna, llm):
    chat = create_chat(client, anna)
    llm.letter_items = [{"recommendation": "home_nursing", "quote": "Mobile Hauskrankenpflege"}]
    upload(client, anna, chat["id"], pdf(LETTER))

    facts = dict(answer(client, anna, chat["id"], "documented_recommendations", ["home_nursing", "medical_aid"]))["facts"]

    letter = next(f for f in facts if f["key"] == "documented_recommendations")
    assert letter["source"] == "document"


def test_recommendations_are_never_taken_from_chat_text(client, anna, llm):
    llm.facts = {**MOTHER, "documented_recommendations": ["inpatient_rehab"]}
    chat = create_chat(client, anna)

    facts = dict(send(client, anna, chat["id"]))["facts"]

    assert "documented_recommendations" not in [f["key"] for f in facts]


@pytest.mark.parametrize(
    ("data", "status"),
    [(b"not a pdf", 415), (pdf("kurz"), 422), (b"%PDF" + b"x" * (10 * 1024 * 1024), 413)],
)
def test_bad_uploads_are_rejected(client, anna, data, status):
    chat = create_chat(client, anna)

    assert_error(upload(client, anna, chat["id"], data), status)
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


def test_failed_letter_extraction_saves_nothing(client, anna, llm):
    llm.fail = True
    chat = create_chat(client, anna)

    assert_error(upload(client, anna, chat["id"], pdf(LETTER)), 502)
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


def test_letter_without_known_recommendations(client, anna, llm):
    chat = create_chat(client, anna)

    confirm = upload(client, anna, chat["id"], pdf(LETTER)).json()[1]

    assert confirm["payload"]["items"] == []
    assert reply(parse_events(client.post(f"/chats/{chat['id']}/messages", json={"text": "ok"}, headers=anna)))
