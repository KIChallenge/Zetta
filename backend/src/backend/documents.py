"""Discharge letters (spec section 9): text from a PDF, recommendations only with a quote that is really there."""

import asyncio
import io
import re
import sys

from pypdf import PdfReader

from backend.facts import FACTS

RECOMMENDATIONS = FACTS["documented_recommendations"].values
# A discharge letter has a few pages. A crafted PDF can make pages share one huge content stream, so the
# cost is capped by pages, by text and by time.
MAX_PAGES = 30
MAX_CHARS = 60_000
PARSE_SECONDS = 15
MAX_QUOTE = 300


def pdf_text(data: bytes) -> str:
    """Text of a text-based PDF ("" for a scanned one: photos and OCR are out of scope), at most MAX_CHARS."""
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"more than {MAX_PAGES} pages")
    parts, size = [], 0
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        size += len(parts[-1])
        if size > MAX_CHARS:
            break
    return "\n".join(parts)[:MAX_CHARS]


async def read_pdf(data: bytes) -> str:
    """pdf_text in its own process: a crafted PDF costs at most PARSE_SECONDS of one CPU and never blocks the server."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "backend.documents",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    try:
        out, _ = await asyncio.wait_for(process.communicate(data), PARSE_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ValueError("PDF took too long to read") from None
    if process.returncode:
        raise ValueError("unreadable PDF")
    return out.decode()


def _norm(text: str) -> str:
    # PDF text breaks lines and hyphenates; compare letters and digits only, case-insensitive.
    return re.sub(r"[\W_]+", "", text).casefold()


def checked(items: list[dict], text: str) -> list[dict]:
    """Items whose quote appears in the letter, one per recommendation; everything else is dropped."""
    haystack = _norm(text)
    out: dict[str, dict] = {}
    for item in items:
        quote = re.sub(r"^[•·*–-]\s*", "", item.get("quote", "").strip())  # a list item's bullet is not part of it
        if (
            item.get("recommendation") in RECOMMENDATIONS
            and 10 <= len(_norm(quote))
            and len(quote) <= MAX_QUOTE  # a quote is one sentence, not the whole letter
            and _norm(quote) in haystack
        ):
            out.setdefault(item["recommendation"], {"recommendation": item["recommendation"], "quote": quote})
    return list(out.values())


if __name__ == "__main__":  # the worker process of read_pdf: PDF on stdin, text on stdout
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))  # 1 GiB; enforced on Linux, not on macOS
    except (ImportError, ValueError, OSError):
        pass
    sys.stdout.buffer.write(pdf_text(sys.stdin.buffer.read()).encode())
