from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from backend.config import settings
from backend.schemas import ProfileData

SYSTEM_PROMPT = "You are a helpful assistant. You may use Markdown."
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
LENGTHS = {
    "short": "Keep your answers short: a few sentences or a short list of next steps.",
    "detailed": "Explain in detail and step by step, but without filler.",
}
TITLE_PROMPT = (
    "Write a short title, at most 6 words, for a conversation that starts with the "
    "user's message. Use the language of the message. Reply with the title only, "
    "without quotes."
)


def build_messages(profile: ProfileData, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Instructions, the user's own details (only if any are filled in), then the chat history."""
    system = (
        f"{SYSTEM_PROMPT} Always answer in {LANGUAGES[profile.answer_language]}, unless the user "
        f"explicitly asks for another language. {LENGTHS[profile.answer_length]}"
    )
    messages = [{"role": "system", "content": system}]
    svnr = profile.svnr and f"{profile.svnr[:4]} {profile.svnr[4:]}"
    place = f"{profile.postal_code} {profile.city}".strip()
    facts = [
        ("Name", profile.full_name),
        ("Address", ", ".join(part for part in (profile.street, place) if part)),
        ("Social security number", svnr),
        ("Phone", profile.phone),
        ("Email", profile.contact_email),
    ]
    if known := [f"- {label}: {value}" for label, value in facts if value]:
        messages.append({
            "role": "system",
            "content": "Known details about the user, entered by the user themselves:\n"
            + "\n".join(known)
            + "\nUse them where they help (e.g. for call scripts or emails), do not ask for them "
            "again and never invent other personal details.",
        })
    return [*messages, *history]


class Llm:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key
        )

    async def reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Stream the assistant's answer to `build_messages` output, chunk by chunk."""
        stream = await self.client.chat.completions.create(
            model=settings.azure_openai_model,
            messages=messages,
            stream=True,
            reasoning_effort="low",
            max_completion_tokens=4000,
        )
        # Closing the stream (also on Stop) ends the request to the LLM.
        async with stream:
            async for chunk in stream:
                # Azure sends chunks without choices, e.g. content filter results.
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    async def title(self, text: str) -> str:
        response = await self.client.chat.completions.create(
            model=settings.azure_openai_model,
            messages=[
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user", "content": text},
            ],
            reasoning_effort="low",
            max_completion_tokens=1000,
        )
        return response.choices[0].message.content or ""


@cache
def get_llm() -> Llm:
    return Llm()


LlmClient = Annotated[Llm, Depends(get_llm)]
