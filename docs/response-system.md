# Response system spec

Status: draft. Scope: Use Case 1 "SV KI-Lotse" of the KI Challenge, Vienna only.

This spec covers how a user's message becomes a plan of concrete next steps (calls, emails, forms, visits) shown as a graph the user checks off step by step. It refines the workflow in `README.md`.

All institution names, responsibilities and eligibility rules mentioned in the scenarios below are placeholders until they are curated from the sources listed in the challenge PDF. None of them is verified.

## 1. Goals

1. Turn a vague situation ("Meine Mutter braucht jetzt Hilfe") into a short list of relevant services and a step graph.
2. Every step is directly actionable: a call step has the number, the call hours and a ready speaking script; an email step has the recipient and a ready email; a form step has the form and the fields that can be prefilled.
3. The user checks steps off, records outcomes, and the graph shows what is open next. The chat sidebar shows the open step count.
4. No contact data, hours, addresses, documents or eligibility rules come from the LLM. They come from the curated corpus.
5. No medical advice (see section 10).

## 2. Responsibility split

| Task | Done by | Notes |
|---|---|---|
| Text -> facts | LLM | Structured output against a closed schema |
| Validate and merge facts | Deterministic | Enum and range checks, explicit user edits win |
| Decide which services are relevant | Deterministic | Triggers in the corpus |
| Decide which question to ask next | Deterministic | Missing required facts |
| Eligibility (administrative only) | Deterministic | Three-state: likely, possible, not |
| Build the step graph | Deterministic | Step templates in the corpus |
| Contact data, hours, address, documents | Deterministic | From the corpus only |
| Phrase a question in the user's language | LLM | Based on a prewritten question |
| Write the speaking script and email text | LLM | Placeholders only, validated, corpus fallback |
| Short intro text for a plan | LLM | One sentence, no data, no topic list |
| Extract recommendations from an uploaded letter | LLM | Must quote, quote is checked |

The LLM never searches, queries or looks anything up. It receives exactly the data the deterministic system hands it.

## 3. Pipeline per turn

```
user message / chip answer / upload
        |
        v
[LLM] extract facts            (skipped for chip answers)
        |
        v
[det] validate, merge into chat facts
        |
        v
[det] engine.evaluate(facts, corpus)
        |-- boundary hit   -> fixed boundary card (section 10)
        |-- no match       -> fixed general contact card
        |-- missing facts  -> question (prewritten text + chips)
        '-- complete       -> plan (services + step graph)
                 |
                 v
        [LLM] write scripts/emails per step (placeholders only)
                 |
                 v
        [det] validate scripts, fill placeholders, fall back to corpus template on failure
        |
        v
SSE events to the frontend: facts, question | plan
```

A turn runs at most three LLM calls: extraction, question phrasing or plan intro, and one batched script call for all steps that need text.

## 4. Fact schema

A closed set of keys with typed values. The LLM extraction uses JSON-schema structured output generated from this schema, so it cannot emit unknown keys or values. Unknown stays `null`.

Rules:

- Every fact key must be required or used by at least one service, question or template. A corpus test enforces this, so the schema cannot grow without a reason.
- No key for diagnoses, symptoms, findings, medications or risks. This is the structural part of the medical boundary.
- Each fact stores its source: `user_text`, `chip`, `document` (with quote) or `profile`. User edits always win over extraction.
- "Weiß nicht" and "möchte ich nicht sagen" are valid values for every question, so the question loop always ends.

Initial keys (to be finalized with the corpus):

| Key | Type | Example values |
|---|---|---|
| `subject` | enum | self, parent, partner, child, other_relative |
| `subject_age_band` | enum | 0-5, 6-14, 15-17, 18-39, 40-64, 65+ |
| `district` | enum | 1010 ... 1230, outside_vienna |
| `insurer` | enum | oegk, bvaeb, svs, unknown |
| `employment_status` | enum | employed, self_employed, retired, unemployed, child_coinsured |
| `lives_alone` | bool | |
| `needs_daily_help` | enum | none, some, a_lot (as reported, not assessed) |
| `recent_hospital_stay` | bool | |
| `documented_recommendations` | list of enum | outpatient_rehab, inpatient_rehab, follow_up_check, medical_aid, home_nursing, home_help, transport_to_treatment, nutrition_counselling |
| `goal` | list of enum | apply_care_allowance, find_support_services, prevention, exercise, nutrition, vaccination, doctor_appointment, child_offers, after_hospital |
| `interests` | list of enum | exercise, nutrition, stress, screening, vaccination |
| `appointment_reason` | enum | check_up, prevention, follow_up, acute (acute -> boundary card) |
| `specialty` | enum | fixed list from the corpus, chosen by the user, never derived from symptoms |
| `preferred_time` | enum | morning, afternoon, any |
| `near_home` | bool | |
| `family_history` | list of enum | only categories that appear in a corpus screening rule (section 12.2) |
| `language` | enum | de, de_simple, en, ... |
| `detail_level` | enum | short, detailed |

Profile data (name, phone, email, optional SV number) lives on the user record and is only ever inserted into scripts as placeholders (section 8).

## 5. Corpus

Read-only, curated data. Recommendation: YAML files in `backend/corpus/`, reviewed through git, validated by pydantic at startup and by tests. Per-chat state lives in the database. This is an open decision (section 18).

### 5.1 Entities

**Institution**

- `id`, `name`, `kind` (insurer, authority, counselling, provider, ...)
- `address`, `district`, `geo` (optional)
- `channels`: list of `{type: phone|email|web_form|visit, value, hours, notes}`
- `hours` are structured: `[{days: [mon..fri], from: "08:00", to: "14:00"}]` plus `closed_on` exceptions
- `online_booking_url` (optional)
- `source_url`, `verified_at`

**Service** (Leistung)

- `id`, `area` (A-F from the PDF), `title`, `summary` (short, plain German, plus simple-German variant)
- `triggers`: facts that make it a candidate, e.g. `goal contains apply_care_allowance` or `subject in [parent] and needs_daily_help in [some, a_lot]`
- `requires`: fact keys needed before a plan can be built
- `responsible`: rules mapping facts to an institution id (e.g. by `insurer` or `employment_status`)
- `criteria`: administrative conditions with three-state evaluation, plus `checked_by` text for conditions the system does not evaluate (e.g. "Pflegebedarf wird bei der Begutachtung festgestellt")
- `documents`: list of document ids
- `forms`: list of form ids
- `steps`: list of step templates (section 6)
- `why`: optional short explanation of the benefit, with `source_url` (PDF section 3.4)
- `available`: optional date ranges (seasonal offers such as "Bewegt im Park"); the engine drops the service outside them
- `source_url`, `verified_at`

**StepTemplate**

- `id` (stable, e.g. `care_allowance.apply_call`)
- `type`: call, email, form, visit, upload, book, wait, info
- `institution`: id or `responsible` reference
- `after`: step ids that must be done first
- `must_ask` (call) or `must_include` (email): list of `{id, text}` items the script has to cover
- `outcomes`: small fixed list, e.g. `[appointment_made, documents_requested, not_reached, rejected]`, each with an effect (section 7.3)
- `fallback_script`: corpus-authored text with placeholders, used when LLM output fails validation
- `slots`: placeholders the step may use

**Document**: `id`, `title`, `where_to_get`, `notes`.

**Form**: `id`, `title`, `url` or file in `SV-Box`, `field_map` (fact or profile key -> form field), `submit_to` institution id.

**Question**: `fact_key`, `text_de`, `text_de_simple`, `chips` (value + label), `why_we_ask` (one line shown under the question).

### 5.2 Corpus checks (tests, run in CI)

- Every reference resolves (institution, document, form, step, fact key).
- Every phone channel has structured hours.
- Every record has `source_url` and `verified_at`; records older than a configurable age fail a test (forces re-verification before a demo).
- Every step template's `fallback_script` uses only its declared slots, and covers all `must_ask` items.
- Every `requires` key has a `Question`.
- Every fact key is used somewhere.
- Step graphs per service are acyclic.
- No phone number, email or URL appears in free-text fields (`summary`, `why`, scripts); they must come from `channels`.

## 6. Engine

Pure functions over `(facts, corpus)`. No I/O, no LLM. This is the part that is unit tested hardest.

### 6.1 Candidate selection

1. Boundary check first (section 10).
2. `district == outside_vienna` -> out-of-scope card.
3. Candidates = services whose triggers match.
4. No candidates -> general contact card (e.g. the insurer's customer service from the corpus).

### 6.2 Next question

- Missing = union of `requires` of all candidates minus known facts.
- Pick the missing fact that the most candidates need; ties broken by a fixed priority in the corpus.
- Ask exactly one question per turn, with chips. A chip answer sets the fact directly, no LLM call.
- Hard cap: after N questions (proposed 4) build the plan with what is known; unresolved parts become `possible` with the open criterion shown.
- Facts that are only needed for one step (e.g. the user's SV number for a form) are asked in the step, not in the question loop.

### 6.3 Eligibility

Per criterion: `met`, `not_met`, `unknown`. Per service:

- any `not_met` -> service is dropped, with a one-line reason the user can see ("Gilt nur für Personen mit Wohnsitz in Wien")
- all `met` -> `likely`
- otherwise -> `possible`, with the unknown criteria listed

Wording rule: the UI never says "Sie haben Anspruch". It says "Kommt in Frage" and lists conditions, plus `checked_by` for conditions the institution assesses.

### 6.4 Plan construction

1. Take the step templates of all remaining services.
2. Resolve `institution` via `responsible` rules.
3. Merge shared steps: identical document collection steps become one "Unterlagen sammeln" step with a merged checklist.
4. Build the DAG from `after` edges. Steps with no open predecessors are `available`, others `blocked`.
5. Order: by service priority, then topological order.
6. Step ids are stable (`service_id.template_id`), so a re-plan after a fact change keeps the user's step states.

## 7. Step graph

### 7.1 Step types and what a step card contains

Every card starts collapsed and shows: title (one line), institution or result (one line), status, and the step's main action if it can be done now (call, open the email, form, link, done). Why, script, email text, hours and the rest of the table below open on demand. No card is a wall of text.

| Type | Card content | Actions |
|---|---|---|
| call | number, call hours, "jetzt erreichbar" / "ab Mo 08:00", speaking script, "have ready" list | call link (`tel:`), done, record outcome |
| email | recipient, subject, body, attachments to add | open in mail client (`mailto:`), copy, done |
| form | form link, prefilled fields, missing fields, where to send it | download, done |
| visit | address, opening hours, what to bring | map link, done |
| upload | what to upload and why (e.g. discharge letter) | upload |
| book | online booking link from the corpus, or a call step as fallback | open link, done |
| wait | what happens next and roughly when (from the corpus) | "received answer", record outcome |
| info | short explanation with source | mark as read |

### 7.2 States

`blocked` -> `available` -> `done` | `skipped`. A done step can be reopened.

### 7.3 Outcomes

Call and wait steps have a fixed outcome list from the corpus. An outcome can:

- mark the step done
- unlock or skip specific steps in the same service (e.g. `not_reached` keeps the step available and shows the next call window)
- set a fact (e.g. `appointment_made` -> stores date and time the user entered)
- trigger a re-plan

Outcomes never create steps that are not in the corpus. Free text notes are stored but not interpreted by the system.

### 7.4 Rendering

- Desktop: graph view, one column per service, edges for `after`. Mobile: vertical list grouped by service, with blocked steps greyed out.
- The graph is part of the chat, under the assistant message that produced it; the latest plan is pinned at the top of the chat.
- Sidebar status is computed: "3 offene Schritte", "Wartet auf Bescheid", "Erledigt".
- Library choice for the graph view is an open decision. A plain CSS column layout may be enough for the expected 3-12 steps.

## 8. Script and email generation

The user wants the AI to write the speaking scripts and emails. That is the main place where the LLM produces content the user acts on, so it is the most constrained part.

### 8.1 Input to the LLM

Per step, batched in one call:

- step type, service title, institution name (name only, no contact data)
- `must_ask` / `must_include` items with ids
- allowed placeholders, e.g. `{user.name}`, `{subject.relation}`, `{subject.name}`, `{user.svnr}`, `{subject.svnr}`, `{user.phone}`, `{doc.quote}`
- relevant non-personal facts (e.g. `subject=parent`, `goal=apply_care_allowance`)
- language and detail level

Personal values are never sent. The LLM writes `{user.name}`, the backend fills it in. This keeps personal data out of the LLM and makes the output checkable.

### 8.2 Output

Structured:

```json
{
  "call": {
    "opening": "Guten Tag, mein Name ist {user.name}. Ich rufe für meine Mutter, {subject.name}, an.",
    "points": [
      {"covers": "ask_form", "text": "Ich möchte Pflegegeld für sie beantragen. Wie bekomme ich den Antrag?"},
      {"covers": "ask_phone_application", "text": "Kann ich den Antrag auch telefonisch stellen?"}
    ],
    "closing": "Vielen Dank. Darf ich mir Ihren Namen notieren?"
  }
}
```

Email output: `subject`, `body`, `covers` list.

### 8.3 Validation (deterministic)

Reject the output if any of these holds:

- a `must_ask` / `must_include` id is not in `covers`
- an unknown placeholder is used
- it contains a phone number, email address, URL, IBAN, date or amount (regex); these only come from data
- it contains a term from a medical blocklist (diagnosis and medication wording)
- it exceeds the length limit for the step type

On rejection: retry once, then use the step's `fallback_script` from the corpus. The user always gets a script. Validation failures are logged for corpus and prompt work.

### 8.4 Filling

After validation the backend fills placeholders from profile and facts. A placeholder without a value renders as a visible gap, e.g. `[SV-Nummer Ihrer Mutter]`, plus a "have ready" item on the card.

### 8.5 Caching

Scripts are generated once per step and plan version and stored. They are regenerated only when facts used by that step change, or when the user presses "neu formulieren".

## 9. Document upload (scenario 3)

1. User uploads a PDF or photo. Text is taken from the PDF, or via OCR/vision for photos (provider decision open).
2. LLM extracts only explicitly written recommendations: `[{recommendation: enum, quote: "..."}]`. It is told to ignore diagnoses and findings.
3. Deterministic check: the quote must appear in the document text (normalized whitespace and case). Otherwise the item is dropped.
4. The user sees the quotes and confirms them ("In Ihrem Brief steht: '...' Stimmt das?"). Confirmed items become `documented_recommendations` with source `document`.
5. The engine treats them like any other fact.
6. The document text itself is not stored beyond the chat; only confirmed quotes are kept.

Not allowed in output: "Aufgrund Ihrer Diagnose benötigen Sie ...". Allowed: "In Ihrem Entlassungsbrief wird eine ambulante Rehabilitation empfohlen."

## 10. Medical boundary

- The extraction schema has an `intent` field with a value `medical_question` (symptoms, diagnosis, medication, dosage, risk). If set, the engine returns a fixed boundary card: contacts from the corpus (e.g. health hotline 1450, emergency 144, own doctor), no LLM text beyond a fixed sentence. The numbers on the card come from the corpus like everything else.
- `appointment_reason=acute` also returns the boundary card.
- No fact key can hold a diagnosis or symptom, so no rule can depend on one.
- Screening explanations (12.2) only restate a corpus rule with its source and always end with "Besprechen Sie das mit Ihrer Hausärztin / Ihrem Hausarzt".
- Script validation blocks medical wording (8.3).

## 11. Personalization

- Language and simple language: questions and service summaries are stored in German and simple German in the corpus. Other languages are translated by the LLM from those texts, never from scratch. Translated text is checked with the same regex rules as scripts (no new numbers, URLs, emails).
- Detail level: `short` shows title, why and actions only; `detailed` expands summaries and criteria.
- Preferences such as `preferred_time` and `near_home` shape the plan (call windows in the morning, institutions in or near the district first).
- Known facts are shown as one editable line above the plan and above fixed cards ("Verstanden: Mutter · 1100 Wien · OEGK", with "Ändern"), not above questions, where they would repeat the answers just given. This is how the user corrects extraction errors, and it shows what the plan is based on.

## 12. Use cases from the PDF

Each scenario lists the expected flow. Services, institutions and responsibilities are placeholders to be curated and verified.

### 12.1 Pflege

Input: "Meine Mutter ist chronisch krank und kommt allein nicht mehr zurecht. Was kann ich tun?"

Extracted: `subject=parent`, `needs_daily_help=a_lot`, `goal=[find_support_services]`. "chronisch krank" is not stored.

Questions (one per turn, chips):

1. In welchem Bezirk wohnt Ihre Mutter? -> `district`
2. Bezieht Ihre Mutter eine Pension? -> `employment_status` (decides the responsible institution for care allowance; to verify)
3. Lebt sie allein? -> `lives_alone`
4. Optional: Gibt es einen Entlassungs- oder Pflegebrief? -> upload step, not a blocking question

Plan (three bundles, matching the PDF):

- Pflegegeld: info step with criteria and `checked_by` -> "Unterlagen sammeln" -> call or form step to the responsible institution (script: request application, ask whether a relative can apply, ask about the assessment visit) -> wait step "Begutachtung" -> wait step "Bescheid", outcomes `granted`, `rejected` (rejected unlocks an info step on objection, if curated).
- Mobile Dienste / Unterstützung im Alltag: call step to the regional counselling institution with a script that covers help at home, transport and meals -> outcome `appointment_made` unlocks a visit or wait step.
- Nachsorge / Reha: only if a discharge letter was uploaded and confirmed; see 12.3.
- Angehörigenunterstützung: info step with relevant offers for relatives, if curated.

### 12.2 Gesundheitsförderung

Input: "Ich möchte etwas für meine Gesundheit tun."

Questions:

1. Alter (band) -> `subject_age_band`
2. Was interessiert Sie? (multi chips: Bewegung, Ernährung, Vorsorge, Impfungen, Stress) -> `interests`
3. Bezirk -> `district`
4. Only if `screening` is selected: "Gibt es in Ihrer Familie eine der folgenden Erkrankungen?" with chips limited to categories that have a corpus rule -> `family_history`

Plan (only for selected interests):

- Vorsorgeuntersuchung: info step with `why` and source -> book step (link to doctor search from the corpus, or call step with script using `preferred_time`).
- Screening by family history: info step that states the corpus rule with source, e.g. "Laut [Quelle] wird bei ... eine frühere Untersuchung empfohlen. Besprechen Sie das bei der Vorsorgeuntersuchung." The engine selects the rule; the LLM does not reason about risk.
- Impfungen: info step on checking the e-Impfpass, then book step.
- Bewegung: offers in or near the district (e.g. "Bewegt im Park" if curated, with season and dates), sign-up step.
- Ernährung, Stress, Gesundheitskurse: offers from the corpus with sign-up steps.

Risk note: the PDF asks for family-history-based screening explanations. This is the closest the system gets to a risk assessment. Mitigation: only fixed rules with sources, no LLM reasoning, fixed referral sentence.

### 12.3 Case manager after a hospital stay

Input: "Ich habe einen Entlassungsbrief bekommen, was muss ich jetzt erledigen?"

Flow: upload step -> extraction with quotes -> user confirms -> `documented_recommendations` -> questions only for what the services need (e.g. `insurer`, `employment_status`).

Plan per confirmed recommendation:

- `outpatient_rehab` / `inpatient_rehab`: info step "In Ihrem Brief steht: '...'" -> step to get the application from the doctor (call script to the doctor's office) -> form step with submission target -> wait step "Bewilligung" -> book step at a facility (list from the corpus, if curated).
- `follow_up_check`: call step to the doctor named by the user (the user enters name and number; the system does not look up doctors outside the corpus), script uses `preferred_time`.
- `medical_aid` (Heilbehelf): steps for prescription -> approval (if needed per corpus) -> supplier.
- `home_nursing`: links to the 12.1 bundle.

### 12.4 Kind

Input: "Ich habe ein Kind und möchte wissen, welche Angebote es gibt."

Questions: `subject_age_band` of the child, `district`, `insurer`, optional `interests`.

Plan, filtered by age band:

- Eltern-Kind-Pass examinations due in this age band: info step + book step.
- Kinderimpfprogramm: info step + book step.
- Kinder-/Jugendgesundheit, Bewegung, Ernährung: regional offers with sign-up steps.
- Familienberatung: call or visit step.
- Social and financial support (e.g. family allowance, inside and outside the SV system): info + form steps, if curated.

### 12.5 Arzttermin (PDF section 3.3)

Input: "Ich möchte einen Arzttermin."

Questions: `appointment_reason` (acute -> boundary card) -> `specialty` (chips, chosen by the user) -> `near_home` -> `preferred_time`.

Plan: book step (online booking from the corpus if available) or doctor search link -> call step with script ("Ich hätte gerne einen Termin für {reason}, am liebsten vormittags") -> outcome `appointment_made` stores date and time.

Limit: there is no booking API. The system prepares and guides; it does not book.

### 12.6 Multiple topics

"Meine Mutter war im Spital und braucht jetzt Hilfe" triggers 12.1 and 12.3 together. The engine merges candidates; questions are shared; shared steps are merged (6.4). This case must be in the evaluation set.

## 13. Data model and API changes

Database (per-chat state):

- `chat_facts`: `chat_id`, `key`, `value` (JSON), `source`, `quote`, `updated_at`
- `plans`: `id`, `chat_id`, `version`, `graph` (JSON: services, steps, edges), `created_at`
- `step_states`: `chat_id`, `step_id`, `status`, `outcome`, `note`, `script` (JSON), `updated_at`
- `messages`: add `kind` (`text`, `question`, `plan`, `boundary`) and `payload` (JSON)

SSE events added to `POST /chats/{id}/messages`: `facts`, `question`, `plan`, `boundary`. Existing `message`, `delta`, `title`, `done`, `error` stay.

New endpoints:

- `POST /chats/{id}/answers`: chip answer `{fact_key, value}`, same SSE stream as messages
- `PATCH /chats/{id}/facts/{key}`: edit a fact chip, triggers re-plan
- `PATCH /chats/{id}/steps/{step_id}`: status, outcome, note
- `POST /chats/{id}/documents`: upload (scenario 3)
- `POST /chats/{id}/steps/{step_id}/script`: regenerate script

## 14. Evaluation

A fixed test set in the repo, run as tests where possible:

- Extraction: per scenario at least 15 phrasings (colloquial, short, long, typos, English, simple German, irrelevant details, two topics). Expected facts per phrasing.
- Engine: table tests `facts -> expected services, questions, step ids`. Fully deterministic.
- Scripts: for each step template, generated output passes validation in at least X% of runs; fallback always passes.
- Hallucination check: every phone number, email and URL rendered anywhere must exist in the corpus. Automated over the full test set; target is zero violations.
- Boundary: a set of medical questions must all return the boundary card.
- Question count: median questions until the first plan per scenario (target at most 3).

## 15. Risks

| # | Risk | Effect | Mitigation |
|---|---|---|---|
| 1 | LLM puts wrong contact data or facts into a script | User calls the wrong number or asks the wrong thing | Placeholders only, regex rejection of numbers/URLs/emails, corpus fallback (8) |
| 2 | Corpus is wrong or outdated | Wrong advice with full confidence | `source_url` and `verified_at` on every record, staleness test, source link on every card |
| 3 | Extraction misreads a fact | Wrong plan | Editable fact chips, chip answers bypass the LLM, user edits win |
| 4 | Medical boundary is crossed (esp. 12.2 family history, 12.3 letters) | Disqualifying in the jury criteria, harmful | No medical fact keys, quote check, fixed rules with sources, boundary card, blocklist |
| 5 | Too many questions | User drops off | One question per turn, cap of 4, chips, ask step-only facts inside the step |
| 6 | Situation outside the corpus | Empty or wrong plan | General contact card, never a free LLM answer; log for corpus work |
| 7 | Graph gets large with multiple topics | Wall of cards | Group by service, show only available steps expanded, collapse blocked ones |
| 8 | Responsibility rules are more complex than modeled (insurer x status x age) | Wrong institution | Model `responsible` as explicit rules with tests per combination; show "zuständig laut [Quelle]" |
| 9 | Personal data (SV number, health context) in prompts and storage | Privacy problem | Placeholders, only confirmed quotes stored, uploads not persisted beyond extraction |
| 10 | No booking or submission APIs | "Termine vereinbaren" from the PDF only partly met | Be explicit in the UI and pitch: prepare and guide, deep links where available |
| 11 | Overfitting to the demo | Breaks on jury input | Section 16 |

## 16. Overfitting

The jury will test with their own phrasings and combinations. The system must not only work for the sentences in the PDF.

Rules:

- No scenario ids or scenario-specific branches in code. The engine only knows facts, services and step templates. Adding a service is a data change.
- Prompts contain the fact schema and generic instructions, not example sentences from the PDF.
- The evaluation set (14) is written before prompt tuning and split: a tuning set and a held-out set. Prompts are changed only based on the tuning set; the held-out set is only measured. At least part of the held-out set is written by a team member who did not write the prompts.
- The held-out set includes cases the PDF does not mention: two topics at once, a relative outside Vienna, an unknown insurer, a user who refuses to answer, English input, medical questions disguised as admin questions.
- Breadth over depth for the corpus: each of the six PDF areas (A-F) has at least one service with real data, so unexpected topics in those areas do not fall through to the general card.
- Fact schema growth is gated by the "every key is used" test, so the schema does not grow per demo sentence.

## 17. Keeping it viable (prototype -> product)

- The corpus format is the product's real asset. It is plain data with sources, so a social insurance carrier could own and maintain it without touching code.
- The engine is pure and table-tested; correctness can be reviewed by domain experts by reading the test tables.
- The LLM part is replaceable: three narrow calls with structured output, each with a deterministic check and a non-LLM fallback (chips, corpus scripts). The system degrades to a guided form, not to a broken one, if the LLM fails.
- Cost and latency: at most three small LLM calls per turn, scripts cached per plan version.
- Integration path: `book` and `form` steps are the extension points for real booking or submission APIs later, without changing the plan model.
- Vienna-only and a small corpus are explicit limits shown in the UI, not hidden.

## 18. Jury criteria mapping

| Criterion (PDF) | Where it is addressed |
|---|---|
| Eigenständig, durchdacht | Responsibility split (2), engine (6) |
| Flexibel, intelligent | Question selection (6.2), multi-topic merge (12.6), outcomes and re-plan (7.3) |
| Daten und Wissensquellen genutzt und verknüpft | Corpus (5), sources on every card |
| Verständlichkeit, Nutzerorientierung | Step cards (7.1), simple language (11), no walls of text |
| Qualität der Handlungsschritte | Ready scripts and emails (8), step graph (7) |
| Umgang mit Unsicherheit, Transparenz, Grenzen | Three-state eligibility (6.3), fact chips (11), boundary (10), quotes (9) |
| Realistische Weiterentwicklung | Section 17 |
| Innovation | Step graph with outcomes, document quotes, personal data kept out of the LLM |

## 19. Out of scope

- Real appointment booking and electronic submission.
- Regions outside Vienna.
- Memory across chats (as in `README.md`).
- Barrierefreiheit (as in `README.md`); voice input is not planned.
- Medical advice of any kind.

## 20. Open decisions

1. Corpus storage: YAML in the repo (recommended) or database tables.
2. Whether the LLM may translate corpus texts into other languages, or only questions and scripts.
3. Rule format: declarative fields per service (recommended) or Python predicates.
4. Graph rendering: plain CSS columns or a graph library.
5. OCR/vision provider for photos of letters.
6. Initial service list per scenario and who curates and verifies it.
7. Question cap (proposed 4) and script validation thresholds.

## 21. Implementation plan

Four phases. Phases 1-3 are required for the challenge; phase 4 is optional. Each phase ends with a check that can be run, not a judgment.

Principle for the order: the engine and corpus are built and tested first without any LLM. The LLM calls are added on top. If the LLM fails during the demo, the chip-driven flow still works.

### 21.1 Phase 1: care slice (scenario 12.1, text only)

Required:

| # | Item | Where |
|---|---|---|
| 1 | Corpus pydantic models, YAML loader, cached like `get_llm` | `backend/src/backend/corpus.py` |
| 2 | Corpus checks from 5.2 as tests | `backend/tests/test_corpus.py` |
| 3 | Fact schema, JSON schema generation for the LLM, merge rules | `backend/src/backend/facts.py` |
| 4 | Engine: candidates, next question, eligibility, plan (pure functions) | `backend/src/backend/engine.py` |
| 5 | Engine table tests (`facts -> services, question, step ids`) | `backend/tests/test_engine.py` |
| 6 | Opening hours: "jetzt erreichbar" / next window | `backend/src/backend/hours.py` |
| 7 | Tables `chat_facts`, `plans`, `step_states`; `Message.kind`, `Message.payload` | `backend/src/backend/models.py` |
| 8 | `send_message` runs the pipeline instead of free `reply()`; events `facts`, `question`, `plan`, `boundary` | `backend/src/backend/routers/chats.py` |
| 9 | Endpoints `answers`, `facts/{key}`, `steps/{step_id}` | `backend/src/backend/routers/chats.py` |
| 10 | LLM `extract_facts()` with structured output | `backend/src/backend/llm.py` |
| 11 | Script generation, validation (8.3), placeholder fill, fallback | `backend/src/backend/scripts.py`, `backend/tests/test_scripts.py` |
| 12 | Boundary card (section 10) | `engine.py`, corpus |
| 13 | Frontend: event types and API calls | `frontend/src/chats.ts` |
| 14 | Frontend: fact chips, question card with chips, plan as list grouped by service, step card (call, email, info, wait), check off, outcome picker | `frontend/src/components/FactChips.vue`, `QuestionCard.vue`, `PlanView.vue`, `StepCard.vue` |
| 15 | Sidebar status computed from step states | `routers/chats.py` (`ChatResponse`), `ChatApp.vue` |
| 16 | Extraction eval set for scenario 1 (15+ phrasings, tuning and held-out split) | `backend/tests/eval/pflege.yaml` |

Not in phase 1: upload, translation, graph view (list is enough), form prefilling, outcome branching beyond `done` / `not_reached`.

Corpus records for phase 1 (each record must carry `source_url`; the files below are the local copies to curate from):

| Record | Kind | Curate from |
|---|---|---|
| `care_allowance` (Pflegegeld) | service | `data/raw/web/text/pflege/pv.at_web_pflegegeld_e24701.txt`, `.../oesterreich.gv.at_de_themen_pflege_4_Seite.360515_e7f7b8.txt`, `.../sozialministerium.gv.at_Themen_Pflege_Pflegegeld.html_2255a9.txt` |
| `care_allowance_form` | form | `data/raw/svbox/Anträge und Formulare/PAL080_0125_Mpfl_052026.pdf` (PVA application under BPGG) |
| `home_care_fsw` (Heimhilfe, Hauskrankenpflege, counselling) | service | `data/raw/web/text/pflege/fsw.at_p_pflege-betreuung-daheim_d6bc45.txt`, `.../fsw.at_p_heimhilfe-pflege-betreuung_2983ca.txt`, `.../fsw.at_p_hauskrankenpflege_12d13c.txt`, `.../fsw.at_p_fragen-antworten_9c36e3.txt` |
| `fsw_application_form` | form | `data/raw/svbox/Anträge und Formulare/fsw-antrag-auf-foerderung-von-leistungen.1779095804.pdf`, `data/raw/web/text/pdf_listed/fsw.at_antrag_95d121.txt` |
| `carer_support` (home visit, talk for relatives) | service | `data/raw/web/text/pflege/gesundheit.gv.at_leben_altern_wohnen-im-alter_pflegende-angehoerige-entlastungen-unterstue_42c9ec.txt`, `.../sozialministerium.gv.at_Themen_Pflege_Betreuende-und-Pflegende-Angehoerige.html_df529e.txt`, `.../fsw.at_p_pflegende-angehoerige_9f99c6.txt` |
| `pva_vienna` | institution | `data/raw/web/text/contacts/pv.at_web_service-und-kontakt_kontakt_wien_kontakt-wien_2d1a86.txt` |
| `fsw_customer_service` | institution | `data/raw/web/text/contacts/fsw.at_kontakt_8b0c77.txt` |
| `oegk_vienna_customer_service` (general fallback) | institution | `data/raw/web/text/contacts/oegk.at_cdscontent_contentid_10007.870674_portal_oegkportal_fc0ed4.txt` and the other Kundenservice files |
| boundary contacts | institutions | `data/raw/web/text/contacts/sozialministerium.gv.at_Themen_Gesundheit_eHealth_Gesundheitsberatung-1450.html_269ca8.txt`, `.../gesundheit.gv.at_service_notruf_hotline.html_4b78ea.txt` |

Done when:

- `pytest` passes, including corpus checks and engine table tests.
- The held-out scenario 1 phrasings reach a plan with the expected services in at most 3 questions in at least 80% of cases (threshold is an open decision).
- The hallucination check (14) finds zero phone numbers, emails or URLs that are not in the corpus.
- With the LLM disabled, the flow still completes via chips and fallback scripts.
- Step states survive a page reload.

### 21.2 Phase 2: discharge letter (scenario 12.3)

Required:

| # | Item | Where |
|---|---|---|
| 1 | Upload endpoint, text extraction from text-based PDFs | `routers/chats.py`, `backend/src/backend/documents.py` |
| 2 | LLM `extract_recommendations()` returning enum + quote | `llm.py` |
| 3 | Quote check against the document text, confirm UI | `documents.py`, `frontend/src/components/DocumentConfirm.vue` |
| 4 | Services for the recommendation enums | corpus |
| 5 | Upload and form step types on the card | `StepCard.vue` |
| 6 | Test letters: the SV-Box letter plus at least two written by a team member who does not write the prompts | `backend/tests/eval/letters/` |

Test letter: `data/raw/svbox/Befunde/Entlassungsbefund.pdf`. Its sections 6 and 7 contain both kinds of recommendation and are the main boundary test:

- To become steps: mobile home nursing, help with personal care, shopping and household, help with getting to radiotherapy appointments, nutrition counselling, timely GP follow-up, inpatient oncological rehabilitation after radiotherapy.
- To be ignored: checking blood values, blood pressure therapy, overall medication and interactions. These are medical tasks for doctors and map to no enum.

Corpus records for phase 2:

| Record | Kind | Curate from |
|---|---|---|
| `rehab` | service | `data/raw/web/text/reha/pv.at_web_reha-und-praevention_vom-antrag-zu-reha-und-kur_91d4c2.txt`, `.../gesundheit.gv.at_gesundheitsleistungen_kur-reha_medizinische-rehabilitation.html_ac4704.txt` |
| `rehab_form` | form | `data/raw/svbox/Anträge und Formulare/Antrag Kur und Reha.pdf` |
| `transport_cost_subsidy` | service + form | `data/raw/svbox/Anträge und Formulare/Antrag-auf-Zuschuss-zu-Fahrtkosten_Wien.pdf`, `data/raw/web/forms/oegk_wien/` (Krankentransportwagen, Vertragsfahrtendienst) |
| `home_nursing_medical` | service | `data/raw/web/forms/oegk_wien/Medizinische_Hauskrankenpflege.pdf`, FSW Hauskrankenpflege files |
| `medical_aids` | service | `data/raw/web/text/heilbehelfe/oegk.at_cdscontent_contentid_10007.870456_portal_oegkportal_a37991.txt` |
| `nutrition_counselling` | service | `data/raw/svbox/Leistungskataloge/Serviceratgeber-2026_Broschuere_A5_OEAM_99-19_klein_korr.pdf`, ÖGK health centre pages |
| `gp_follow_up` | service | no institution record: the user enters their doctor; script only |

Dependency: `pypdf` for text extraction (justification: no PDF text extraction in the current stack). Photos are out of scope for this phase.

Done when:

- The SV-Box letter yields the expected recommendations, each with a quote that passes the check.
- None of the medical recommendations listed above appears as a step.
- The two team-written letters produce their expected recommendations.

### 21.3 Phase 3: remaining scenarios (12.2, 12.4, 12.5)

Mostly data. Code changes are limited to new fact keys, the `available` date filter and the `book` step type.

| Scenario | Records | Curate from |
|---|---|---|
| 12.2 Gesundheitsförderung | Vorsorgeuntersuchung, Impfungen, Bewegt im Park (seasonal), ÖGK courses | `data/raw/web/text/vorsorge/`, `text/impfen/wien.gv.at_gesundheit_impfen_71d83c.txt`, `text/bewegung/`, `text/gesundheitsfoerderung/` |
| 12.4 Kind | Eltern-Kind-Pass, Kinderimpfprogramm, Familienbeihilfe, MA 11 Familienberatung, Familienzentren, Enorm in Form | `data/raw/web/text/kind/`, `data/raw/web/forms/bmf/beih3_Familienbeihilfe_Antrag.pdf` |
| 12.5 Arzttermin | doctor search link, call script | `data/raw/web/text/arzt/` (the ÖGK search is a web app; only the link is used) |
| Area E (social) | Mindestsicherung, Hilfe in besonderen Lebenslagen | `data/raw/web/text/sozial/`, `text/contacts/wien.gv.at_zusammenleben_sozialhilfe-mindestsicherung-standorte-oeffnungszeiten_9330bb.txt` |

Gaps in the data:

- `impfservice.wien` blocks automated download (403). Vaccination details must be copied by hand or taken from wien.gv.at.
- Bewegt im Park course list is offline until May 2027. Model it as seasonal with a link only.
- No doctor directory. Scenario 12.5 uses the ÖGK search link.

Done when: the held-out eval sets for 12.2, 12.4, 12.5 and the multi-topic case (12.6) meet the same thresholds as phase 1.

### 21.4 Phase 4: optional

In order of value per effort:

1. Graph view of the plan (instead of the list).
2. Outcome branching beyond `done` / `not_reached`.
3. Translation to other languages (section 11).
4. Form prefilling (only for PDFs with fillable fields; to check per form).
5. Screening by family history (12.2), only if the team accepts the risk in 15.4.
6. Photos of letters (OCR/vision provider).

### 21.5 Technical notes

- **Schema changes:** `Base.metadata.create_all` in `app.py` creates new tables but does not add columns to existing ones. Adding `Message.kind` and `Message.payload` needs a reset of the dev database. There are no migrations; none are added for the prototype.
- **Structured output:** the extraction calls use `response_format` with a JSON schema generated from `facts.py`. Support depends on the Azure deployment; to verify with the deployed model before phase 1 item 10.
- **YAML:** the corpus format needs `PyYAML` (new dependency). JSON would avoid it but is harder to curate by hand. Open decision 1.
- **Streaming:** only the short intro text is streamed (`delta`); questions and plans arrive as single events.
- **Scraper:** the script that produced `data/raw/web/` should move to `backend/scripts/scrape.py` if the sources are re-fetched before the demo.
- **Raw data:** `data/raw/` holds third-party material (about 60 MB) and should not be committed; add it to `.gitignore`.

### 21.6 Curation workflow

1. Pick a record from the phase tables.
2. Read the local copy in `data/raw/`, write the YAML record with `source_url` (the live URL from `data/raw/web/manifest.tsv`), `verified_at` and only facts stated in the source.
3. A second person checks phone numbers, hours and addresses against the live page.
4. `pytest` runs the corpus checks.
5. Conflicting statements across sources (for example differing hotline hours) are resolved from the institution's own page, never by picking one silently.
