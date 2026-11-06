"""The narrow LLM calls (spec section 2): text -> facts, plan intro, scripts with placeholders, and help with forms.

The LLM never searches or looks anything up and never gets profile values or contact data. What the user types
or uploads goes through `redact` first.
"""

import json
import re
from functools import cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from backend.config import settings
from backend.facts import FACTS, extraction_guide, extraction_schema

LANGUAGES = {
    "de": 'German (as used in Austria, addressing the user formally with "Sie")',
    "en": "English",
    "fr": "French",
    "cs": "Czech",
    "sk": "Slovak",
    "sl": "Slovenian",
    "tr": "Turkish",
    "bks": "Bosnian/Croatian/Serbian",
    "ro": "Romanian",
    "pl": "Polish",
    "hu": "Hungarian",
    "uk": "Ukrainian",
    "ar": "Arabic",
}
TITLE_PROMPT = (
    "Write a short title, at most 6 words, for a conversation that starts with the "
    "user's message. Use the language of the message. Reply with the title only, "
    "without quotes."
)
EXTRACT_PROMPT = (
    "You turn one message of a user into facts for a guide to social insurance and care services in Vienna, "
    "Austria. The message may be in any language, colloquial, very short or long, with typos or irrelevant "
    "details. Fill a field only if the message states it or clearly implies it; otherwise use null or an empty "
    "list. Never guess. There are no fields for illnesses, diagnoses, symptoms or medication: do not try to "
    "record them anywhere."
)
INTRO_PROMPT = (
    "Write one short, warm sentence of at most 12 words that introduces a plan of next steps to the user. "
    "Do not name the topics or the steps: they are shown right below. No filler such as \"Gerne\" or "
    "\"So sehen Sie rasch\". Never write phone numbers, email addresses, web addresses, "
    "dates, amounts or names, and say nothing medical. Never say that someone is entitled to something "
    '("Anspruch"); say what may apply. Reply with the text only. Language: {language}.'
)
SCRIPTS_PROMPT = (
    "You write short texts that a user in Vienna uses to contact an institution: speaking scripts for phone "
    "calls and emails. Write in German as used in Austria, polite and plain, in the first person (the user "
    "speaks or writes).\n"
    "For each step you get the items the text must cover (with ids), the placeholders you may use and a few "
    "facts.\n"
    "- Call: an opening (greeting, who is calling, why), exactly one point per item with its id in `covers`, "
    "and a closing. Points are what the user says on the phone: direct questions like \"Kann ich ...?\" or "
    "\"Wie ...?\", not \"Ich möchte fragen, ob ...\".\n"
    "- Email: a subject and a body that starts with \"Sehr geehrte Damen und Herren,\" and ends with "
    "\"Mit freundlichen Grüßen\". `covers` lists the ids of all items the body covers.\n"
    "- Personal data only as placeholders, exactly as given, e.g. {user.name}. {subject.relation} is the person "
    'concerned in the accusative with its possessive, e.g. "meine Mutter", "meinen Vater": write "für '
    '{subject.relation}", never "meine {subject.relation}": no possessive or article before it. You may also '
    "write the relation yourself from facts.subject, never a name.\n"
    "- Never write phone numbers, email addresses, web addresses, dates, amounts or account numbers.\n"
    "- Nothing medical: no illnesses, diagnoses, symptoms, medication or treatments.\n"
    "- {detail}"
)
LETTER_PROMPT = (
    "You read a hospital discharge letter for a guide to social insurance and care services. List only "
    "recommendations that are explicitly written in the letter and match one of the allowed values, each with "
    "an exact quote copied word for word from the letter (one sentence or list item). Ignore diagnoses, "
    "findings, lab values, medication, therapy plans and anything doctors decide among themselves: these are "
    "medical tasks and map to no value. If nothing matches, return an empty list.\nAllowed values: {values}"
)
TRANSLATE_PROMPT = (
    "You translate the German texts of a guide to social insurance and care services in Vienna, Austria, into "
    "{language}. Readers are people who may not know the Austrian system, often in a difficult situation: write "
    "plainly and politely, addressing the reader formally. Many texts are short labels of buttons, chips and form "
    "fields. A text may come with a `note` that says what it means in the app: follow it, but do not translate it.\n"
    "Terms:\n"
    "- Zetta is the name of this app. Keep \"Zetta\" as a name in every language, never translate it.\n"
    "- Bewegt im Park is the name of a programme: keep it in German.\n"
    "Translate these into {language} by their meaning, never leave the German word:\n"
    "- Kasse: a public health insurance fund. Kassenvertrag: a contract with one.\n"
    "- Wahlarzt, Wahlarztpraxis: a private doctor WITHOUT a contract with public health insurance. The patient pays "
    "first and gets part of it back. Never use a word that suggests a contract, such as French \"conventionné\".\n"
    "- Spital: hospital. Entlassung: discharge from hospital. Entlassungsbrief: discharge letter.\n"
    "- rund um die Uhr: around the clock, in words. Never use a digit the German text does not have, such as 24/7.\n"
    "Rules:\n"
    "- Return one translation per text, with the same id.\n"
    "- Keep placeholders such as {user.name} or {n} exactly as they are.\n"
    "- Never add or change phone numbers, email addresses, web addresses, dates or other numbers.\n"
    "- Keep names of institutions and abbreviations in German: ÖGK, PVA, FSW, e-card, Fonds Soziales Wien.\n"
    "- For Austrian benefits and official terms, translate the meaning and add the German term in brackets once, so "
    "the reader can use it on the phone, e.g. \"care allowance (Pflegegeld)\". Not in very short labels.\n"
    "- Add nothing else: no advice, no medical statements."
)
FORM_PROMPT = (
    "You help people in Vienna, Austria, fill in an official German application form: {form}. Readers may be old, "
    "young or disabled and find forms hard: write plainly and politely, addressing the reader formally. You get the "
    "form's questions with their ids, its own help texts and which options are chosen, never personal data. Use only "
    "these: add no rules, deadlines, amounts, names, phone numbers, email or web addresses or dates, say nothing "
    "medical and never say that someone is entitled to something. Plain text without Markdown.\n{task}"
)
FORM_TASKS = {
    "explain": "Explain the question in `question` in one to three short sentences in {language}: what it means and how "
    "to answer it. Reply with the text only.",
    "suggest": "Write a short draft answer for the free-text question `question`, in German because it goes on the "
    "German form, from the form's help texts and the chosen answers in `answers`, in at most `room` characters: the "
    "lines on paper are short. A list of items goes one per line. If something personal is needed, write a gap in "
    "square brackets, e.g. [Name]. Reply with the text only.",
    "ask": "Answer the user's question in `user_question` about this form in one to four short sentences in {language}. "
    "If the form's texts do not answer it, or it is about illness, symptoms, medication or treatment, say briefly that "
    "you cannot answer it and that `submit_to` can. Reply with the text only.",
    "check": "`filled` says which questions are answered and `answers` which options are chosen; `shown` are the hints "
    "the user already sees. Give at most three short hints in {language} that are not among them, each about one "
    "question (its id in `question`): a question still open that probably applies, or answers that do not fit "
    "together. No hints if nothing is useful.",
}
HINTS_SCHEMA = {
    "type": "object",
    "properties": {
        "hints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "text": {"type": "string"}},
                "required": ["question", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hints"],
    "additionalProperties": False,
}
DETAIL = {
    "short": "Keep it short: one sentence per point.",
    "detailed": "Each point may have a second sentence that explains the question.",
}
SCRIPTS_SCHEMA = {
    "type": "object",
    "properties": {
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "opening": {"type": "string"},
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"covers": {"type": "string"}, "text": {"type": "string"}},
                            "required": ["covers", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "closing": {"type": "string"},
                },
                "required": ["step_id", "opening", "points", "closing"],
                "additionalProperties": False,
            },
        },
        "emails": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "covers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["step_id", "subject", "body", "covers"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["calls", "emails"],
    "additionalProperties": False,
}


# Identifiers no extraction needs. Dates only in letters: in a chat message they can tell an age or a discharge day.
SVNR = re.compile(r"\b\d{4}[ /-]?\d{2}[ .]?\d{2}[ .]?\d{2}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
DATE = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.(\s?\d{2,4}\b)?")


def redact(text: str, dates: bool = False) -> str:
    """The text without social security numbers, email addresses and, with `dates`, dates (GDPR data minimisation)."""
    text = EMAIL.sub("[E-Mail]", SVNR.sub("[SV-Nummer]", text))
    return DATE.sub("[Datum]", text) if dates else text


def _format(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


class Llm:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",  # the client refuses an empty key
            # The defaults (10 minutes, 2 retries) would hold a reply and its database session open for half an hour.
            timeout=60,
            max_retries=1,
        )

    async def _complete(self, system: str, user: str, response_format: dict | None = None) -> str:
        response = await self.client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            reasoning_effort="low",
            max_completion_tokens=4000,
            extra_body=settings.llm_extra_body or None,
            **({"response_format": response_format} if response_format else {}),
        )
        return response.choices[0].message.content or ""

    async def extract(self, text: str, question: str | None, topics: dict[str, str] | None = None) -> dict:
        """Facts from one user message. `question`: the question the user is answering, if any. `topics`: the plan's."""
        system = f"{EXTRACT_PROMPT}\n\nFields:\n{extraction_guide(topics)}"
        system += f"\n\nThe user is answering this question: {question}" if question else ""
        return json.loads(await self._complete(system, text, _format("facts", extraction_schema(topics))))

    async def intro(self, plan: dict, language: str) -> str:
        return await self._complete(
            INTRO_PROMPT.format(language=LANGUAGES[language]), json.dumps(plan, ensure_ascii=False)
        )

    async def scripts(self, steps: list[dict], detail: str) -> dict[str, dict]:
        """Step id -> {"call": {...}} or {"email": {...}}, with placeholders instead of personal data."""
        data = json.loads(await self._complete(
            SCRIPTS_PROMPT.replace("{detail}", DETAIL[detail]),
            json.dumps(steps, ensure_ascii=False),
            _format("scripts", SCRIPTS_SCHEMA),
        ))  # fmt: skip
        out = {c.pop("step_id"): {"call": c} for c in data["calls"]}
        out |= {e.pop("step_id"): {"email": e} for e in data["emails"]}
        return out

    async def recommendations(self, letter: str) -> list[dict]:
        """[{recommendation, quote}] from a letter's text; the quotes are checked by documents.checked."""
        fact = FACTS["documented_recommendations"]
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "recommendation": {"type": "string", "enum": list(fact.values)},
                            "quote": {"type": "string"},
                        },
                        "required": ["recommendation", "quote"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        }
        values = "; ".join(f"{v}: {h}" for v, h in fact.hints.items())
        content = await self._complete(LETTER_PROMPT.replace("{values}", values), letter, _format("letter", schema))
        return json.loads(content)["items"]

    async def form_help(self, task: str, data: dict, language: str) -> str | list[dict]:
        """One of FORM_TASKS on the form's structure (forms.llm_form): text, or [{question, text}] for "check"."""
        system = FORM_PROMPT.replace("{form}", data["form"]).replace("{task}", FORM_TASKS[task])
        system = system.replace("{language}", LANGUAGES[language])
        content = json.dumps(data, ensure_ascii=False)
        if task == "check":
            return json.loads(await self._complete(system, content, _format("hints", HINTS_SCHEMA)))["hints"]
        return await self._complete(system, content)

    async def translate(self, texts: list[str], language: str, notes: dict[str, str]) -> list[str]:
        """For scripts/translate.py only, on public texts: the app itself never translates at runtime."""
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                        "required": ["id", "text"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        }
        content = await self._complete(
            TRANSLATE_PROMPT.replace("{language}", language),
            json.dumps(
                [{"id": i, "text": t, **({"note": notes[t]} if t in notes else {})} for i, t in enumerate(texts)],
                ensure_ascii=False,
            ),
            _format("translations", schema),
        )
        found = {item["id"]: item["text"] for item in json.loads(content)["items"]}
        return [found.get(i, "") for i in range(len(texts))]

    async def title(self, text: str) -> str:
        return await self._complete(TITLE_PROMPT, text)


@cache
def get_llm() -> Llm:
    return Llm()


LlmClient = Annotated[Llm, Depends(get_llm)]
