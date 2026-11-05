"""Bring frontend/src/locales/*.json up to date with the German texts. Run after changing a text:

    uv run scripts/translate.py

Only missing texts go to the LLM, and only public texts: no personal data, no chats. Translations that break the
rules in backend.translations are retried, then left out, so the frontend shows the German text instead.
"""

import asyncio
import json
import sys

from backend.llm import Llm
from backend.translations import LANGUAGES, LOCALES_DIR, all_sources, problems

MAX_BATCH_CHARS = 3000
# Short labels mean nothing without knowing where they appear.
RELATION = "Object of \"for\" inside a sentence, in the accusative case: I am calling for this person."
NOTES = {
    "Etwas": "Amount of help someone needs in daily life: some help.",
    "Viel": "Amount of help someone needs in daily life: a lot of help.",
    "Keine": "Amount of help someone needs in daily life: none.",
    "Egal": "Preferred time for an appointment: any time is fine.",
    "Haut": "Medical specialty: dermatology.",
    "Augen": "Medical specialty: ophthalmology.",
    "Hals-Nasen-Ohren": "Medical specialty: ear, nose and throat.",
    "Normal": "Font size: normal.",
    "Groß": "Font size: large.",
    "Sehr groß": "Font size: very large.",
    "Hell": "Colour theme: light.",
    "Dunkel": "Colour theme: dark.",
    "Standard": "Display contrast: standard.",
    "Stark": "Display contrast: high.",
    "An": "Email header: To.",
    "Betreff": "Email header: Subject.",
    "Anhang": "Email header: Attachment.",
    "Mehr": "Button that shows more details.",
    "Stand": "Followed by a date: data as of.",
    "Liste": "View of a plan as a list.",
    "Übersicht": "View of a plan as an overview.",
    "Offen": "Status of a task: open.",
    "Danach": "Status of a task: comes later.",
    "Läuft gerade": "Status of a task: in progress.",
    "Jetzt dran": "Status of a task: it is your turn now.",
    "Erledigt": "Status of a task: done.",
    "Übersprungen": "Status of a task: skipped.",
    "Alter": "Form field: the age of a person.",
    "Ort": "Form field: town or city.",
    "Person": "Settings section heading: personal details.",
    "Kontakt": "Settings section heading: contact details.",
    "Sicherheit": "Settings section heading: account security (password, deleting the account).",
    "Erste 4 Ziffern": "Form field: the first 4 digits of the Austrian social security number.",
    "TT.MM.JJJJ": "Placeholder for a date: day.month.year with 2, 2 and 4 digits, in the local notation.",
    "Nicht gespeichert": "Status: changes are not saved yet.",
    "Besuch": "Topic: visiting someone in hospital.",
    "Entlassung": "Topic: discharge from hospital.",
    "Anrufen": "Type of task: a phone call. Not a command.",
    "Antrag": "Type of task: an application form.",
    "Stimmt so": "Answer: yes, that is correct.",
    "Weiter": "Button: continue.",
    "mich": RELATION,
    "meine Mutter": RELATION,
    "meinen Vater": RELATION,
    "meine Partnerin bzw. meinen Partner": RELATION,
    "mein Kind": RELATION,
    "eine Angehörige bzw. einen Angehörigen": RELATION,
    "die betroffene Person": RELATION,
}
ROUNDS = 3


def batches(texts: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    size = 0
    for text in texts:
        if out[-1] and size + len(text) > MAX_BATCH_CHARS:
            out.append([])
            size = 0
        out[-1].append(text)
        size += len(text)
    return out


async def translate(llm: Llm, code: str, sources: list[str], limit: asyncio.Semaphore) -> dict[str, str]:
    async def one(batch: list[str]) -> dict[str, str]:
        async with limit:
            try:
                return {s: t for s, t in zip(batch, await llm.translate(batch, LANGUAGES[code], NOTES)) if not problems(s, t, code)}
            except Exception as e:
                print(f"{code}: a batch failed: {e}", file=sys.stderr)
                return {}

    found: dict[str, str] = {}
    pending = sources
    for _ in range(ROUNDS):
        if not pending:
            break
        for part in await asyncio.gather(*map(one, batches(pending))):
            found |= part
        pending = [s for s in pending if s not in found]
    return found


async def main() -> int:
    llm, sources, missing = Llm(), all_sources(), 0
    limit = asyncio.Semaphore(6)
    LOCALES_DIR.mkdir(exist_ok=True)
    for code in LANGUAGES:
        path = LOCALES_DIR / f"{code}.json"
        known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        known = {s: t for s, t in known.items() if s in sources and not problems(s, t, code)}
        todo = sorted(sources - set(known))
        known |= await translate(llm, code, todo, limit)
        left = sorted(sources - set(known))
        path.write_text(json.dumps(dict(sorted(known.items())), ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"{code}: {len(known)} of {len(sources)} texts, {len(todo)} new")
        for text in left:
            print(f"  missing: {text[:100]}", file=sys.stderr)
        missing += len(left)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
