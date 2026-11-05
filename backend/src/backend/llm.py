"""The three narrow LLM calls (spec section 2): text -> facts, plan intro, scripts with placeholders.

The LLM never searches or looks anything up and never gets personal values or contact data.
"""

import json
from functools import cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from backend.config import settings
from backend.facts import extraction_schema

LANGUAGES = {
    "de": 'German (as used in Austria, addressing the user formally with "Sie")',
    "en": "English",
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
    "Write one or two short, warm sentences that introduce a plan of next steps to the user. Name the topics "
    "of the plan briefly. Do not repeat the steps. Never write phone numbers, email addresses, web addresses, "
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
    'concerned in the accusative, e.g. "meine Mutter", "meinen Vater"; you may also write the relation '
    "yourself from facts.subject, never a name.\n"
    "- Never write phone numbers, email addresses, web addresses, dates, amounts or account numbers.\n"
    "- Nothing medical: no illnesses, diagnoses, symptoms, medication or treatments.\n"
    "- {detail}"
)
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


def _format(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


class Llm:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key
        )

    async def _complete(self, system: str, user: str, response_format: dict | None = None) -> str:
        response = await self.client.chat.completions.create(
            model=settings.azure_openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            reasoning_effort="low",
            max_completion_tokens=4000,
            **({"response_format": response_format} if response_format else {}),
        )
        return response.choices[0].message.content or ""

    async def extract(self, text: str, question: str | None) -> dict:
        """Facts from one user message. `question`: the question the user is answering, if any."""
        system = EXTRACT_PROMPT + (f"\nThe user is answering this question: {question}" if question else "")
        return json.loads(await self._complete(system, text, _format("facts", extraction_schema())))

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

    async def title(self, text: str) -> str:
        return await self._complete(TITLE_PROMPT, text)


@cache
def get_llm() -> Llm:
    return Llm()


LlmClient = Annotated[Llm, Depends(get_llm)]
