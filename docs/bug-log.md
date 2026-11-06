# Bug log

Date: 2026-11-06. Branch: `fix/bug-hunt`, based on `main` at 3062d92 (rename to Zetta).

Scope: the whole app after the recent merges (security fixes, off-topic handling, home dashboard, app bar and
footer, form wizard, email instead of a call, rename to Zetta).

Method:

- Baseline: `uv run pytest -q` (449 passed), `npm run build` with type-check (passed), `npm test` (6 passed). No
  linter is configured in the project (no ruff or eslint config).
- Code review of `pipeline.py`, `engine.py`, `forms.py`, `scripts.py`, `documents.py`, `translations.py`, the
  routers, `guards.py`, `chats.ts`, `i18n.ts`, `ChatApp.vue`, `StepCard.vue`, `PlanView.vue`, `FormWizard.vue`,
  `FactChips.vue`, `QuestionCard.vue`, `NextUpList.vue`, `SettingsPage.vue` and `App.vue`.
- A separate stack (backend on port 8010 with its own SQLite file, Vite on 5183) with the real LLM, driven over the
  API with a small script and in the browser pane. Test data was the fictional persona from `backend/tests`. About 40
  real LLM calls in total.
- Covered flows: Pflegegeld for a mother, a child's check-up, a dermatologist appointment, financial help, a medical
  question, an off-topic question followed by an on-topic one, outside Vienna, a hospital discharge with a PDF letter
  upload. Every step outcome, a branch (decision granted and rejected), reopening, call to email and back, all 4 form
  wizards with the PDFs read back with pypdf, password change, account deletion, settings, home dashboard, English,
  dark mode, high contrast, text sizes M, L and XL at 375px, keyboard only, browser back and forward.

## Fixed

### B1: The plan chat scrolls sideways on phones

- Severity: high. The plan is the main screen, and the users who pick large text are the ones who need it most. It
  also happened at normal text size as soon as an email step was open.
- Area: `frontend/src/components/ChatApp.vue:734`, `:736`; `frontend/src/components/StepCard.vue:349-363`.
- Found by: the known issue, confirmed in the browser pane with a 375px viewport and measurements of `scrollWidth`.
- Steps: open a chat with a plan on a 375px wide screen, set text size to "Sehr groß" in the settings, look at the
  plan. Or at normal size: open the step "Angehörigengespräch anfragen".
- Expected: the chat column fits the screen.
- Actual: the message column was 434px wide on a 375px screen (59px too wide), so the whole chat, including the
  plan bar and the "Verstanden" line, slid sideways. At normal size with the email step open: 31px too wide.
- Root cause: the grids around a plan reply (`.msg.assistant`, `.plan-msg`) had no column limit, so the widest
  content set the width of everything in the reply, the "Verstanden" line included. That content was in the step
  cards: the phone number in the call button could not wrap (`white-space: nowrap`), long single words
  ("Gesprächsleitfaden", the address `angehoerigengespraech@svqspg.at`) could not break, and on narrow screens the
  card details kept an inset as deep as the title, which grows with the text size. The narrow rule for the right
  padding of `.card-sub` never applied either, because the base rule came after it in the file.
- Fix: commit `fix(frontend): stop the plan chat from scrolling sideways on phones`. The reply grids get
  `minmax(0, 1fr)` like the message list already has; card details and bodies may hyphenate and break long words;
  a phone number wraps only at its spaces; on narrow screens the card details use the card's whole width; the base
  `.card-sub` rule moved above the narrow rule.
- Evidence: before, 434px vs 375px at XL in the Pflegegeld chat. After, 0px overflow for all 8 test chats at M, L and
  XL with every step card and every "Mehr dazu" open; home, chat list, settings and the form wizard also 0px. At XL
  the call button shows "01/24 5" and "24" on two lines and the link reads "Gesprächsleit-faden".
- Status: fixed.

### B2: "meine meine Mutter" in LLM-written scripts

- Severity: medium. The user reads these texts out on the phone; seen in 3 of 4 LLM scripts of a Pflegegeld plan.
- Area: `backend/src/backend/scripts.py:54` and `:104`, `backend/src/backend/llm.py:63`.
- Found by: the known issue, confirmed in code: nothing checked the words in front of a placeholder.
- Steps: start a Pflegegeld chat for a mother and get to the plan. Open "Bei der zuständigen Stelle anrufen".
- Expected: "Ich rufe wegen Pflegegeld für meine Mutter an."
- Actual: "... für meine meine Mutter an."
- Root cause: `{subject.relation}` is rendered as "meine Mutter" or "meinen Vater", with the possessive. The prompt
  only said it is "in the accusative", so the LLM wrote "meine {subject.relation}", and `check_text` accepted it.
- Fix: commit `fix(scripts): reject a possessive before the relation placeholder`. The prompt says the placeholder
  brings its own possessive and shows "für {subject.relation}". `check_text` rejects a possessive or article right
  before `{subject.relation}`, so such a script is retried once and then replaced by the corpus script, as for any
  other rejected script.
- Regression tests: `tests/test_scripts.py::test_invalid_scripts_are_rejected` (two new cases) and
  `tests/test_chats.py::test_a_possessive_before_the_relation_placeholder_never_doubles_it` (fake LLM writes
  "für meine {subject.relation}"; the plan gets the corpus scripts and no "meine meine"). Both fail without the fix.
- Live check after the fix: a new Pflegegeld plan got 4 of 4 LLM scripts accepted, none doubled.
- Status: fixed.

### B3: Keyboard focus is lost after answering a chip or updating a step

- Severity: medium. Accessibility failure (focus order) in the two main flows: keyboard and screen reader users are
  sent back to the top of the page after every answer and every step action.
- Area: `frontend/src/components/ChatApp.vue:82`, `:229`, `:373`.
- Found by: keyboard pass in the browser pane.
- Steps: in a chat, Tab to a chip of the open question and press Enter. Or open a step, Tab to "Gelesen" (or "Lieber
  eine E-Mail schreiben", "Doch noch nicht erledigt") and press Enter. Then press Tab.
- Expected: focus stays near what was just done.
- Actual: the pressed chip or button disappears with the new state, `document.activeElement` becomes `<body>`, and the
  next Tab starts at "Zum Inhalt springen" at the top of the page.
- Root cause: no focus handling when the pressed control is removed by the update.
- Fix: commit `fix(frontend): keep keyboard focus after a chip answer or step update`. If focus fell to the page,
  it goes to the composer after an answer (the new question's chips are one Shift+Tab away, and the reply is
  announced in the live region) and to the step's heading button after a step update.
- Evidence: before, `<body>` after the switch to email. After, `t-home_care_fsw.call` after the switch,
  `t-home_nursing_medical.info` after "Gelesen", and the composer `#q` during and after a chip answer.
- Status: fixed.

### B4: Wrong translations of "Neu registrieren" and "Zum Plan"

- Severity: low. The sign-in card is the first screen a new user sees, in all 5 languages it read "register again";
  the plan bar in English read "To the map".
- Area: `frontend/src/locales/*.json`, `backend/scripts/translate.py:100`.
- Found by: the login screen and the plan bar in English in the browser pane.
- Steps: log out, pick English: the second tab says "Register again". Log in, open a plan: the bar says "To the map".
- Expected: "Create new account" (and the same meaning in fr, cs, sk, sl); "To the plan".
- Actual: en "Register again", fr "S'inscrire à nouveau", cs "Zaregistrovat se znovu", sk "Zaregistrovať sa znova",
  sl "Registrirajte se na novo"; en "To the map".
- Root cause: short labels translated without context.
- Fix: commit `fix(i18n): translate the sign-up tab and the plan button correctly`. Notes for both labels in
  `translate.py`, the entries regenerated with `uv run scripts/translate.py`. The Slovenian answer was still close to
  "register anew", so it was set to "Ustvarite nov račun" by hand (the script keeps valid entries).
- Regression test: `tests/test_translations.py` passes; no test can judge meaning.
- Status: fixed.

### B5: Changing the letter's recommendations under "Verstanden" is saved as "Stimmt so"

- Severity: low. Wrong text in the chat history; the facts themselves were right.
- Area: `backend/src/backend/routers/chats.py:198`.
- Found by: code review of the answer endpoint, then reproduced over the API.
- Steps: upload a discharge letter, confirm its items, get to the plan, then change "Laut Ihrem Dokument" under
  "Verstanden" to one item. Reload the chat.
- Expected: the user's message reads "Laut Ihrem Dokument: Hauskrankenpflege", as shown while sending.
- Actual: it reads "Stimmt so", the answer of the confirm card.
- Root cause: the endpoint told the confirm card from a fact edit by the value being a list, but the request schema
  turns every value of this list fact into a list.
- Fix: commit `fix(chats): label a later change of the letter's items as an edit`. The confirm card's labels are
  used only while the confirm card is the latest assistant message (the facts line is not shown under it).
- Regression test: `tests/test_documents.py::test_upload_confirm_and_plan_with_quotes` (new last part). Fails without
  the fix.
- Status: fixed.

### B6: The home list shows a translatable label in German

- Severity: low. One line in "Was jetzt ansteht" stays German in another language.
- Area: `frontend/src/components/NextUpList.vue:46`.
- Found by: scanning the English UI for German text.
- Steps: switch to English, have a doctor's appointment chat with the practice list. Look at the home page.
- Expected: "A practice from the list" (it is in the catalog), as on the step card.
- Actual: "Eine Ordination aus der Liste".
- Root cause: the institution line is shown without `t()`, unlike in `StepCard.vue`. Real institution names are not
  in the catalog and stay German either way.
- Fix: commit `fix(frontend): translate the institution line on the home list`.
- Evidence: after the fix the home list shows "A practice from the list".
- Status: fixed.

## Open

### O1: The backend container does not reload changed code

- Severity: low (development only), but it cost a teammate time: a new frontend against an old backend showed the
  blank-PDF fallback instead of the form wizard.
- Area: `compose.yaml:10`.
- Cause: `uvicorn` runs without `--reload`, so after a pull the backend serves the old code until it is restarted.
- Proposal: add `--reload` to the backend command for local development. Without `watchfiles` uvicorn falls back to
  polling (`StatReload`), which also works on mounted volumes; seen on the local stack of this hunt.
- Status: open, waiting for the user's decision before `compose.yaml` is changed.

### O2: Two tabs answering at the same moment can create two plans with the same version

- Severity: low. Needs two replies to the same chat within the few seconds of an LLM call.
- Area: `backend/src/backend/pipeline.py:474`, `backend/src/backend/models.py:135`.
- Cause (code-level): the new version is the latest one plus 1, read without a lock, and `plans` has no unique
  constraint on chat and version. Both turns also insert the same new `step_states` rows, so the second one fails on
  the primary key and gets "Reply failed".
- Why open: a fix needs a lock per chat or a unique constraint with a retry, which is more than a small change.

### O3: A later message about another person mixes two people's facts

- Severity: low to medium, needs a product decision.
- Area: `backend/src/backend/facts.py:288` (`merge`).
- Steps: answer "Für wen" with "Für mich selbst", get to a plan, then write "Mein Vater braucht Pflege, er lebt in
  Döbling".
- Actual: "Für wen" stays "Für mich selbst" (a chip answer always beats an extraction), but the district becomes
  Döbling and the help needed becomes the father's. The next question is "Leben Sie allein?".
- Why open: the source order (chip over text) is in the spec on purpose. Starting a new chat or editing "Für wen"
  under "Verstanden" works; whether a new person should reset the facts is a product decision.

### O4: The insured person's SV number in the rehab and transport forms is not checked

- Severity: low. A typo goes onto the paper form.
- Area: `backend/corpus/forms.yaml:550` and `:639` (`insured_svnr`).
- Cause: the check digit is only checked for questions bound to a person's detail (`{subject.svnr}`); the insured
  relative's number is a plain text question. In the hunt it accepted "Testwert".
- Why open: needs a new question kind or detail in the corpus schema, which is more than a bug fix.

## Checked and fine

- All 8 scenarios end where they should: plans for care, child, appointment, money and discharge; the boundary card
  for the medical question; the out-of-scope card for Linz; the goal question with the off-topic note, which did not
  count toward the question cap.
- Letter upload: SV number and dates are redacted before the LLM, only quotes that are in the letter are kept, the
  file name with an umlaut is shown correctly, the quotes appear under "Mehr dazu".
- Step outcomes: "Nicht erreicht" keeps a call open, every other outcome closes its step, the next steps unlock,
  "rejected" opens the clarification branch and reopening hides it again, "granted" does not. Call to email and
  back resets the step and shows the corpus text of the other way.
- Form wizards (Pflegegeld PAL 080, FSW, rehab, transport): answers saved section by section, conditional questions,
  progress, review findings including the contradiction check on the FSW form. The downloaded PDFs had 60, 42, 42
  and 8 filled fields with the expected values (read back with pypdf). "Remember" kept the mother's details and did
  not change the profile.
- Settings: profile with the SVNR split into the 4 digits and the birth date, password change (422 for a short one,
  403 for a wrong current one, other sessions logged out), account deletion (403 for a wrong password, then login
  fails).
- Home "Was jetzt ansteht" and the sidebar agree on each chat's state; "Erreichbar heute ab 8:00 Uhr" was right for
  the time of day.
- English: settings, plans, cards and wizard fully translated apart from user data, institution names and plan intros
  written earlier in German (by design: the intro is written once, in the language set at the time).
- Dark mode with high contrast, keyboard order on the home page (every stop has a visible focus ring), Escape in the
  form wizard (goes through the wizard's own close, so ChatApp is told), browser back and forward between chats and
  settings.
- The rename: no "Lotse" left in the UI, the catalogs or the code apart from storage keys and the cookie name.

## Not covered

- Real phones and screen readers (only Chrome's emulation in the browser pane and DOM checks).
- Widths below 375px, other browsers, right-to-left languages (Arabic is offered for answers, not for the interface).
- Two tabs in practice (O2 is from the code), a reload in the middle of a reply beyond what the existing tests cover,
  and the rate limits under load.
- Turkish, Bosnian/Croatian/Serbian, Romanian, Polish, Hungarian, Ukrainian and Arabic answers, and the LLM form help
  (explain, draft, ask, check) with the real LLM, to stay within the LLM budget.
- The docker compose stack itself.
