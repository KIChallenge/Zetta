"""Discharge letters (spec section 9): text from a PDF, recommendations only with a quote that is really there."""

import io
import re

from pypdf import PdfReader

from backend.facts import FACTS

RECOMMENDATIONS = FACTS["documented_recommendations"].values


def pdf_text(data: bytes) -> str:
    """Text of a text-based PDF ("" for a scanned one: photos and OCR are out of scope)."""
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _norm(text: str) -> str:
    # PDF text breaks lines and hyphenates; compare letters and digits only, case-insensitive.
    return re.sub(r"[\W_]+", "", text).casefold()


def checked(items: list[dict], text: str) -> list[dict]:
    """Items whose quote appears in the letter, one per recommendation; everything else is dropped."""
    haystack = _norm(text)
    out: dict[str, dict] = {}
    for item in items:
        quote = re.sub(r"^[•·*–-]\s*", "", item.get("quote", "").strip())  # a list item's bullet is not part of it
        if item.get("recommendation") in RECOMMENDATIONS and len(_norm(quote)) >= 10 and _norm(quote) in haystack:
            out.setdefault(item["recommendation"], {"recommendation": item["recommendation"], "quote": quote})
    return list(out.values())
