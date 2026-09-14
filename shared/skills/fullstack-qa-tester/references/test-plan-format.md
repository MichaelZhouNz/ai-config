# Test plan format (`test-plan.md`)

The plan is the bridge between *exploring the code* and *executing the tests*. Write it
so a competent tester (human or the Phase 2 runner) could execute each case without
re-reading the source. Every case needs concrete UI steps, the API call(s) you expect
each step to trigger, and the database rows you expect to change — those three are
exactly what gets captured and checked during execution.

## File structure

```markdown
# QA Test Plan — <App name>

## Application summary
<2–4 sentences: what the app does, the main flows, the frontend/backend stack, and how
they connect (e.g. "React SPA on :3000 calls a FastAPI backend on :8000; JWT in an
httpOnly cookie; Postgres").>

## Environment & assumptions
- Frontend URL: http://localhost:3000
- Backend URL: http://localhost:8000  (API base: /api)
- Test database: <type>, watched tables: users, orders, order_items, sessions
- Test accounts / seed data needed: <e.g. an existing user a@x.com / Password1!>
- Anything that must be true before running (migrations applied, server up, etc.)

## Coverage summary
<A short table: category → number of cases, so the reader sees the breadth at a glance.>

## Test cases
<One subsection per case, using the case template below. Number them TC01, TC02, …
and group them by category with `###` headings.>
```

## Per-case template

Use this exact shape for every case so the runner can translate it mechanically:

```markdown
### TC07 — Reject registration with an already-used email
- **Category:** Validation
- **Priority:** High
- **Preconditions:** A user `a@x.com` already exists.
- **Steps:**
  1. Navigate to `/register`.
  2. Fill email `a@x.com`, password `Password1!`, and submit.
- **Expected API:** `POST /api/register` returns `409` with an error message body.
- **Expected DB changes:** None — no new row in `users`.
- **Expected result / assertions:**
  - An inline error like "email already registered" is visible.
  - `users` row count is unchanged.
```

Keep steps as **observable UI actions** ("click the *Delete* button on the first row"),
not internal calls. The runner turns each step into Playwright actions and the harness
records what actually happened (screenshot + API + DB) so expected-vs-actual is visible
in the report.

## What to cover — category checklist

A full-stack app is more than its happy paths. Walk this list against the features you
found while exploring the code and generate cases wherever a row applies. Aim for
breadth; it's fine to mark a category "N/A for this app" in the plan.

- **Happy-path CRUD** — for every resource (user, order, product, comment, …): create,
  read/list, view detail, update, delete. One case per operation per resource.
- **Form validation** — required fields, type/format (email, phone, URL), min/max
  length, numeric ranges/boundaries, invalid combinations, client-side vs server-side
  enforcement (does the backend reject what the UI would block?).
- **Authentication** — login with valid creds, wrong password, unknown user, logout,
  session persistence across reload, expired/invalid session handling.
- **Authorization / access control** — a normal user accessing admin-only pages or
  another user's resource; acting on a record they don't own; hitting the API without
  auth. These often reveal the most serious bugs — include them.
- **Error handling** — backend 4xx/5xx surfaced to the user, 404 for missing records,
  duplicate/conflict (409), and how the UI behaves when an API call fails.
- **Edge cases & data integrity** — empty states (no data yet), very long input,
  special characters / unicode / emoji, duplicate submissions (double-click submit),
  relationships and cascades (deleting a parent with children), unique constraints.
- **Search / filter / sort / pagination** — empty results, filters that narrow
  correctly, sort order, page boundaries.
- **State transitions** — workflows with status (draft → submitted → approved; cart →
  order → shipped): valid transitions succeed, invalid ones are rejected.
- **Idempotency / concurrency** — resubmitting the same action, the back button after a
  mutation, two operations on the same record.

For each resulting case, decide which **watched tables** it touches so Phase 2 can snapshot
the right ones (snapshotting only relevant tables keeps the run fast and the diffs readable).

## Worked example (matches the runner pattern)

```markdown
### TC01 — User can register a new account
- **Category:** Authentication
- **Priority:** High
- **Preconditions:** No user with email `qa+new@example.com` exists.
- **Steps:**
  1. Navigate to `/register`.
  2. Fill email `qa+new@example.com` and password `Password1!`.
  3. Click **Sign up** and wait for the dashboard to load.
- **Expected API:** `POST /api/register` → `201`, body contains the new user id.
- **Expected DB changes:** one row added to `users` with that email; a row added to
  `sessions`.
- **Expected result / assertions:**
  - URL is `/dashboard`.
  - A welcome message naming the user is visible.
```

This is detailed enough that the Phase 2 runner can implement it directly (see
`references/playwright-capture.md` for how each case becomes a `with session.test_case(...)`
block). Always present the finished `test-plan.md` to the user and get explicit
confirmation before executing — running mutates the test database.
