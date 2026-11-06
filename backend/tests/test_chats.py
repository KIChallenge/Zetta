import asyncio
import io
import json
import re

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from backend import pipeline
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
    assert set(body) == {"id", "title", "created_at", "updated_at", "status", "next"}
    assert body["status"] is None and body["next"] is None
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


MOTHER = {"subject": "mother", "needs_daily_help": "a_lot"}
PROFILE = {
    "full_name": "Anna Berger",
    "street": "Favoritenstraße 1",
    "postal_code": "1100",
    "city": "Wien",
    "svnr": "1237 010180",
    "phone": "0660 1234567",
    "contact_email": "anna@example.at",
}


def answer(client, headers, chat_id, key, value):
    response = client.post(f"/chats/{chat_id}/answers", json={"fact_key": key, "value": value}, headers=headers)
    assert response.status_code == 200
    return parse_events(response)


def reply(events):
    assert events[-1][0] == "done", events
    return events[-1][1]


def to_plan(client, headers, llm, chat_id):
    """First message about the mother, then chip answers until the plan."""
    llm.facts = MOTHER
    assert reply(send(client, headers, chat_id))["payload"]["fact_key"] == "district"
    assert reply(answer(client, headers, chat_id, "district", "1100"))["payload"]["fact_key"] == "pension_payer"
    assert reply(answer(client, headers, chat_id, "pension_payer", "pv"))["payload"]["fact_key"] == "lives_alone"
    return answer(client, headers, chat_id, "lives_alone", "yes")


def steps_of(plan):
    return {s["id"]: s for s in plan["steps"]}


def test_first_message_streams_facts_and_one_question(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)

    response = client.post(f"/chats/{chat['id']}/messages", json={"text": QUESTION}, headers=anna)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response)
    assert [name for name, _ in events] == ["message", "facts", "title", "done"]
    message, facts, question = events[0][1], events[1][1], events[-1][1]
    assert set(message) == {"id", "role", "kind", "text", "payload", "created_at"}
    assert (message["role"], message["kind"], message["text"]) == ("user", "text", QUESTION)
    assert TIMESTAMP.match(message["created_at"])
    assert [(f["key"], f["value"], f["source"]) for f in facts] == [
        ("subject", "mother", "user_text"),
        ("needs_daily_help", "a_lot", "user_text"),
    ]
    assert (question["role"], question["kind"]) == ("assistant", "question")
    assert question["text"] == "In welchem Wiener Bezirk wohnt Ihre Mutter?"
    assert question["payload"]["fact_key"] == "district"
    assert {"value": "1100", "label": "10., Favoriten"} in question["payload"]["chips"]
    assert {"value": "unknown", "label": "Weiß nicht"} in question["payload"]["chips"]
    assert llm.calls[0] == ("extract", {"text": QUESTION, "question": None})
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == [message, question]
    assert client.get("/chats", headers=anna).json()[0]["status"] == "Frage offen"
    assert client.get("/chats", headers=anna).json()[0]["next"] == {
        "kind": "question", "text": question["text"], "type": None, "institution": None, "reachable": None, "open_steps": 0,
    }  # fmt: skip


def test_the_chat_list_names_the_next_step_of_a_plan(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    up = client.get("/chats", headers=anna).json()[0]["next"]

    plan = client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"]
    first = next(s for s in plan["steps"] if s["status"] == "available" and s["type"] != "wait")
    assert (up["kind"], up["text"], up["type"], up["open_steps"]) == ("step", first["title"], first["type"], 11)
    assert up["institution"] == (first.get("institution") or {}).get("name")
    if first["type"] == "call":
        assert up["reachable"] == first["contact"]["reachable"]


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


def test_a_chip_answer_sets_the_fact_without_the_llm(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])
    calls = len(llm.calls)

    events = answer(client, anna, chat["id"], "district", "1100")

    assert [name for name, _ in events] == ["message", "facts", "done"]
    message = events[0][1]
    assert (message["kind"], message["text"]) == ("answer", "10., Favoriten")
    assert message["payload"] == {"fact_key": "district", "value": "1100"}
    district = next(f for f in events[1][1] if f["key"] == "district")
    assert (district["value"], district["source"]) == ("1100", "chip")
    assert reply(events)["text"] == "Bezieht Ihre Mutter eine Pension? Wenn ja, von welcher Stelle?"
    assert len(llm.calls) == calls


def test_a_typed_answer_is_extracted_with_the_question_as_context(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])

    send(client, anna, chat["id"], "Favoriten")

    assert llm.calls[-1] == ("extract", {"text": "Favoriten", "question": "In welchem Wiener Bezirk wohnt Ihre Mutter?"})


def test_chip_answers_win_over_a_later_extraction(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])
    answer(client, anna, chat["id"], "district", "1100")

    llm.facts = {"district": "1030"}
    facts = dict(send(client, anna, chat["id"], "Mein Bruder wohnt im 3. Bezirk"))["facts"]

    assert next(f for f in facts if f["key"] == "district")["value"] == "1100"


def test_plan_has_filled_scripts_and_no_personal_data_goes_to_the_llm(client, anna, llm):
    client.put("/me/profile", json=PROFILE, headers=anna)
    chat = create_chat(client, anna)

    events = to_plan(client, anna, llm, chat["id"])

    assert [name for name, _ in events] == ["message", "facts", "plan", "done"]
    plan, done = events[2][1], reply(events)
    assert (done["kind"], done["text"], done["payload"]) == ("plan", llm.intro_text, {"version": 1})
    assert [s["id"] for s in plan["services"]] == ["care_allowance", "home_care_fsw", "carer_support"]
    steps = steps_of(plan)
    call = steps["care_allowance.call"]
    assert call["status"] == "available"
    assert call["contact"]["value"] == "+43 (0)5 03 03"
    assert call["contact"]["href"] == "tel:+4350303"
    assert call["contact"]["hours"] == "Mo–Mi 7:00–15:30, Do 7:00–18:00, Fr 7:00–15:00"
    assert call["script"]["opening"] == "Guten Tag, hier spricht Anna Berger."
    assert call["script"]["source"] == "llm"
    assert call["script"]["have_ready"] == [{"label": "SV-Nummer Ihrer Mutter", "value": None}]
    assert [o["id"] for o in call["outcomes"]] == ["reached", "callback", "not_reached"]
    mail = steps["home_care_fsw.send_application"]
    assert mail["status"] == "blocked"
    assert mail["contact"]["href"] == "mailto:kundinnenservice@fsw.at"
    assert mail["script"]["body"].endswith("Anna Berger")
    sent = json.dumps(llm.calls, ensure_ascii=False)
    for value in ("Anna", "Berger", "1234567", "anna@example.at", "1237", "Favoritenstraße"):
        assert value not in sent
    assert client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"] == plan
    assert client.get("/chats", headers=anna).json()[0]["status"] == "11 offene Schritte"


def test_profile_changes_show_up_in_the_scripts_right_away(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    client.put("/me/profile", json={**PROFILE, "full_name": "Anna Huber"}, headers=anna)

    plan = client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"]
    assert steps_of(plan)["care_allowance.call"]["script"]["opening"] == "Guten Tag, hier spricht Anna Huber."


def test_step_states_survive_a_reload(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    url = f"/chats/{chat['id']}/steps"

    client.patch(f"{url}/care_allowance.call", json={"outcome": "reached", "note": "Antrag kommt per Post"}, headers=anna)
    client.patch(f"{url}/documents", json={"checks": ["photo_id", "income_proof"]}, headers=anna)
    plan = client.patch(f"{url}/documents", json={"status": "done"}, headers=anna).json()

    assert plan == client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"]
    steps = steps_of(plan)
    assert (steps["care_allowance.call"]["status"], steps["care_allowance.call"]["outcome"]) == ("done", "reached")
    assert steps["care_allowance.call"]["note"] == "Antrag kommt per Post"
    assert steps["documents"]["checks"] == ["photo_id", "income_proof"]
    assert steps["care_allowance.submit"]["status"] == "available"
    assert plan["status"] == "9 offene Schritte"


def test_not_reached_keeps_the_call_open(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    plan = client.patch(
        f"/chats/{chat['id']}/steps/care_allowance.call", json={"outcome": "not_reached"}, headers=anna
    ).json()

    call = steps_of(plan)["care_allowance.call"]
    assert (call["status"], call["outcome"]) == ("available", "not_reached")
    assert TIMESTAMP.match(call["updated_at"])


def test_a_done_step_can_be_reopened(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    url = f"/chats/{chat['id']}/steps/care_allowance.info"
    client.patch(url, json={"outcome": "read"}, headers=anna)

    plan = client.patch(url, json={"status": "open"}, headers=anna).json()

    info = steps_of(plan)["care_allowance.info"]
    assert (info["status"], info["outcome"]) == ("available", None)


@pytest.mark.parametrize(
    ("step", "body", "status"),
    [
        ("nope", {"status": "done"}, 404),
        ("care_allowance.call", {"outcome": "granted"}, 422),
        ("documents", {"checks": ["passport_of_the_cat"]}, 422),
        ("documents", {"status": "finished"}, 422),
    ],
)
def test_invalid_step_updates_are_rejected(client, anna, llm, step, body, status):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    assert_error(client.patch(f"/chats/{chat['id']}/steps/{step}", json=body, headers=anna), status)


def test_step_update_without_a_plan_is_404(client, anna):
    chat = create_chat(client, anna)

    assert_error(client.patch(f"/chats/{chat['id']}/steps/documents", json={"status": "done"}, headers=anna), 404)


def test_replan_keeps_step_states_and_unchanged_scripts(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    client.patch(f"/chats/{chat['id']}/steps/care_allowance.call", json={"outcome": "reached"}, headers=anna)
    scripted = sum(1 for method, _ in llm.calls if method == "scripts")

    events = answer(client, anna, chat["id"], "lives_alone", "no")

    plan = dict(events)["plan"]
    assert reply(events)["payload"] == {"version": 2}
    assert reply(events)["text"] == llm.intro_text
    assert events[0][1]["text"] == "Lebt allein: Nein"
    assert steps_of(plan)["care_allowance.call"]["status"] == "done"
    # Only the FSW call uses lives_alone, so only its script is written again.
    rewritten = [method_input for method, method_input in llm.calls if method == "scripts"][scripted:]
    assert [[s["step_id"] for s in batch] for batch in rewritten] == [["home_care_fsw.call"]]


def test_a_message_without_new_facts_keeps_the_plan(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    llm.facts = {}

    events = send(client, anna, chat["id"], "Und was mache ich jetzt?")

    assert "plan" not in dict(events)
    assert (reply(events)["kind"], reply(events)["text"]) == ("text", pipeline.TO_PLAN)
    assert client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"]["version"] == 1


def test_a_plan_topic_named_without_new_facts_gets_its_summary(client, anna, llm):
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    llm.facts = {}

    events = send(client, anna, chat["id"], "Was ist Pflegegeld?")

    summary = next(s.summary for s in pipeline.get_corpus().services if s.id == "care_allowance")
    assert "plan" not in dict(events)
    assert (reply(events)["kind"], reply(events)["text"]) == ("text", summary)


def test_a_long_plan_intro_falls_back_to_one_fixed_sentence(client, anna, llm):
    llm.intro_text = (
        "Gerne, ich bereite die nächsten Schritte zu Pflegegeld, Pflege und Betreuung zu Hause sowie Entlastung "
        "für pflegende Angehörige für Sie vor."
    )
    chat = create_chat(client, anna)

    assert reply(to_plan(client, anna, llm, chat["id"]))["text"] == "Hier ist Ihr Plan."


def test_without_the_llm_the_chips_and_fallback_scripts_still_lead_to_a_plan(client, anna, llm):
    llm.fail, llm.title_text = True, None
    chat = create_chat(client, anna)

    first = reply(send(client, anna, chat["id"]))
    assert (first["kind"], first["payload"]["fact_key"]) == ("question", "goal")
    assert {"value": "unknown", "label": "Etwas anderes"} in first["payload"]["chips"]
    for key, value in [("goal", ["apply_care_allowance"]), ("subject", "mother"), ("district", "1100")]:
        assert reply(answer(client, anna, chat["id"], key, value))["kind"] == "question"
    events = answer(client, anna, chat["id"], "pension_payer", "pv")

    plan = dict(events)["plan"]
    assert reply(events)["text"] == "Hier ist Ihr Plan."
    call = steps_of(plan)["care_allowance.call"]
    assert call["script"]["source"] == "fallback"
    assert call["script"]["opening"] == "Guten Tag, mein Name ist [Ihr Name]. Ich rufe wegen eines Antrags auf Pflegegeld für meine Mutter an."


def test_a_doctor_appointment_picked_by_chip_still_asks_when(client, anna, llm):
    llm.fail, llm.title_text = True, None
    chat = create_chat(client, anna)
    reply(send(client, anna, chat["id"]))

    asked = []
    events = answer(client, anna, chat["id"], "goal", ["doctor_appointment"])
    values = {"district": "1100", "appointment_reason": "check_up", "specialty": "dermatology", "preferred_time": "morning"}
    while (message := reply(events))["kind"] == "question":
        key = message["payload"]["fact_key"]
        asked.append(key)
        events = answer(client, anna, chat["id"], key, values[key])

    assert sorted(asked) == sorted(values)
    doctors = steps_of(dict(events)["plan"])["doctor_appointment.call"]["doctors"]
    assert len(doctors) == 5
    assert doctors[0]["contact"]["href"].startswith("tel:+43")


def test_medical_question_gets_the_boundary_card(client, anna, llm):
    llm.medical = True
    chat = create_chat(client, anna)

    card = reply(send(client, anna, chat["id"], "Welche Tabletten helfen gegen Schwindel?"))

    assert (card["kind"], card["payload"]["card"]) == ("card", "boundary")
    hotline = card["payload"]["contacts"][0]
    assert hotline["name"] == "Gesundheitsberatung 1450"
    assert hotline["channels"][0]["href"] == "tel:1450"
    assert hotline["channels"][0]["reachable"]["open"] is True
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json()[-1] == card


def test_outside_vienna_gets_the_out_of_scope_card(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])

    card = reply(answer(client, anna, chat["id"], "district", "outside_vienna"))

    assert card["payload"]["card"] == "out_of_scope"


def test_the_question_loop_stops_at_the_cap(client, anna, llm):
    chat = create_chat(client, anna)
    for _ in range(4):
        assert reply(send(client, anna, chat["id"], "Hallo"))["payload"]["fact_key"] == "goal"

    card = reply(send(client, anna, chat["id"], "Hallo"))

    assert card["payload"]["card"] == "general"
    assert card["payload"]["contacts"][0]["channels"][0]["href"] == "tel:+435076611"


def test_an_off_topic_message_does_not_stop_answers_about_the_plan(client, anna, llm):
    chat = create_chat(client, anna)
    facts = dict(to_plan(client, anna, llm, chat["id"]))["facts"]
    llm.facts, llm.off_topic = {"subject": "self", "district": "outside_vienna"}, True

    off = send(client, anna, chat["id"], "Wie wird das Wetter in Graz?")
    # The real extraction also sets a goal here, which leaves the plan as it is.
    llm.facts, llm.off_topic = {"goal": ["find_support_services"], "asks_about": "home_care_fsw"}, False
    events = send(client, anna, chat["id"], "Was kostet die Heimhilfe?")

    summary = next(s.summary for s in pipeline.get_corpus().services if s.id == "home_care_fsw")
    assert (reply(events)["kind"], reply(events)["text"]) == ("text", summary)
    assert "plan" not in dict(events)
    assert dict(off)["facts"] == facts
    assert (reply(off)["kind"], reply(off)["text"]) == ("text", pipeline.OFF_TOPIC_PLAN)


def test_off_topic_messages_ask_the_open_question_again_without_using_up_the_cap(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])
    llm.facts, llm.off_topic = {}, True

    again = [reply(send(client, anna, chat["id"], "Erzähl mir einen Witz")) for _ in range(3)]

    assert reply(answer(client, anna, chat["id"], "district", "1100"))["payload"]["fact_key"] == "pension_payer"
    assert reply(answer(client, anna, chat["id"], "pension_payer", "pv"))["payload"]["fact_key"] == "lives_alone"
    assert dict(answer(client, anna, chat["id"], "lives_alone", "yes"))["plan"]["services"]
    assert {(q["payload"]["fact_key"], q["payload"]["note"]) for q in again} == {("district", pipeline.OFF_TOPIC)}


def test_an_off_topic_first_message_gets_the_first_question_with_a_hint(client, anna, llm):
    llm.off_topic = True
    chat = create_chat(client, anna)

    first = reply(send(client, anna, chat["id"], "Wer gewinnt heute das Fußballspiel?"))

    assert (first["payload"]["fact_key"], first["payload"]["note"]) == ("goal", pipeline.OFF_TOPIC)


def test_after_the_boundary_card_a_new_topic_starts_fresh(client, anna, llm):
    llm.facts = {"subject": "self", "goal": ["doctor_appointment"], "appointment_reason": "acute"}
    chat = create_chat(client, anna)
    boundary = send(client, anna, chat["id"], "Ich brauche heute einen Arzttermin, ich habe starke Schmerzen.")
    llm.facts = {**MOTHER, "goal": ["apply_care_allowance"]}

    events = send(client, anna, chat["id"], QUESTION)

    assert reply(boundary)["payload"]["card"] == "boundary"
    assert reply(events)["kind"] == "question"
    assert "appointment_reason" not in {f["key"] for f in dict(boundary)["facts"]}


def test_a_vienna_district_named_later_ends_outside_vienna(client, anna, llm):
    llm.facts = MOTHER
    chat = create_chat(client, anna)
    send(client, anna, chat["id"])
    answer(client, anna, chat["id"], "district", "outside_vienna")
    llm.facts = {"district": "1100"}

    events = send(client, anna, chat["id"], "Entschuldigung, sie wohnt doch in Favoriten.")

    assert reply(events)["payload"]["fact_key"] == "pension_payer"


@pytest.mark.parametrize(
    "body",
    [{"fact_key": "favourite_colour", "value": "blue"}, {"fact_key": "district", "value": "9999"},
     {"fact_key": "goal", "value": "no_such_goal"}, {"fact_key": "goal", "value": []}],
)  # fmt: skip
def test_answers_reject_unknown_facts_and_values(client, anna, body):
    chat = create_chat(client, anna)

    assert_error(client.post(f"/chats/{chat['id']}/answers", json=body, headers=anna), 422)
    assert client.get(f"/chats/{chat['id']}/messages", headers=anna).json() == []


def test_an_unexpected_error_sends_an_error_event_and_drops_the_message(client, anna, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(pipeline, "evaluate", broken)
    chat = create_chat(client, anna)

    events = send(client, anna, chat["id"])

    assert events[0][0] == "message"
    assert events[-1] == ("error", {"status": 502, "detail": "Reply failed"})
    assert history(client, anna, chat["id"]) == []


async def stop_after_message(path, headers):
    """Drive the app like a browser whose user leaves the chat once the message was saved."""
    saved = asyncio.Event()
    request = {"type": "http.request", "body": json.dumps({"text": QUESTION}).encode()}

    async def receive():
        nonlocal request
        if request:
            first, request = request, None
            return first
        await saved.wait()
        return {"type": "http.disconnect"}

    async def send_(message):
        if b"event: message" in message.get("body", b""):
            saved.set()

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
            (b"host", b"testserver"),
            (b"authorization", headers["Authorization"].encode()),
            (b"content-type", b"application/json"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await asyncio.wait_for(app(scope, receive, send_), timeout=5)


def test_leaving_during_the_extraction_keeps_the_message(client, anna, llm):
    llm.hang = True
    chat = create_chat(client, anna)

    asyncio.run(stop_after_message(f"/chats/{chat['id']}/messages", anna))

    assert history(client, anna, chat["id"]) == [("user", QUESTION)]


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
        ("POST", f"/chats/{chat_id}/answers", {"fact_key": "district", "value": "1100"}),
        ("GET", f"/chats/{chat_id}/state", None),
        ("PATCH", f"/chats/{chat_id}/steps/documents", {"status": "done"}),
        ("POST", f"/chats/{chat_id}/steps/documents/form", {}),
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


def test_an_outcome_opens_its_branch(client, anna, llm):
    chat = create_chat(client, anna)
    plan = dict(to_plan(client, anna, llm, chat["id"]))["plan"]
    assert "care_allowance.clarify" not in steps_of(plan)
    url = f"/chats/{chat['id']}/steps/care_allowance.decision"
    assert [o["id"] for o in steps_of(plan)["care_allowance.decision"]["outcomes"]] == ["granted", "rejected"]

    plan = client.patch(url, json={"outcome": "rejected"}, headers=anna).json()

    clarify = steps_of(plan)["care_allowance.clarify"]
    assert (clarify["status"], clarify["contact"]["href"]) == ("available", "tel:+4350303")
    assert clarify["script"]["opening"]  # written with the plan, shown once the branch opens
    assert "care_allowance.clarify" not in steps_of(client.patch(url, json={"outcome": "granted"}, headers=anna).json())


def test_form_steps_offer_the_form_filled_in_with_the_profile(client, anna, bob, llm):
    client.put("/me/profile", json=PROFILE, headers=anna)
    chat = create_chat(client, anna)
    steps = steps_of(dict(to_plan(client, anna, llm, chat["id"]))["plan"])

    # The card shows how far the form is; the wizard asks for the rest. The FSW form goes with an email.
    assert steps["care_allowance.submit"]["form"]["wizard"] == {"done": 3, "total": 16}  # Anna's name, the pension
    assert steps["home_care_fsw.send_application"]["form"]["wizard"]["total"] == 9
    response = client.get(f"/chats/{chat['id']}/steps/care_allowance.submit/form", headers=anna)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    fields = PdfReader(io.BytesIO(response.content)).get_fields()
    assert fields["Familienname andere"]["/V"] == "Berger"
    assert fields["Email2"]["/V"] == "anna@example.at"
    assert fields["Fam.Name"].get("/V") in (None, "")
    assert_error(client.get(f"/chats/{chat['id']}/steps/care_allowance.call/form", headers=anna), 404)
    assert_error(client.get(f"/chats/{chat['id']}/steps/care_allowance.submit/form", headers=bob), 404)


def kept(client, headers):
    """Relation -> entry -> the value as the settings page shows it, for the people with kept details."""
    return {
        p["relation"]: {e["entry"]: e["shown"] for e in p["entries"] if e["shown"]}
        for p in client.get("/me/people", headers=headers).json()
        if p["kept"]
    }


def care_url(chat):
    return f"/chats/{chat['id']}/steps/care_allowance.submit/form"


def test_details_typed_into_one_form_fill_the_next(client, anna, bob, llm):
    client.put("/me/profile", json=PROFILE, headers=anna)
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])
    answers = {"first_name": "Maria", "last_name": "Berger", "birth_date": "12.03.1948", "sex": "female", "rep_title": "Mag."}
    client.put(f"{care_url(chat)}/answers", json={"answers": answers}, headers=anna)

    response = client.post(care_url(chat), json={"remember": True}, headers=anna)

    fields = PdfReader(io.BytesIO(response.content)).get_fields()
    assert (fields["Fam.Name"]["/V"], fields["Geburtsdatum"]["/V"], fields["Titel2"]["/V"]) == ("Berger", "12.03.1948", "Mag.")
    assert kept(client, anna) == {
        "self": {"title": "Mag."},
        "mother": {"name": "Maria Berger", "birth_date": "12.03.1948", "sex": "weiblich"},
    }
    assert kept(client, bob) == {}
    # The next form has them, untouched by its wizard so far.
    fsw = PdfReader(io.BytesIO(client.get(f"/chats/{chat['id']}/steps/home_care_fsw.send_application/form", headers=anna).content))
    assert (fsw.get_fields()["Familienname Titel KundIn"]["/V"], fsw.get_fields()["Geburtsdatum KundIn"]["/V"]) == ("Berger", "12.03.1948")


def test_kept_details_can_be_deleted(client, anna, llm):
    client.put("/me/people/mother", json={"birth_date": "1948-03-12"}, headers=anna)

    assert client.delete("/me/people/mother", headers=anna).status_code == 204
    assert kept(client, anna) == {}
    assert_error(client.delete("/me/people/mother", headers=anna), 404)


def test_details_entered_in_the_settings_fill_the_first_form(client, anna, llm):
    response = client.put("/me/people/mother", json={"full_name": "Maria Berger", "sex": "female"}, headers=anna)
    chat = create_chat(client, anna)
    to_plan(client, anna, llm, chat["id"])

    assert response.json()["kept"] is True
    fields = PdfReader(io.BytesIO(client.get(care_url(chat), headers=anna).content)).get_fields()
    assert (fields["Fam.Name"]["/V"], fields["Geschlecht"]["/V"]) == ("Berger", "weiblich")


def test_settings_replace_a_persons_details_and_an_empty_person_is_removed(client, anna):
    client.put("/me/people/mother", json={"full_name": "Maria Berger", "sex": "female"}, headers=anna)
    client.put("/me/people/mother", json={"full_name": "Maria Berger"}, headers=anna)
    assert kept(client, anna) == {"mother": {"name": "Maria Berger"}}

    client.put("/me/people/mother", json={}, headers=anna)
    assert kept(client, anna) == {}


def test_the_users_own_row_keeps_only_details_beyond_the_profile(client, anna):
    client.put("/me/people/self", json={"full_name": "Anna Berger", "title": "Mag."}, headers=anna)

    assert kept(client, anna) == {"self": {"title": "Mag."}}
    own = next(p for p in client.get("/me/people", headers=anna).json() if p["relation"] == "self")
    assert "name" not in [e["entry"] for e in own["entries"]]


def test_unknown_relations_are_not_kept(client, anna):
    assert_error(client.put("/me/people/neighbour", json={"full_name": "X"}, headers=anna), 404)
