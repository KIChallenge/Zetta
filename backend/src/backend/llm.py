from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from backend.config import settings

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer in the language the user writes in. "
    "You may use Markdown."
)
TITLE_PROMPT = (
    "Write a short title, at most 6 words, for a conversation that starts with the "
    "user's message. Use the language of the message. Reply with the title only, "
    "without quotes."
)


class Llm:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key
        )

    async def reply(self, history: list[dict[str, str]]) -> AsyncIterator[str]:
        """Stream the assistant's answer to the chat history, chunk by chunk."""
        stream = await self.client.chat.completions.create(
            model=settings.azure_openai_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
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
