# Zetta: From a question to the next step

Zetta helps people in Vienna navigate health, care and social insurance services. It turns a situation described in everyday language into concrete next steps: whom to contact, what to say, which documents to prepare and which form to complete.

## Example Use Cases

- Ich brauche einen Termin bei einer Hautärztin in Wien-Neubau, am liebsten vormittags. Es geht um eine Vorsorgeuntersuchung.
- Meine Mutter (82, Wien) kommt nach einem Sturz zu Hause kaum noch allein zurecht, wie beantrage ich Pflegegeld für sie?
- Ich möchte Pflegegeld für meine Mutter beantragen.

## Core points

### Privacy

- **Personal details are filled in after generation.** For call scripts and emails, the language model writes placeholders such as `{user.name}`. The backend inserts profile details afterwards, so profile names, addresses and social security numbers do not need to reach the model.
- **Less sensitive data goes into prompts.** Free text is filtered for social security numbers and email addresses before reaching the model. Dates are also filtered from uploaded letters. This is partial redaction, not full anonymisation: other personal details in a message or letter may still reach the configured model server.
- **Local model hosting is supported.** Zetta can connect to a local model through an OpenAI-compatible server instead of the default Azure endpoint. This allows model inference to stay within the operator's own infrastructure. The chosen model and server must support the structured outputs Zetta needs; compatibility and answer quality must be checked for that deployment.

Local inference is a practical option, not a promise that every deployment is private by default. For example, [Ollama documents a local OpenAI-compatible endpoint](https://docs.ollama.com/api/openai-compatibility). Zetta's privacy also depends on application hosting, storage, network security and the operator's configuration.

### Strong focus on preventing AI hallucination

**The language model handles language. A deterministic system selects services and builds the plan.** The model never searches the web, queries the institution database or decides which institution is responsible.

1. The model converts a message into facts from a closed schema. Unsupported keys and values are rejected.
2. Explicit rules select relevant services, identify missing information and choose the next question.
3. The system builds the plan from a predefined corpus. Contact details, opening hours, addresses, required documents and forms come from that corpus, not model memory.
4. The model drafts call scripts and emails using placeholders. Checks reject forbidden contact details, dates, amounts, medical wording and unknown placeholders. Invalid drafts are replaced with corpus-authored templates.

The data itself is checked too: automated tests cover references, source links, verification dates and step dependencies. Recommendations extracted from a letter must include a supporting quote that the system can match against the document. A matching quote supports traceability; it does not prove the model interpreted the passage correctly.

These safeguards address a recognised limitation: generative models can confidently produce false information, described as confabulation in the [NIST Generative AI Profile, section 2.2](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf). Zetta reduces opportunities for this failure through a narrow model role, validation and fallback text. It does not claim zero hallucinations.

### Being honest about limits

- **Vienna and the curated corpus define the scope.** Zetta cannot discover services outside its dataset. Source links and verification dates make the information traceable, but records still need maintenance.
- **Guidance is not an official decision.** A service may come into question; the responsible institution decides entitlement. Zetta does not diagnose, recommend treatment or assess a person's care needs medically.
- **Missing information stays visible.** The system asks focused questions, offers an "I don't know" answer and leaves gaps for missing personal details. Users can inspect and correct the facts it understood.
- **Opening hours are not appointment availability.** A morning preference can help rank practices by their recorded hours. It does not confirm a free appointment or make a booking.
- **The user stays in control.** Zetta prepares scripts, email drafts and filled forms. Users review them, make contact and submit applications themselves.

## What the user gets

A short plan with a clear current step, ready-to-use call scripts and email drafts, document checklists and guided forms. Completed steps and recorded outcomes show what to do next. The aim is to help someone act, without making them work through a wall of text.

## Project references

- [Product scope](README.md)
- [Response system and safeguards](response-system.md)
- [Implementation overview](../README.md#how-it-works)
- [Model configuration](../backend/.env.example)
- [Security review and deployment considerations](security-review.md)
