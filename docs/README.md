## Landing page

Login/registration page (JSON Web Tokens and basic registration).

## Main page

### Left sidebar

A list of chats. Each chat has:

- A title (renamable)
- A delete option
- A short status, e.g. open questions, the next step, or "nothing to do here"

Out of scope: memory.

## General philosophy

The agent turns the user's questions into concrete next steps, not walls of text.

## Workflow (summary)

1. The user asks a question.
2. The LLM converts the question into a list of facts.
3. A deterministic system keeps having the LLM ask the user clarifying questions until the system decides it has enough facts.
4. The completed fact list is processed by a second deterministic system, which works with a predefined corpus of institutions (contact information, descriptions, websites, etc.).
5. This deterministic system outputs the relevant institutions with their contact info, required documents, next steps, addresses, etc.
6. The LLM takes this list and turns it into text with contact info and next steps, displayed as cards or a graph.

## The "wow" effect

No card should be a wall of text.

Out of scope: Barrierefreiheit

### Examples

- Phone call: If it recommends calling an institution, the card already includes the hours when they take calls and a complete call script filled in with your name and personal details, covering what to ask for. It also has a button to mark the call as completed and record their response. The user doesn't have to ask for any of this.
- Email: If it recommends writing an email, the card already contains the email, pre-written with your details.

## Scope

- Vienna only, using a predefined database.
- The LLM must never hallucinate contact info, opening hours, etc.
