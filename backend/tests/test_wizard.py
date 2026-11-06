"""The form wizard (forms.yaml `sections`): the deterministic model, saved answers, the filled PDF and the optional
LLM help, which never sees a personal value or a part that stays on paper."""

import io
import json

import pytest
from pypdf import PdfReader
from test_chats import PROFILE, anna, assert_error, create_chat, to_plan  # noqa: F401 (anna is a fixture)

from backend import forms, scripts
from backend.routers import chats
from backend.corpus import get_corpus
from backend.facts import FACTS
from backend.schemas import ProfileData

CARE = get_corpus().forms["care_allowance_form"]
ANNA = ProfileData(**PROFILE)
MOTHER = {"full_name": "Maria Berger", "birth_date": "1948-03-12", "sex": "female"}


def pdf_states() -> dict[str, set[str]]:
    """Full field name -> the states its widgets can take (empty for a text field)."""
    found: dict[str, set[str]] = {}
    for page in PdfReader(forms.FORMS_DIR / CARE.file).pages:
        for annot in page.get("/Annots") or []:
            node, names = annot.get_object(), []
            widget = node
            while node is not None:
                if "/T" in node:
                    names.insert(0, node["/T"])
                node = node["/Parent"].get_object() if "/Parent" in node else None
            appearances = widget.get("/AP", {}).get("/N", {})
            states = set(appearances.keys()) if widget.get("/FT", "") == "/Btn" or "/Off" in appearances else set()
            found.setdefault(".".join(names), set()).update(states - {"/Off"})
    return found


def conditions(when) -> list[dict]:
    return when if isinstance(when, list) else [when] if when else []


# ---- The corpus ----


def test_every_question_names_a_real_field_and_state_of_the_pdf():
    fields = pdf_states()

    for q in CARE.questions:
        assert set(q.fields) <= set(fields), q.id
        assert not q.map or set(q.map.values()) <= fields[q.fields[0]], q.id
    assert {f for q in CARE.questions for f in q.fields} == set(fields)  # every field is accounted for


def test_question_ids_are_unique_and_never_a_fact_key():
    ids = [q.id for q in CARE.questions]

    assert len(ids) == len(set(ids))
    assert not set(ids) & set(FACTS)


def test_conditions_only_look_at_facts_and_earlier_questions():
    seen = set(FACTS)
    for section in CARE.sections:
        assert set(section.when or {}) <= set(FACTS), section.id
        for q in section.questions:
            assert all(set(c) <= seen for c in conditions(q.when)), q.id
            seen.add(q.id)
    assert all(set(c.when) <= seen for c in CARE.checks)


def test_everything_medical_the_consents_and_the_signature_stay_on_paper():
    manual = [q for q in CARE.questions if q.manual]

    assert {"Leiden", "Medikamente", "Demenz", "Spital", "Unfallhergang", "Pflegeberatung", "Datum_1"} <= {
        f for q in manual for f in q.fields
    }
    assert all(q.value is None and not q.suggest and not q.required for q in manual)
    for q in CARE.questions:
        if not q.manual:
            assert not scripts.MEDICAL.search(" ".join([q.label, *q.fields])), q.id


def test_kinds_fit_their_options_and_drafts():
    for q in CARE.questions:
        if q.kind in forms.CHOICE_KINDS:
            assert forms.options(q), q.id
            assert set(q.map) <= set(forms.options(q)), q.id
        assert not q.suggest or q.kind == "multiline", q.id


# ---- The model ----


def model(facts, answers=None, kept=None, profile=ANNA):
    return forms.wizard(CARE, profile, kept or {}, facts, answers or {})


def question(view, qid):
    return next(q for s in view["sections"] for q in s["questions"] if q["id"] == qid)


def shown(facts, answers, kept=None):
    return {r.question.id for r in forms.rows(CARE, ANNA, kept or {}, facts, answers) if r.shown}


def test_prefills_say_where_they_come_from():
    kept = {"mother": MOTHER, "self": {"title": "Mag."}}

    view = model({"subject": "mother", "pension_payer": "pv"}, {"former_names": "Huber"}, kept)

    def got(qid):
        q = question(view, qid)
        return q["value"], q["source"], q["source_label"]

    assert got("last_name") == ("Berger", "kept", None)
    assert got("sex") == ("female", "kept", None)  # the answer's code
    assert got("birth_date") == ("12.03.1948", "kept", None)
    assert got("rep_first_name") == ("Anna", "profile", None)
    assert got("rep_title") == ("Mag.", "kept", None)
    assert got("pension") == ("yes", "fact", "Pension von der PV")
    assert got("pension_office") == ("Pensionsversicherungsanstalt", "fact", "Pension von der PV")
    assert got("former_names") == ("Huber", "answer", None)
    assert got("svnr") == ("", None, None)


def test_for_themselves_the_user_is_the_person_and_nobody_applies_for_them():
    view = model({"subject": "self"})

    assert [s["id"] for s in view["sections"]] == ["person", "care", "benefits", "attachments"]
    assert (question(view, "last_name")["value"], question(view, "last_name")["source"]) == ("Berger", "profile")
    assert question(view, "svnr")["value"] == "1237010180"


def test_questions_show_only_for_the_answers_they_depend_on():
    facts = {"subject": "mother"}

    assert {"similar_benefit_applied", "similar_benefit_kind"} <= shown(facts, {"similar_benefit": "no", "similar_benefit_applied": "yes"})
    assert "similar_benefit_kind" in shown(facts, {"similar_benefit": "yes"})  # either of the two
    assert "similar_benefit_kind" not in shown(facts, {"similar_benefit": "no", "similar_benefit_applied": "no"})
    assert "carers" not in shown(facts, {"care_by_others": "no", "carers": "yes"})
    assert "other_citizenship" not in shown(facts, {})
    assert "other_citizenship" in shown(facts, {}, {"mother": {"citizenship": "other"}})  # from a kept detail
    assert "payout" in shown(facts, {"pension": "no"})


def test_open_required_questions_and_the_forms_checks_are_the_findings():
    view = model({"subject": "mother", "pension_payer": "pv"}, {"pension": "no", "care_by_others": "yes", "proof": "attached"})

    missing = [f["question"] for f in view["findings"] if f["kind"] == "missing"]
    hints = [f["text"] for f in view["findings"] if f["kind"] == "check"]
    assert {"svnr", "application_type", "pension_applied", "similar_benefit"} <= set(missing)
    assert "proof" not in missing  # answered, though only asked once a role is chosen
    assert hints == [
        "Im Gespräch haben Sie eine Pension genannt, bei Punkt 8 steht aber „nein“.",
        "Bei Punkt 4 steht „ja“. Kreuzen Sie bitte auch an, wer hilft.",
    ]  # proof only counts while asked: no role, no hint
    assert "Bei Punkt 4 steht „ja“. Kreuzen Sie bitte auch an, wer hilft." not in [
        f.get("text") for f in model({"subject": "mother"}, {"care_by_others": "yes", "carers": "yes"})["findings"]
    ]


def test_the_paper_parts_are_listed_but_never_asked():
    view = model({"subject": "mother"})

    asked = {q["id"] for s in view["sections"] for q in s["questions"]}
    assert not asked & {q.id for q in CARE.questions if q.manual}
    assert {"label": "Unterschrift", "page": 4, "point": 11} in view["manual"]
    assert len(view["manual"]) == 8


@pytest.mark.parametrize(
    ("value", "limits", "expected"),
    [
        ("kurz", [10], ["kurz"]),
        ("zu lang für eins", [10], None),
        ("Anna Berger\nFavoritenstraße 1", [12, 24], ["Anna Berger,", "Favoritenstraße 1"]),
        ("eins zwei drei vier", [9, 9], ["eins zwei", "drei vier"]),
        ("eins zwei drei vier fünf", [9, 9], None),
        ("Wort", [None, 5], ["Wort"]),
    ],
)
def test_long_answers_are_split_over_the_lines_of_the_form_or_refused(value, limits, expected):
    assert forms.lines(value, limits) == expected


# ---- The API ----


def url(chat, part=""):
    return f"/chats/{chat['id']}/steps/care_allowance.submit/form{part}"


@pytest.fixture
def chat(client, anna, llm):  # noqa: F811 (anna is a fixture)
    client.put("/me/profile", json=PROFILE, headers=anna)
    client.put("/me/people/mother", json=MOTHER, headers=anna)
    created = create_chat(client, anna)
    to_plan(client, anna, llm, created["id"])
    return created


def save(client, headers, chat, answers):
    return client.put(url(chat, "/answers"), json={"answers": answers}, headers=headers)


@pytest.mark.parametrize(
    "answer",
    [
        {"svnr": "1234567890"},  # wrong check digit
        {"birth_date": "31.02.1948"},
        {"marital_status_since": "2024-01-01"},
        {"postal_code": "11000"},
        {"email": "keine-adresse"},
        {"pension": "vielleicht"},
        {"former_names": "x" * 31},  # the field takes 30
        {"conditions": "Demenz"},  # on paper only
        {"nope": "x"},
    ],
)
def test_answers_are_checked(client, anna, chat, answer):  # noqa: F811
    assert_error(save(client, anna, chat, answer), 422, f"invalid:{next(iter(answer))}")


def test_answers_are_saved_and_the_wizard_resumes(client, anna, chat):  # noqa: F811
    response = save(client, anna, chat, {"svnr": "1237 010180", "application_type": "new", "last_name": "Berger"})

    assert response.status_code == 200
    view = client.get(url(chat, "/wizard"), headers=anna).json()
    assert (question(view, "svnr")["value"], question(view, "svnr")["source"]) == ("1237010180", "answer")
    assert question(view, "application_type")["value"] == "new"
    assert question(view, "last_name")["source"] == "kept"  # the same as kept: the kept details stay its source
    assert view["form"]["title"] == "Antrag auf Pflegegeld (PAL 080)"
    assert view["subject"] == "Mutter"
    assert view["submit_to"]["address"] == "Friedrich-Hillegeist-Straße 1, 1020 Wien"

    cleared = save(client, anna, chat, {"application_type": ""}).json()
    assert (question(cleared, "application_type")["value"], question(cleared, "svnr")["value"]) == ("", "1237010180")
    plan = client.get(f"/chats/{chat['id']}/state", headers=anna).json()["plan"]
    assert next(s for s in plan["steps"] if s["id"] == "care_allowance.submit")["form"]["wizard"]["done"] == 8


def test_another_users_chat_has_no_wizard(client, anna, chat):  # noqa: F811
    from test_chats import register

    bob = register(client, "bob")

    assert_error(client.get(url(chat, "/wizard"), headers=bob), 404)
    assert_error(save(client, bob, chat, {"application_type": "new"}), 404)
    # A form card without a wizard.
    assert_error(client.get(f"/chats/{chat['id']}/steps/home_care_fsw.send_application/form/wizard", headers=anna), 404)


def test_the_pdf_has_the_answers_and_leaves_the_paper_parts_blank(client, anna, chat):  # noqa: F811
    save(client, anna, chat, {
        "svnr": "1237010180", "application_type": "increase", "care_by_others": "yes", "carers": "yes",
        "carer_names": "Anna Berger\nFavoritenstraße 1, 1100 Wien", "pension": "no", "payout": "cash",
        "similar_benefit": "no", "hospice_from": "01.01.2026",  # hidden: hospice leave is not "ja"
    })  # fmt: skip

    fields = PdfReader(io.BytesIO(client.get(url(chat), headers=anna).content)).get_fields()
    values = {name: f.get("/V") for name, f in fields.items() if f.get("/V") not in (None, "", "/Off")}

    assert values["VSNR_1"] == "1237010180"
    assert values["Antrag Pflg"] == "/02"
    assert values["Betreuung durch andere Person"] == "/02"
    assert values["Person Stelle Pflegeperson"] == "/ja"
    assert [values[f"Name und Adresse Pflegeperson{n}"] for n in ("", "2", "3")] == ["Anna Berger,", "Favoritenstraße 1, 1100", "Wien"]
    assert (values["ausländische Pension"], values["Anweisung"], values["andere Leistung"]) == ("/01", "/02", "/01")
    assert (values["Fam.Name"], values["Familienname andere"]) == ("Berger", "Berger")
    assert "Familienhospiz seit" not in values
    assert not {f for q in CARE.questions if q.manual for f in q.fields} & set(values)


def test_typed_details_are_kept_for_the_next_forms_only_when_asked(client, anna, chat):  # noqa: F811
    save(client, anna, chat, {"svnr": "1237010180", "first_name": "Maria Theresia", "rep_phone": "0664 7654321"})

    def mother():
        people = client.get("/me/people", headers=anna).json()
        return {e["entry"]: e["values"] for e in next(p for p in people if p["relation"] == "mother")["entries"]}

    client.post(url(chat), json={"remember": False}, headers=anna)
    assert (mother()["svnr"], mother()["name"]) == ({"svnr": ""}, {"full_name": "Maria Berger"})
    assert client.get("/me/profile", headers=anna).json()["phone"] == "0660 1234567"

    response = client.post(url(chat), json={"remember": True}, headers=anna)

    assert response.status_code == 200
    assert (mother()["svnr"], mother()["name"]) == ({"svnr": "1237010180"}, {"full_name": "Maria Theresia Berger"})
    assert client.get("/me/profile", headers=anna).json()["phone"] == "0664 7654321"


# ---- The optional LLM layer ----


@pytest.fixture(autouse=True)
def no_cached_explanations():
    chats.EXPLAINED.clear()


def ask(client, headers, chat, kind, **body):
    return client.post(url(chat, "/help"), json={"kind": kind, **body}, headers=headers)


def test_the_llm_never_sees_a_personal_value_or_a_paper_part(client, anna, chat, llm):  # noqa: F811
    save(client, anna, chat, {
        "svnr": "1237010180", "former_names": "Moser", "carer_names": "Berta Huber", "care_by_others": "yes",
        "carers": "yes", "temporary_address": "Pflegeheim Sonnenhof",
    })  # fmt: skip
    llm.hints = [{"question": "eu_care_benefit", "text": "Punkt 7 ist noch offen."}]

    assert ask(client, anna, chat, "explain", question="similar_benefit").json() == {"text": llm.form_text}
    assert ask(client, anna, chat, "suggest", question="attachments").json() == {"text": llm.form_text}
    assert ask(client, anna, chat, "ask", text="Was ist ein Kostenträger? Meine Nummer ist 1237 010180.").json() == {"text": llm.form_text}
    assert ask(client, anna, chat, "check").json() == {
        "hints": [{"question": "eu_care_benefit", "section": "benefits", "text": "Punkt 7 ist noch offen."}]
    }

    calls = [value for method, value in llm.calls if method == "form_help"]
    assert [c["task"] for c in calls] == ["explain", "suggest", "ask", "check"]
    sent = json.dumps(calls, ensure_ascii=False)
    for value in ("Anna", "Berger", "Maria", "1237", "010180", "anna@example.at", "Favoritenstraße", "0660", "1948",
                  "Moser", "Huber", "Sonnenhof", "weiblich", "female"):  # fmt: skip
        assert value not in sent, value
    for q in CARE.questions:
        if q.manual:
            assert f'"id": "{q.id}"' not in sent and q.label not in sent, q.id
    assert not scripts.MEDICAL.search(sent)
    assert calls[3]["answers"] == {"care_by_others": "yes", "carers": "yes", "pension": "yes"}
    assert calls[3]["filled"]["svnr"] is True
    assert "Für wen: Mutter" in calls[1]["facts"]


def test_explanations_are_asked_once_per_question_and_language(client, anna, chat, llm):  # noqa: F811
    ask(client, anna, chat, "explain", question="pension")
    ask(client, anna, chat, "explain", question="pension")

    assert [m for m, _ in llm.calls].count("form_help") == 1


def test_a_medical_question_is_not_answered_and_not_sent(client, anna, chat, llm):  # noqa: F811
    assert ask(client, anna, chat, "ask", text="Muss ich die Demenz meiner Mutter angeben?").json() == {"refused": True}
    assert "form_help" not in [m for m, _ in llm.calls]


def test_drafts_only_for_questions_that_allow_them(client, anna, chat):  # noqa: F811
    assert_error(ask(client, anna, chat, "suggest", question="former_names"), 422)
    assert_error(ask(client, anna, chat, "explain", question="conditions"), 422)  # on paper only


def test_without_the_llm_the_wizard_still_works(client, anna, chat, llm):  # noqa: F811
    llm.fail = True

    for kind, body in [("explain", {"question": "pension"}), ("suggest", {"question": "attachments"}),
                       ("ask", {"text": "Was heißt Kostenträger?"}), ("check", {})]:  # fmt: skip
        assert_error(ask(client, anna, chat, kind, **body), 503, "Not available")
    assert client.get(url(chat, "/wizard"), headers=anna).status_code == 200
    assert save(client, anna, chat, {"application_type": "new"}).status_code == 200
    assert client.get(url(chat), headers=anna).status_code == 200


@pytest.mark.parametrize(
    "text",
    ["Rufen Sie unter 0800 123456 an.", "Mehr auf www.pv.at.", "Sie bekommen 200 Euro.", "Fragen Sie {user.name}.",
     "Bei Schmerzen kreuzen Sie ja an.", "", "Kopien " * 30],
)  # fmt: skip
def test_llm_text_with_contact_data_amounts_or_medical_words_is_not_shown(client, anna, chat, llm, text):  # noqa: F811
    llm.form_text = text

    assert_error(ask(client, anna, chat, "suggest", question="attachments"), 503)


def test_llm_hints_about_unknown_questions_or_with_contact_data_are_dropped(client, anna, chat, llm):  # noqa: F811
    llm.hints = [
        {"question": "conditions", "text": "Tragen Sie die Krankheiten ein."},
        {"question": "nope", "text": "Hallo."},
        {"question": "similar_benefit", "text": "Schreiben Sie an info@pv.at."},
        {"question": "pension", "text": "Passt."},
    ]

    assert ask(client, anna, chat, "check").json() == {"hints": [{"question": "pension", "section": "benefits", "text": "Passt."}]}
