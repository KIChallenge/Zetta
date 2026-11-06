# Security review: Zetta

- **Scope:** `main` at `0456cae` (2026-11-05), working tree as it is. Review only, no code changed.
- **Method:**
  - Read every file listed in the task: `backend/src/backend/**`, `backend/scripts/`, `frontend/src/**`, `frontend/index.html`, `frontend/vite.config.ts` and `compose.yaml`.
  - Ran `npm audit`, and `pip-audit` on an export of `uv.lock`.
  - Scanned the full git history for secrets with redacted output.
  - Probed two targets dynamically:
    - **An isolated backend copy** on `127.0.0.1:8011`. It used a temporary SQLite DB and a fake LLM, did not load the real key and made no Azure calls.
    - **The running docker stack**, for non-LLM checks only: headers, Vite exposure, XSS rendering in the built-in browser, and one 30 MB body.
- **Test accounts:**
  - `sec-test-a` and `sec-test-b` lived in the isolated DB, which is now deleted.
  - `sec-test-xss` lived in the docker DB. It was deleted through `DELETE /me`, and `users where email like 'sec-test%'` now returns 0 rows.
  - The isolated server is stopped. The docker containers were already running and were left running.

## 1. Summary

**The basics are solid:**
- Access control holds: no IDOR on any chat route.
- JWT handling is correctly pinned, passwords use argon2, and no secret is in git.
- Contact data never comes from the LLM, and all user and LLM text renders escaped.

**The main risks are availability and abuse.** The backend has no limits of any kind: request size, rate, LLM usage and PDF parsing cost are all unbounded. Docker compose also publishes the backend, the Vite dev server and Vue devtools on every network interface. So anyone on the same Wi-Fi can register and, with a single request, either:
- freeze the backend for every user (a 64 kB PDF blocked everyone for 5.6 s), or
- send millions of characters to the team's Azure deployment.

**Data protection is mostly a production topic.** Discharge letters (health data, names, often the SVNR) go to Azure OpenAI in full, and deleted accounts stay readable in the SQLite file.

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 2 |
| Medium | 5 |
| Low | 7 |
| Info | 9 |

**Fix first, in this order:**

1. **M-1:** Bind the compose ports to `127.0.0.1`. Effort S. This takes the network attacker out of the demo.
2. **H-1:** Run PDF parsing off the event loop, with a page cap and a character cap. Effort S/M.
3. **H-2:** Cap request body size before reading, on uploads and on all JSON routes. Effort S.
4. **M-2:** Cap the letter text sent to the LLM, add per-user LLM rate limits and set client timeouts. Effort S/M.
5. **M-3:** Throttle login, and raise the backend password minimum to 10 characters to match the frontend. Effort S/M.

## Fix status (branch `fix/security-vulnerabilities`)

The findings below describe `0456cae`. This branch fixes them on top of `ebb9719`. Each fix has a test in `backend/tests/test_security.py`, and I re-ran the review probes against the fixed backend.

| ID | Status | What changed |
|---|---|---|
| H-1 | Fixed | The PDF is parsed in a separate process with a 15 s timeout, at most 30 pages and 60,000 characters. The 400-page PDF is now refused in 0.34 s, and the other user waited 5 ms (was 5.6 s). |
| H-2 | Fixed | `guards.BodyLimit`: 64 kB for JSON, 10 MB for uploads, checked on `Content-Length` and counted for chunked bodies. A 30 MB body gets a 413 without being read. |
| M-1 | Fixed | Compose binds both ports to `127.0.0.1`. `/docs`, `/redoc` and `/openapi.json` are off. `TrustedHostMiddleware` checks the `ALLOWED_HOSTS` setting. |
| M-2 | Fixed | 60 LLM turns and 10 uploads per user per hour. At most 60,000 characters of a letter reach the LLM. The client uses a 60 s timeout and 1 retry. |
| M-3 | Fixed, one gap | Passwords need 10 characters, and common ones are refused. Login locks for 15 min after 5 failures per email, and password checks after 5 failures per user. Registrations are limited per address, and at most 4 argon2 hashes run at once. Gap: there is no per-address login limit, because behind the dev proxy all users share one address. In production, add it at the reverse proxy. |
| M-4 | Fixed | Tokens carry a version (`token_versions` table). A password change or `POST /auth/logout` ends every older token. Expiry stays 24 h (`JWT_EXPIRE_MINUTES`). |
| M-5 | Code fixed, legal work open | SVNRs and emails are redacted before every LLM call, and dates as well in letters. Still open, and not code: the DPIA, consent at upload, processor terms and Azure abuse-monitoring retention. |
| L-1 | Fixed, one gap | `PRAGMA secure_delete`, and the DB file is set to 0600 at startup. Still open: the SVNR is stored in plaintext at rest, which needs key management. Data deleted before this fix stays in old files until you run `sqlite3 backend/zetta.db VACUUM` once. |
| L-2 | Fixed | The API sends `default-src 'none'`, `frame-ancestors 'none'`, `nosniff`, `no-referrer` and `no-store`. Vite dev and preview send a CSP and frame protection, and the inline script moved to `public/view.js`. Whatever serves the built app in production must send the preview headers. |
| L-3 | Fixed | The session is an httpOnly, `SameSite=Strict` cookie, `Secure` over https. Cookie-authenticated changes need `X-Requested-With`. The frontend no longer stores a token and removes the old one from `localStorage`. |
| L-4 | Open | Hiding whether an email has an account needs confirmation emails. It is mitigated by the registration limit. |
| L-5 | Fixed | Source Sans 3 is self-hosted in `frontend/public/fonts`, with no Google requests. |
| L-6 | Partly fixed | Done: images pinned by digest, `uv run --frozen`, `npm ci` and `restart: unless-stopped`. Not done: non-root users and read-only mounts, because they would break the existing volumes and the location of `zetta.db`. |
| L-7 | Fixed | The filter now catches any domain and runs of spelled-out digits. |
| I-1 | Fixed | The title is redacted and checked with `check_text`. If the check fails, the chat keeps its title. |
| I-2 | Fixed | Quotes are capped at 300 characters. |
| I-3 | Fixed | DOMPurify allows only Markdown tags and `href`. |
| I-4 | Fixed | The docstring is corrected, and a test asserts that no profile value appears in any LLM call. |
| I-5 | Fixed | See M-1. |
| I-6 | Fixed | `.env.example` warns about plain-http LLM endpoints. |
| I-7 | Fixed, except entropy | A root `.gitignore` covers `.DS_Store` and `.env*`, and `frontend/.gitignore` covers `.env*`. `JWT_SECRET` is still only checked for length. |
| I-8 | Fixed | The doctor import keeps https links only, and a test checks every link in the corpus. |
| I-9 | Open | Data export, retention and a privacy notice are product and legal decisions. |

## 2. Findings

### H-1 PDF parsing blocks the event loop: one upload freezes the backend for all users

- **Severity:** High.
  - CVSS 3.1 base 6.5 (`AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H`).
  - Ranked High on likelihood × impact:
    - accounts are free (open registration, no verification);
    - the exploit is one small request;
    - the impact is a full, repeatable outage for every user.
- **Affected:** `backend/src/backend/routers/chats.py:185-200`, `backend/src/backend/documents.py:13-16`
- **Evidence:**

  ```python
  async def upload_document(request: Request, ...):   # async def
      data = await request.body()
      ...
      text = documents.pdf_text(data)                  # synchronous pypdf on the event loop
  ```
  ```python
  def pdf_text(data: bytes) -> str:
      reader = PdfReader(io.BytesIO(data))
      return "\n".join(page.extract_text() or "" for page in reader.pages)   # no page or time limit
  ```

  - Pages can share one content stream, so the cost is pages × stream size, not file size.
  - **Dynamic test** (isolated backend, fake LLM): a 64 kB PDF with 400 pages, all pointing at one 300-line content stream. While it uploaded, a second user polled `GET /me`. Result:

    ```
    64 kB PDF, 400 pages sharing one stream -> 201 in 5.7s;
    other user's /me max latency 5.61s (median 0.003s, n=7)
    ```

  - The 10 MB limit allows about 150 times as many page objects, which means minutes of complete freeze per request. Uvicorn runs one worker, so SSE streams already in progress stall too.
- **Exploit:** Register an account, create a chat, then POST the crafted PDF in a loop. Nobody else gets an answer.
- **Confirmed:** dynamically, on the isolated backend.
- **Fix:** Effort S/M.
  - Cap pages and extracted text.
  - Parse off the event loop.
  - For a hard time limit, use a process pool. A thread does not stop on timeout and still contends for the GIL.

  ```python
  # documents.py
  MAX_PAGES, MAX_CHARS = 30, 60_000

  def pdf_text(data: bytes) -> str:
      reader = PdfReader(io.BytesIO(data))
      if len(reader.pages) > MAX_PAGES:
          raise ValueError("too many pages")
      out, size = [], 0
      for page in reader.pages:
          out.append(page.extract_text() or "")
          size += len(out[-1])
          if size > MAX_CHARS:
              break
      return "\n".join(out)[:MAX_CHARS]

  # chats.py
  text = await asyncio.wait_for(asyncio.to_thread(documents.pdf_text, data), timeout=15)
  ```

### H-2 No request body size limit: unauthenticated memory exhaustion

- **Severity:** High. CVSS 3.1 7.5 (`AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`).
- **Affected:**
  - `backend/src/backend/routers/chats.py:194-196`: the size is checked only after the full read.
  - Every JSON route: FastAPI buffers the whole body before validation.
  - `compose.yaml:8`: uvicorn is exposed directly, with no proxy in front.
- **Evidence:**

  ```python
  data = await request.body()
  if len(data) > MAX_UPLOAD:
      raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="File too large")
  ```

  - **Isolated backend:** a 60 MB upload returned `413 File too large`, but only after the whole body was buffered.
  - **Running stack, unauthenticated:** a 30 MB unterminated JSON body to `/auth/login` returned `422 {"detail": "JSON decode error"}` in 0.33 s. That error is only possible after the full body was read.
  - Uvicorn has no body limit, and the backend container's memory limit is 3.8 GiB (`docker stats`).
  - Compose has no `restart:` policy, so a killed backend stays down.
- **Exploit:** A few parallel multi-GB POSTs to `/auth/login`, with no account needed, get the backend OOM-killed and it stays down.
- **Confirmed:** dynamically that bodies are buffered without a limit. The OOM outcome is inferred (no load testing).
- **Fix:** Effort S.
  - Reject oversized requests before reading them: check `Content-Length`, and count the bytes for chunked requests.
  - In production, also set a reverse-proxy limit (for nginx, `client_max_body_size 11m`).

  ```python
  # chats.py: stream the upload instead of request.body()
  data = bytearray()
  async for chunk in request.stream():
      data += chunk
      if len(data) > MAX_UPLOAD:
          raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="File too large")

  # app.py: cheap global guard for JSON routes (chunked bodies need a pure ASGI byte counter)
  @app.middleware("http")
  async def limit_body(request, call_next):
      limit = MAX_UPLOAD if request.url.path.endswith("/documents") else 64 * 1024
      if int(request.headers.get("content-length") or 0) > limit:
          return error_response(413, "Request too large")
      return await call_next(request)
  ```

### M-1 Dev stack published on all network interfaces

- **Severity:** Medium, on likelihood × impact.
  - Likelihood: likely on a shared venue or hackathon Wi-Fi.
  - Impact: H-1, H-2, M-2 and M-3 become reachable by anyone on the network, with no foothold needed.
- **Affected:** `compose.yaml:8-10`, `compose.yaml:18`, `compose.yaml:21-22`, `frontend/vite.config.ts:14`
- **Evidence:**
  - **Docker binds both ports to all interfaces.** `docker ps` shows `0.0.0.0:5173->5173/tcp` and `0.0.0.0:8000->8000/tcp`, and `lsof` shows `TCP *:8000 (LISTEN)` and `TCP *:5173 (LISTEN)`. The host's LAN IP is `192.168.0.17`.
  - **The frontend is the Vite dev server** (`npm run dev -- --host`) with `vite-plugin-vue-devtools`. These all answer 200: `/__devtools__/`, `/__open-in-editor?file=package.json` and raw sources such as `/vite.config.ts`.
  - **The backend exposes its API docs.** `/docs` and `/openapi.json` both answer 200.
  - **The backend has no Host check.** A request with `Host: evil.example` gets 200, while Vite correctly answers 403. DNS rebinding from a web page can therefore reach a backend that is only on localhost. Only unauthenticated routes are at risk, since the token lives in another origin's storage.
- **Exploit:** Someone at the venue opens `http://192.168.0.17:5173`, or scripts `:8000` directly, registers, and runs H-1, H-2 or M-2.
- **Confirmed:** dynamically.
- **Fix:** Effort S.

  ```yaml
  ports:
    - "127.0.0.1:8000:8000"
  # ...
    - "127.0.0.1:5173:5173"
  ```

  For production:
  - Build the frontend and serve the static files behind a reverse proxy with TLS, body limits and headers. Don't publish the backend port at all.
  - Use `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` and `TrustedHostMiddleware`.

### M-2 Unbounded LLM usage: cost and quota exhaustion

- **Severity:** Medium. CVSS 3.1 6.5 (`AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H`): it hits the LLM's availability for all users, and money.
- **Affected:**
  - `backend/src/backend/routers/chats.py:206`: the whole letter text.
  - `backend/src/backend/llm.py:153-167`: no timeout and no retry setting.
  - `backend/src/backend/routers/chats.py:142-169`: no rate limit.
  - `backend/src/backend/routers/auth.py:20-32`: open registration.
- **Evidence:**
  - **The letter text has no cap.** The fake LLM recorded the length of what reached `llm.recommendations()`:

    | PDF | Characters sent to the LLM |
    |---|---|
    | 57 kB, one page | 1,388,890 |
    | 64 kB, from H-1 | 8,116,399 |

    That is beyond any model context. Up to the context limit, every upload is one maximum-size request against the team's TPM quota.
  - **Each text message can trigger up to five LLM calls:**
    - `extract`;
    - `title` (first message only);
    - `intro`;
    - `scripts` (up to two attempts).

    Each call allows `max_completion_tokens=4000`. Chip answers also run `intro` and `scripts` whenever a plan gets built.
  - **Nothing limits usage.** There is no per-user or global rate limit, no cap on parallel SSE streams and no quota. Registration needs no email verification and no CAPTCHA.
  - **The client keeps library defaults.** `AsyncOpenAI(...)` is created without `timeout` or `max_retries`, so it uses a 10-minute timeout and 2 retries. A slow upstream holds a stream and a DB session open that long.
- **Exploit:** A script registers accounts and loops uploads and messages in parallel. The real demo then gets 429s and the budget drains.
  - The default endpoint name (`aif-dvsv-dev-hackathon-01-...`) suggests a hackathon resource, possibly shared with other teams. **Needs verification.**
- **Confirmed:**
  - Dynamically: the character counts, through the fake LLM.
  - Inferred: the quota and cost impact.
- **Fix:** Effort S/M.
  - Cap the letter text, together with the page cap from H-1.
  - Add per-user limits. For the demo, an in-memory counter is enough, for example 20 LLM turns per hour and 5 uploads per day. Allow one active stream per user.
  - Set `AsyncOpenAI(timeout=30, max_retries=1)`.
  - Set a budget alert on the Azure resource.

  ```python
  text = documents.pdf_text(data)[:MAX_LETTER_CHARS]   # e.g. 60_000
  ```

### M-3 No brute-force protection, weak password policy

- **Severity:** Medium. CVSS 3.1 6.5 (`AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:L/A:N`). An account holds the SVNR, address and care-related chats.
- **Affected:**
  - `backend/src/backend/schemas.py:19`: `min_length=8`.
  - `backend/src/backend/routers/auth.py:35-40`.
  - `backend/src/backend/routers/users.py:11-14`: password change and account deletion are not throttled either.
  - `backend/src/backend/security.py:11`.
- **Evidence (dynamic):**
  - **Weak passwords pass.** Register with `12345678` gets 201, and so does `password`. The frontend requires 10 characters ("Mindestens 10 Zeichen"); the backend accepts 8, including the most common passwords.
  - **Guessing is free.** 15 wrong logins in a row all got 401, and the correct password right after got 200: no lockout, no delay, no 429.
  - **Login timing is uniform**, which is good: the median was 32 ms for an unknown email and 30 ms for a wrong password, thanks to `DUMMY_HASH`.
  - **Logins are a memory amplifier.** argon2-cffi defaults use 64 MiB per hash, and `login` runs in the 40-thread threadpool, so a login flood peaks at about 2.5 GiB.
- **Exploit:** Online guessing or credential stuffing against emails, which can be enumerated (L-4).
- **Confirmed:** dynamically.
- **Fix:** Effort S/M.
  - Set the backend minimum to 10 characters, and reject a short list of common passwords.
  - Throttle per IP and per account, for example 5 failures in 15 minutes, then 429 with backoff.
  - Limit parallel hashing with a semaphore.

  ```python
  Password = Annotated[str, Field(min_length=10, max_length=128)]
  ```

### M-4 Access tokens cannot be revoked

- **Severity:** Medium. CVSS 3.1 5.9 (`AV:N/AC:H/PR:N/UI:R/S:U/C:H/I:L/A:N`). It needs a stolen token first (a shared PC, XSS or a leak), but then a password change does not help.
- **Affected:** `backend/src/backend/security.py:28-47`, `backend/src/backend/routers/users.py:34-38`, `frontend/src/App.vue:26-29`
- **Evidence (dynamic):**
  - **Password changes don't revoke tokens.** The token was issued, `POST /me/password` returned 204, and then the old token still got 200 on `GET /me`; `GET /me/profile` still returned the SVNR.
  - **The same pre-change token later deleted the account** with `DELETE /me` (password required).
  - **Logout happens only on the client**, which removes the token from `localStorage`. The token stays valid until `exp`, 24 hours later (`JWT_EXPIRE_MINUTES=1440`).
- **Exploit:** A token copied from a shared library PC or a public terminal keeps working for a day after the victim logs out and changes the password.
- **Confirmed:** dynamically.
- **Fix:** Effort S.
  - Add a `token_version` integer per user and put it in the token as `ver`.
  - Compare it in `get_current_user`, and bump it on a password change and on "log out everywhere".
  - In production, use 1-2 h tokens.
  - `create_all` does not add columns to an existing table, so either `ALTER TABLE` manually or keep the field in a new table, as `profiles` does.

### M-5 Discharge letters and free text reach Azure OpenAI unredacted (GDPR Art. 9)

- **Severity:** Medium. This is a compliance gap that matters before production.
  - Likelihood: certain, with real users.
  - Impact: special-category health data and national identifiers go to a processor with no minimisation.
- **Affected:**
  - `backend/src/backend/routers/chats.py:206` and `llm.py:191-215`: the letter.
  - `llm.py:169-173`: `extract`, the raw message.
  - `llm.py:246-247`: `title`, the raw first message.
- **Evidence:** I traced every LLM call and what goes into it.

  | Call | Input | Personal data |
  |---|---|---|
  | `extract` | raw user message plus the corpus question | whatever the user types (names, SVNR, diagnoses) |
  | `title` | raw first message | same |
  | `recommendations` | full PDF text, uncapped | letters hold the patient's name and birth date, often the SVNR, diagnoses and medication |
  | `intro` | subject enum plus service titles and eligibility | none |
  | `scripts` | step ids, corpus items, placeholder names, enum facts (`scripts.llm_input`) | none |
  | `translate` (`scripts/translate.py`, build-time) | corpus and UI strings | none |

  - **The claim that profile data never goes to the LLM holds.** `ProfileData` is used only after generation, in `scripts.slot_values`, `render` and `plain`. No LLM input contains a profile field. `tests/test_scripts.py:128` covers the scripts input.
  - **The letter is the gap.** It is the most sensitive data in the app, and it is sent in full. Only confirmed recommendations are stored, which is good minimisation at rest, but there is none in transit.
  - **The endpoint is in Azure West Europe** (`-we-`), which is good.
- **Scenario:** This is not an attack. Uploading a real letter in the demo sends real patient data to the hackathon's Azure resource.
- **Confirmed:** by code tracing.
- **Fix:** Effort M.
  - **For the demo:** use synthetic letters only.
  - **Before production:**
    - Run a DPIA, and sign processor terms with Microsoft.
    - Get explicit consent at upload (Art. 9(2)(a)).
    - Check the Azure OpenAI abuse-monitoring retention, and apply for modified abuse monitoring.
    - Redact before sending, and cap the text. Apply the quote check (`documents.checked`) to the same redacted text.

  ```python
  SVNR = re.compile(r"\b\d{4}\s?\d{2}\s?\d{2}\s?\d{2}\b")
  DATE = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}\b")
  def redact(text: str) -> str:
      return DATE.sub("[Datum]", SVNR.sub("[SVNR]", text))
  ```

### L-1 Deleted data stays in the SQLite file, and the SVNR is stored in plaintext

- **Severity:** Low. An Art. 17 issue at the file level; it needs access to the DB file.
- **Affected:** `backend/src/backend/database.py:10`, `backend/src/backend/models.py:37`, `backend/src/backend/routers/users.py:41-45`
- **Evidence (isolated DB):**

  ```
  before delete: {'users': 2, 'profiles': 1, 'chats': 2, 'messages': 18, 'chat_facts': 6, 'plans': 1, 'step_states': 1}
  after delete:  {'users': 1, 'profiles': 0, 'chats': 0, 'messages': 0, 'chat_facts': 0, 'plans': 0, 'step_states': 0}
  deleted SVNR bytes still in the db file: True | deleted name: True
  ```

  - `PRAGMA secure_delete` is 0 and `foreign_keys` is 0.
  - On the host, `backend/zetta.db` is `-rw-r--r--` (world-readable) and unencrypted.
- **Confirmed:** dynamically.
- **Fix:** Effort S.
  - Turn on `secure_delete`, and run `VACUUM` after deletions.
  - `chmod 600` the DB file.
  - In production, use an encrypted volume or a managed DB.
  - Consider not storing the SVNR on the server at all.

  ```python
  @event.listens_for(engine, "connect")
  def _pragmas(dbapi_conn, _):
      dbapi_conn.execute("PRAGMA secure_delete=ON")
      dbapi_conn.execute("PRAGMA foreign_keys=ON")
  ```

### L-2 No security headers, no CSP, the app can be framed

- **Severity:** Low. There is no XSS sink today (see L-3), so this is defence in depth, plus clickjacking.
- **Affected:** `backend/src/backend/app.py:21-27`, the Vite dev server, `frontend/index.html:11-24` (an inline script)
- **Evidence:**
  - The backend sends only `server`, `content-type` and `vary`. The frontend sends only `Vary`, `Content-Type` and `Cache-Control`.
  - No CSP, no `X-Frame-Options` or `frame-ancestors`, no `nosniff`, no `Referrer-Policy`.
  - No TLS anywhere.
- **Scenario:** A page frames the app and tricks a logged-in user into deleting a chat, which takes two clicks. Account deletion is safe because it needs the password.
- **Confirmed:** dynamically (headers).
- **Fix:** Effort S, for production. Serve the built frontend with headers. Either hash the `applyView` script or move it into a file.

  ```
  Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-<applyView>'; style-src 'self';
    connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  ```

### L-3 JWT stored in `localStorage`

- **Severity:** Low.
  - Likelihood: low. I found no XSS path; what remains is a compromised dependency or a browser extension.
  - Impact: high if it happens. It means 24 h of access, no revocation (M-4), and the SVNR and chats readable.
- **Affected:** `frontend/src/auth.ts:21-23`, `frontend/src/auth.ts:53`
- **Evidence:**
  - **There is one `v-html`:** `ChatApp.vue:481`, which renders DOMPurify output for assistant `text` messages only. The current pipeline never creates those.
  - **Everything else renders through `{{ }}`:** titles, names, profile fields, filenames, letter quotes and translations.
  - **Browser test on the running stack:**
    - Inputs: the chat title `"><svg onload=alert(1)><img src=x onerror=alert(2)>`, the display name `<img src=x onerror=alert('dn')>`, and the full name `<script>alert(3)</script><img src=x onerror=alert(4)>`.
    - Result: `img[src=x]` matched 0 elements and `[onload],[onerror]` matched 0. The payloads appear as escaped text.
- **Confirmed:** dynamically (no XSS). The risk rating is inferred.
- **Fix:** Effort M, for production. Use an httpOnly, `SameSite=Strict` cookie with CSRF protection, or a short-lived in-memory token with a refresh cookie. Keep a CSP (L-2).

### L-4 Account enumeration through registration

- **Severity:** Low.
  - Likelihood: medium.
  - Impact: low. It reveals that an email has an account with a care and social-insurance guide.
- **Affected:** `backend/src/backend/routers/auth.py:28-31`
- **Evidence:** Registering an existing email returns `409 {"detail": "Email already registered"}`; the check is case-insensitive (`SEC-TEST-A@...`). Login itself is uniform (401, same timing).
- **Confirmed:** dynamically.
- **Fix:** Effort M. Answer new and existing emails identically, and tell the owner by email. This needs email delivery; accept the risk for the demo.

### L-5 Google Fonts loaded from Google servers

- **Severity:** Low for the demo. Fix it before production: the court rulings below apply.
- **Affected:** `frontend/index.html:8-10`
- **Evidence:**
  - `<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3...">` sends every visitor's IP address and user agent to Google before any consent.
  - LG München I (3 O 17493/20, 20.01.2022) ruled that this violates the GDPR. Many Austrian warning letters in 2022 cited it.
- **Confirmed:** by code.
- **Fix:** Effort S. Self-host Source Sans 3 (woff2 in `frontend/public`, with `@font-face`), and remove the preconnects.

### L-6 Containers run as root with the backend source mounted read-write

- **Severity:** Low. It hardens H-2 and limits what a future RCE could do.
- **Affected:** `compose.yaml:3-8`, `compose.yaml:13-18`
- **Evidence:**
  - **Both containers run as root:** `id -u` returns 0 in each.
  - **The backend source is mounted read-write:** `bind /Users/fabian/sv-challenge/Zetta/backend -> /app rw=true`. That includes `.env` with the Azure key and `zetta.db`.
  - **Images are pinned by tag, not by digest.**
  - **`npm install` runs on every start, not `npm ci`.** It can rewrite the host's `package-lock.json`; another session's notes mention npm dropping the `libc` fields.
  - **There is no restart policy.**
- **Scenario:** Code execution in the backend, for example through a future pypdf bug, could change the source tree on the host and read the key.
- **Confirmed:** dynamically.
- **Fix:** Effort S.
  - Set `user: "1000:1000"`.
  - Mount the source read-only and keep the DB on its own volume.
  - Pass the secrets with `env_file: backend/.env` instead of the mount.
  - Use `npm ci`, pin image digests and set `restart: unless-stopped`.

### L-7 The LLM output filter misses some contact data

- **Severity:** Low. No attacker controls these prompts, so the only source is hallucination. The spec says "The LLM must never hallucinate contact info".
- **Affected:** `backend/src/backend/scripts.py:31-42` (`FORBIDDEN`), used for `intro` (`pipeline.py:255`) and for scripts (`scripts.py:118`)
- **Evidence:** I called `check_text` directly.

  | Text | Result |
  |---|---|
  | `Mehr unter bit.ly/pflege-hilfe` | ACCEPTED |
  | `Infos auf pflege.wien` | ACCEPTED |
  | `Siehe evil.io/x` | ACCEPTED |
  | `Rufen Sie null-sechs-sechs-vier an` | ACCEPTED |
  | `Siehe www.evil.at` | rejected (url) |
  | `Rufen Sie 0664 123 an` | rejected (phone) |

  User text never reaches these prompts: `intro` gets enum facts and corpus titles, and `scripts` gets corpus items and enum facts.
- **Confirmed:** dynamically, as a unit call.
- **Fix:** Effort S.
  - Use a generic domain pattern such as `\b[\w-]+\.[a-z]{2,}\b(/\S*)?` instead of the TLD list.
  - Flag runs of three or more German number words.
  - Add these strings to `tests/test_hallucination.py`.

### Info

- **I-1 The chat title is unvalidated LLM output** (`routers/chats.py:99-106`).
  - **Evidence:** With the fake LLM echoing the message, the stored title was `<img src=x onerror=alert(document.domain)> Rufen Sie sofort 0900 123 456 an: https://evil.example`. It rendered escaped.
  - **Why Info:** Only the user's own first message feeds the title, so this is self-injection. Still, it is the only LLM output that skips `check_text`.
  - **Fix:** Run `check_text`, and on failure fall back to the first words of the message.
- **I-2 Letter quotes have no maximum length** (`documents.py:30`).
  - **Evidence:** The only check is a minimum, `len(_norm(quote)) >= 10`. A prompt-injected letter can make the "quote" the whole letter, and it is then stored in `messages.payload` and `chat_facts.quote`.
  - **Why Info:** The enum and the verbatim check stop an injection from adding anything the letter does not already contain.
  - **Fix:** Cap a quote at about 300 characters.
- **I-3 A legacy `v-html` path** (`ChatApp.vue:85`, `ChatApp.vue:481`, `markdown.ts`).
  - **Evidence:** It uses DOMPurify 3.4.17 with default settings.
  - **Why Info:** No backend code creates assistant `text` messages any more.
  - **Fix:** Remove the path, or restrict `ALLOWED_TAGS`.
- **I-4 Misleading comments about LLM data.**
  - **Evidence:** `schemas.py:118` says the profile is "sent to the LLM". The profile handover note describes an `llm.build_messages` that sends profile fields; that function no longer exists.
  - **Why it matters:** Someone may "restore" it.
  - **Fix:** Correct the comment. Add one end-to-end test asserting that no profile value appears in any `FakeLlm.calls` input.
- **I-5 Public API docs** (`app.py:21`).
  - **Evidence:** `/docs`, `/redoc` and `/openapi.json` answer without a token.
  - **Fix:** Fine for the demo; disable them in production.
- **I-6 A plain-HTTP LLM endpoint in the example config** (`.env.example:12`).
  - **Evidence:** It suggests `http://192.168.1.51:9931/v1`.
  - **Risk:** With that endpoint, chat text and letters cross the venue network unencrypted.
  - **Fix:** Use it only on a trusted network, or through TLS or an SSH tunnel.
- **I-7 Gaps in git hygiene.**
  - **Evidence:**
    - There is no root `.gitignore`.
    - `frontend/.gitignore` does not cover `.env*`. Vite inlines `VITE_*` variables into the bundle, so a future `frontend/.env` with a key could be both committed and served publicly.
    - `.DS_Store` sits untracked in the root.
    - `JWT_SECRET` is checked for length (32 or more) but not for entropy.
  - **Fix:** Add the ignore entries.
- **I-8 No URL scheme check for doctor data** (`scripts/import_doctors.py:76`).
  - **Evidence:**
    - The import takes `source_url` from the scraped profile without a scheme check.
    - `tests/test_corpus.py:92` checks `https://` for institutions, documents, forms and services, but not for `doctors.json` or for `web` channel values used as `href`.
    - All 3002 doctor URLs are https today.
  - **Data protection:** Doctor names and addresses are personal data scraped from praxisplan.at, so check the source's terms and the legal basis before production.
  - **Fix:** Add a test.
- **I-9 GDPR housekeeping.**
  - **Evidence:**
    - There is no export endpoint (Art. 15 and 20); `/me/profile` plus the chat routes cover part of it.
    - Old chats are never deleted automatically (Art. 5(1)(e)).
    - Registration and upload show no privacy notice.
  - **Fix:** Plan these before production.

## 3. Demo vs production

**For the hackathon demo:**
- **M-1:** Bind to `127.0.0.1`, or demo from a hotspot only you use. This one change takes H-1, H-2, M-2 and M-3 off the network.
- **If other devices must reach the app** (jury phones): also do the H-1 page cap with `to_thread`, the H-2 body cap and the M-2 letter cap. Each is a few lines.
- **M-5:** Show synthetic discharge letters only, never a real one.
- **Can wait:** M-4, L-1 to L-6 and all Info items.

**Before any production use:**
- Everything above, plus a reverse proxy with TLS and limits, and a production frontend build.
- M-3: rate limits and the password policy.
- M-4: revocation and short-lived tokens.
- M-5: the full GDPR work (DPIA, consent, redaction, processor terms).
- L-1 to L-6.
- I-5 to I-9.

## 4. Checked and found fine

**Access control**
- Every chat route depends on `get_owned_chat`: messages, state, rename, delete, steps, send message, answers and documents.
- User B against user A's chat got 404 on all 8 routes, and B's chat list stayed empty.
- The 404 is the same as for a missing chat, so ids can't be probed. Chat ids are uuid4.
- The dependency runs before the body is read, so B's upload is refused before buffering.

**Mass assignment and input checks**
- `PUT /me/profile` with extra `user_id` and `email` fields: both were ignored. B's profile and A's email were unchanged.
- `StepUpdate` fields are whitelisted, and outcomes and checklist ids are checked against the plan.
- `AnswerRequest` is checked against the closed fact schema.

**JWT and passwords**
- HS256 is pinned in `decode`, and `exp` and `sub` are required.
  - An `alg=none` token got 401.
  - A token without `exp` got 401.
  - An HS512 token signed with the right key got 401.
- The secret is required (at least 32 characters) and has no default, so the backend refuses to start without it.
- A deleted user's token gets 401.
- argon2-cffi 25.1.0 runs with its RFC 9106 defaults (t=3, 64 MiB, p=4), and `DUMMY_HASH` evens out login timing.

**SQL injection and error messages**
- **No SQL injection:** all queries use the SQLAlchemy ORM or `select` with bound parameters. `literal_column` is used only with constant `rowid` strings.
- **Generic errors:** unhandled exceptions return a generic 500.
- **No input echo in validation errors:** a 200-character password returned only "password: String should have at most 128 characters", and truncated JSON returned "JSON decode error".

**CORS:** Only `http://localhost:5173` is allowed, without credentials. A preflight from another origin gets 400.

**LLM safety**
- **Contacts never come from the LLM.** Contacts, opening hours and addresses always come from the corpus (`contact_view`, `institution_view`).
- **Every output except the title is validated:**
  - `extract`: a strict JSON schema, and `merge()` keeps only valid enum values.
  - `intro`: `check_text`, at most 120 characters.
  - `scripts`: `validate()` checks coverage, placeholders, forbidden patterns and length, with a corpus fallback.
  - The letter: enum-constrained, with a verbatim quote check. Only confirmed items are stored, and the raw text is discarded.
- **Personal data stays out of the prompts.** It appears only as placeholders, filled in at render time. No profile field reaches any LLM call, and user text never reaches the `intro` or `scripts` prompts.

**Translations**
- They are built offline from public strings and checked by `problems()`: placeholders, numbers, and no new emails or URLs.
- They are committed for review and rendered as text.
- Locales load from a fixed `import.meta.glob` map, so a stored language code can't load arbitrary files.

**Frontend**
- No `v-html` on user or LLM content, apart from the DOMPurify path in I-3.
- `mailto:` links are built from the corpus address, with the subject and body run through `encodeURIComponent`. `tel:` links use corpus digits.
- The chat id from the URL hash is URL-encoded before it goes into a path (`chats.ts:162`); `/chats/..%2F..%2Fme/messages` got 404.
- No open redirect, since the hash is never used as a navigation target.
- External links set `rel="noopener noreferrer"`.

**Upload**
- A non-PDF gets 415 (prefix check) or 422 (pypdf fails to parse it).
- pypdf 6.21.4 caps decompression at 75 MB per stream.
- The filename is unquoted, cut to 100 characters and rendered as text.
- The PDF bytes are not stored.

**Account deletion:** The ORM cascade removes every row: profile, chats, messages, facts, plans and step states. The file residue is L-1.

**Secrets**
- **`backend/.env` is protected:** it is gitignored (`backend/.gitignore:8`) with mode 0600.
- **`generate_env.py` is sound:** it uses `secrets.token_hex(32)` and opens the file with `O_EXCL|0600`.
- **The real values appear nowhere else.** I searched without printing them. Neither `AZURE_OPENAI_API_KEY` (84 characters) nor `JWT_SECRET` is:
  - in any of the 45 commits or 583 objects;
  - in the working tree outside `.env`, including `frontend/dist` and the worktrees;
  - in the backend container logs, whose only error is a 401 `AuthenticationError` with no key fragment.
- **`llm_api_key` has `repr=False`.**
- **The regex scan of the history found nothing:** its 5 hits are all code such as `api_key=settings...`.

**Dependencies:** `npm audit` reported 0 vulnerabilities at every severity. `pip-audit` checked the 40 packages of the `uv.lock` export and found no known vulnerabilities.

**Vite dev server**
- `/@fs/etc/passwd` got 403.
- Traversal attempts fall back to the SPA page.
- The Host check is on: a foreign Host got 403.
- The container mounts only `./frontend`, so the backend `.env` can't be reached through it.

**Logging:** No log call writes message text, profile data or letter text, only step ids and error reasons.

## 5. Not covered

- **Live LLM behaviour against prompt injection**, since there were no Azure calls by design. I judged the robustness from the schema and validation code.
- **Azure limits:** the actual quota and TPM limits, and whether the resource is shared with other teams.
- **The devtools websocket:** the RPC that `vite-plugin-vue-devtools` exposes over the HMR websocket, which could include file read or write. It is reachable but I did not analyse it. **Needs verification.**
- **Load and OOM behaviour** beyond single 60 MB and 30 MB requests, since load testing was out of scope. The OOM outcome of H-2 is inferred.
- **A 10 MB-scale PDF bomb:** only the 64 kB amplification case ran.
- **Corpus contents:** whether the phone numbers and URLs are correct, beyond the scheme checks.
- **A legal review** of the GDPR points (legal basis, rules on using the SVNR, the DPIA).
- **The production frontend build:** `frontend/dist` exists, but compose does not serve it.
- **The settings-page work** in the other session's worktree.
