---
name: fullstack-qa-tester
description: >-
  End-to-end QA tester for full-stack web applications, driven by Playwright.
  Use this when the user wants to QA, test, or validate a full-stack app that
  has both a frontend and a backend; when they ask for a test plan, test cases,
  an end-to-end or e2e test suite, an integration or regression run, or to "test
  my whole app" across UI, API, and database; or when they mention testing user
  flows against a real test database. Given frontend and backend project
  path(s), a description of how they connect, and a test database connection
  string, it explores the code, writes a detailed test-case plan to a Markdown
  file for approval, then after confirmation executes every case with Playwright
  — capturing a screenshot, the API request and response, and the database
  changes before and after each step — and produces a PDF report marking each
  step passed or failed. Test or staging databases only; never production.
license: For use within the owner's own projects.
---

# Full-stack QA tester

Act as a QA engineer for a full-stack web app. You explore the real codebase,
propose a thorough test plan, get the user's sign-off, then execute every case
end-to-end with Playwright while capturing — for **each step** — a screenshot,
the API request/response, and the database state before and after. The result is
a single PDF: each tested case, each step, its evidence, and a passed/failed mark.

The work runs in three phases with a hard stop between planning and execution:

1. **Explore & plan** — read the code, write `test-plan.md`, present it.
2. **Confirm** — the user approves (and edits) the plan before anything runs.
3. **Execute & report** — drive the app with Playwright, capture evidence, emit the PDF.

## ⚠️ Safety — read before doing anything

Executing the plan **mutates the database**: it creates, updates, and deletes
real rows, and it submits real forms and API calls against the running app.

- **Only ever use a test or staging database.** Before Phase 2, confirm with the
  user, in plain words, that the connection string points at a disposable test
  database — not production. If there's any doubt, do not run.
- **Never log, print, echo, or commit the connection string.** Pass it via an
  environment variable (`TEST_DB_URL`); the harness records only the DB *scheme*,
  never the full URL, and redacts secrets from captured request/response bodies.
- **Don't exfiltrate data.** Captured rows and payloads stay in the local results
  folder for the report. Don't send them anywhere.
- This skill needs no escalated permissions. It only reads the user's code,
  drives a browser locally, and reads/writes the test database the user pointed it at.

## Required inputs — gather these first

Ask for anything missing before you start exploring:

1. **Frontend project path(s)** — one or more directories. (e.g. a React/Vue/Next app.)
2. **Backend project path(s)** — one or more directories. (e.g. a FastAPI/Express/Rails API.)
3. **How they connect & work** — the base URLs/ports, how the frontend reaches the
   backend (direct origin, dev proxy, `/api` prefix), the auth model (cookie/JWT/session),
   and anything non-obvious about the main flows. This shapes both the plan and the runner.
4. **Test database connection string** — so you can read data, inspect it, and capture
   per-step changes. Supported schemes:
   - `postgresql://user:pass@host:5432/dbname`
   - `mysql://user:pass@host:3306/dbname`
   - `sqlite:///absolute/path/to/file.db` (or a path ending `.db`/`.sqlite`)
   - `mongodb://host:27017/dbname`

   Get it as an env var if possible. Confirm it's a **test** database (see Safety).

Also confirm the app can actually be started (commands, ports, required env). If you
can't run it, Phase 2 will only produce failures — surface that early.

## Setup / dependencies

Install once in the environment that will run the tests:

```bash
pip install playwright
playwright install chromium          # one-time browser download
# plus the driver for the database in use:
pip install psycopg2-binary          # postgresql
pip install pymysql                  # mysql
pip install pymongo                  # mongodb
# sqlite needs nothing — it's in the standard library
```

`generate_report.py` renders the PDF with the same Chromium you installed for tests
(WeasyPrint is used as a fallback if present). If neither is available it writes
`report.html` and prints how to finish — the run itself never fails for lack of a PDF engine.

## Phase 1 — Explore the code, then write the plan

1. **Explore both sides thoroughly.** Map the backend routes (methods, paths, request/
   response shapes, status codes, auth requirements) and the data model (tables/
   collections, keys, relationships, constraints). Map the frontend pages, forms,
   and the actions that call each endpoint. Use the connection description to tie UI
   actions to API calls to database effects.
2. **Inspect the test database** to ground the plan in reality: list the tables and
   note which ones each feature touches (these become the run's *watched tables*).
3. **Write `test-plan.md`** following **`references/test-plan-format.md`** exactly.
   Cover far more than happy paths — walk the category checklist there (CRUD,
   validation, auth, **authorization/access control**, error handling, edge cases &
   data integrity, search/filter/sort/pagination, state transitions, idempotency).
   Every case needs concrete UI steps, the API call(s) each step should trigger, the
   DB rows expected to change, and explicit pass/fail assertions.

Save the plan inside a fresh results folder named `qa-results-YYYYMMDD-HHMM/` (see
`references/results-schema.md` for the folder layout).

## Phase 2 — Confirm, then execute

**Stop and present `test-plan.md` to the user. Do not execute until they approve.**
Invite them to add, remove, or correct cases — they know the app's intent better than
the code reveals. Re-confirm the database is a test database here.

After approval, build and run the suite:

1. **Copy `scripts/qa_harness.py` into the results folder** so the runner can import it.
2. **Write `run_tests.py`** in the results folder by translating the approved plan
   mechanically — one `with session.test_case(...)` per case, one `with tc.step(...)`
   per step, in order. Follow **`references/playwright-capture.md`** for the full
   pattern: starting/confirming the servers, selector strategy, waiting correctly,
   `check` vs `require`, auth handling, and per-case isolation with `new_context()` +
   `session.attach(page)`.
3. **Run it** with the connection string in the environment:

   ```bash
   cd qa-results-YYYYMMDD-HHMM
   TEST_DB_URL="postgresql://user:pass@localhost:5432/app_test" python run_tests.py
   ```

   The harness captures each step's screenshot, API calls, and DB diff, and flushes
   `results.json` after **every** case — so even a crash mid-run leaves a usable report.

Do a quick one-case smoke run first (servers up, selectors right, DB connected, capture
working) before the full suite.

## Phase 3 — Generate and present the report

```bash
python /path/to/skill/scripts/generate_report.py qa-results-YYYYMMDD-HHMM
```

This reads `results.json`, embeds screenshots as base64 (the report is fully
self-contained), and writes `report.html` and `report.pdf` into the folder. The PDF is
the deliverable, in exactly the required format: per **tested case** → per **tested
step** → screenshot + API request/response + DB before/after → **passed/failed** badge,
with a summary scorecard and contents at the top.

Present `report.pdf` to the user. Give a one-line summary (e.g. "10/12 passed; 2 auth
cases failed") and offer to dig into any failure.

## What's in this skill

- `scripts/qa_harness.py` — the capture toolkit `run_tests.py` imports (DB snapshot/diff,
  network capture with redaction, screenshots, `results.json`). Copy it into each run.
- `scripts/generate_report.py` — turns a results folder into `report.html` + `report.pdf`.
- `references/test-plan-format.md` — how to write `test-plan.md` (structure, per-case
  template, category checklist). Read in Phase 1.
- `references/playwright-capture.md` — how to write `run_tests.py` with the harness
  (patterns, waiting, auth, isolation, gotchas, troubleshooting). Read in Phase 2.
- `references/results-schema.md` — the results folder layout and `results.json` schema.

## What NOT to do

- **Never run against a production database.** Test/staging only — the suite deletes
  and mutates rows. If unsure, stop and ask.
- **Never hard-code, log, print, or commit the connection string.** Use `TEST_DB_URL`.
- **Never execute the plan without explicit user confirmation.** The plan-then-confirm
  gate is mandatory.
- **Don't skip exploration** and write generic tests — the plan must reflect this app's
  actual routes, models, and flows.
- **Don't collapse multiple planned steps into one** — per-step capture (a screenshot,
  API, and DB diff for each action) is the whole point.
- **Don't drop awkward test cases** to make the run look greener — keep them and let
  failures show honestly.
- **Don't send captured data anywhere.** It stays in the local results folder.
