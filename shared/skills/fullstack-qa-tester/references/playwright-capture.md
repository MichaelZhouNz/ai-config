# Writing `run_tests.py` with the capture harness

This is the how-to for Phase 2: turning the approved `test-plan.md` into a single
runnable `run_tests.py` that drives the app with Playwright while `qa_harness.py`
captures a screenshot, the API request/response, and the database diff for every
step. Read `results-schema.md` for the shape of what gets written, and
`test-plan-format.md` for where the test cases come from.

The golden rule: **`run_tests.py` is a faithful translation of the plan.** One
`with session.test_case(...)` per planned case, one `with tc.step(...)` per planned
step, in order. Don't invent coverage the plan didn't describe, and don't silently
drop cases — if a case turns out to be untestable, keep it and let it fail with a
clear error so it shows up in the report.

## The shape of a runner

```python
import os
from playwright.sync_api import sync_playwright
from qa_harness import QASession          # the copy sitting next to this file

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND = "http://localhost:3000"
BACKEND  = "localhost:8000"               # substring used to filter captured API calls

session = QASession(
    app_name="Acme App",
    results_dir=RESULTS_DIR,
    db_url=os.environ["TEST_DB_URL"],     # never hard-code the connection string
    watch_tables=["users", "orders", "order_items"],
    api_url_filter=BACKEND,               # only capture calls to the backend
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # ----- TC01 -----------------------------------------------------------
    ctx = browser.new_context()           # fresh cookies/storage per case → isolation
    page = ctx.new_page()
    session.attach(page)                  # re-attach capture to every new page
    with session.test_case("TC01", "User can register", category="Auth",
                           description="Register via the signup form") as tc:
        with tc.step("Open the registration page"):
            page.goto(f"{FRONTEND}/register")
        with tc.step("Submit a valid registration"):
            page.fill("#email", "qa+tc01@example.com")
            page.fill("#password", "Secret123!")
            page.click("button[type=submit]")
            page.wait_for_url("**/dashboard")
        tc.check("Lands on the dashboard", "/dashboard" in page.url)
        tc.check("Welcome message shows the email",
                 page.get_by_text("qa+tc01@example.com").is_visible())
    ctx.close()

    # ----- TC02 -----------------------------------------------------------
    ctx = browser.new_context()
    page = ctx.new_page()
    session.attach(page)
    with session.test_case("TC02", "Registration rejects a duplicate email",
                           category="Validation") as tc:
        with tc.step("Submit an email that already exists"):
            page.goto(f"{FRONTEND}/register")
            page.fill("#email", "existing@example.com")
            page.fill("#password", "Secret123!")
            page.click("button[type=submit]")
            page.wait_for_selector(".error")
        tc.check("Shows a validation error", page.locator(".error").is_visible())
        tc.check("Stays on the registration page", "/register" in page.url)

    browser.close()

session.finish()
```

That is the whole vocabulary: `QASession`, `session.attach(page)`,
`session.test_case(...)`, `tc.step(...)`, `tc.check(...)` / `tc.require(...)`, and
`session.finish()`. Everything else is ordinary Playwright.

## Before you run: get the app actually running

Captures are worthless if the app isn't up. Before writing assertions:

1. **Start the backend and the frontend** (or confirm they're already running). Use
   whatever the repos document — `npm run dev`, `uvicorn app:app`, `docker compose
   up`, etc. Note the real ports; don't assume 3000/8000.
2. **Confirm the URLs by hand.** `curl -sf http://localhost:3000` for the frontend
   and a known health/route on the backend. If the frontend talks to the backend
   through a dev proxy (e.g. CRA/Vite proxy), API calls may appear under the
   *frontend* origin — set `api_url_filter` to a path fragment like `/api` instead
   of a host in that case.
3. **Point `TEST_DB_URL` at the same database the running backend writes to.** If
   the backend uses one database and you snapshot another, every `db_changes` panel
   will be empty and you won't know why.

If you can't get the app running, stop and tell the user what's missing (a build
step, an env var, a service) rather than producing a report full of failures.

## Selectors: prefer stable, user-facing handles

Flaky selectors cause false failures. In rough order of preference:

- `page.get_by_role("button", name="Sign up")`, `get_by_label(...)`,
  `get_by_placeholder(...)`, `get_by_text(...)` — resilient and readable.
- `data-testid` hooks if the app has them: `page.get_by_test_id("submit")`.
- CSS/id selectors (`#email`, `.error`) when nothing better exists.
- Avoid deep structural selectors (`div > div:nth-child(3) > span`) — they break on
  any markup change.

When unsure what the selectors are, open the app and read the DOM (or grep the
frontend source for `id=`, `name=`, `data-testid=`, label text) before guessing.

## Waiting: the #1 cause of flake and empty captures

Playwright auto-waits for elements, but it does **not** know when *your* async work
finished. The harness already calls `wait_for_load_state("networkidle")` at the end
of each step (best-effort, 5s) so late XHRs land before it reads the API buffer and
snapshots the DB — but you still need to wait for the thing your assertion depends
on. Use explicit, intention-revealing waits:

```python
page.wait_for_url("**/dashboard")                 # navigation
page.wait_for_selector(".toast-success")          # element appears
page.get_by_role("row").wait_for()                # locator visible
page.wait_for_load_state("networkidle")           # network settles (extra safety)
```

Avoid `page.wait_for_timeout(...)` (arbitrary sleeps) except as a last resort — it's
both slow and unreliable.

**Put the action that triggers an API call inside the step that should capture it.**
The harness slices the API buffer to the window between a step's enter and exit, so
if you click in one step but the response only arrives after the next step opened,
the call lands in the wrong step. Keep each "do X → wait for its result" together in
one `with tc.step(...)` block.

## Assertions: `check` vs `require`

- `tc.check(description, condition, detail=None)` — **soft.** Records pass/fail,
  marks the case failed if false, and keeps going. Use it for most assertions so a
  single wrong expectation doesn't hide everything after it.
- `tc.require(description, condition, detail=None)` — **hard.** Same recording, but
  on failure it aborts the rest of *this* case (the suite continues). Use it for
  preconditions a later step genuinely can't proceed without (e.g. "login
  succeeded" before testing an authenticated page).

`condition` is evaluated by you and passed as a bool — compute it from the page or
the captured data:

```python
tc.check("API returned 201", any(c["status"] == 201 for c in []))   # see note below
tc.check("Error banner is visible", page.locator(".error").is_visible())
tc.require("Logged in", "/login" not in page.url, detail=page.url)
```

To assert on captured API calls or DB changes, the simplest path is to assert on the
**observable UI result** (the row appeared, the success toast showed, the URL
changed). The harness records the raw API/DB facts into the report regardless, so a
reviewer can see the request body and the inserted row next to your pass/fail. If you
do want to assert on them programmatically, capture the value yourself in the step
(e.g. read it via `page.request` or check the rendered table) rather than reaching
into the harness internals.

### A failing step still captures everything

When a step's body raises (a selector times out, `wait_for_url` fails), the harness
still screenshots the failure state, records the API calls and DB diff for that
window, marks the step and case failed, and then **aborts the remaining steps of
that case** — later steps usually depend on the one that broke, so running them
produces misleading noise. The next test case runs normally. This is why each case
gets its own `new_context()`: a broken case can't leak state into the next.

If you want a step to *expect* a failure (e.g. submitting bad input should show an
error, not throw), don't rely on an exception — drive the UI and assert with
`tc.check(...)` on the visible error, as in TC02 above.

## Authentication / login flows

If most cases need a logged-in user, the clean options are:

- **Log in at the start of each case** (most isolated, a little slower). A small
  helper keeps it tidy:

  ```python
  def login(page, email, password):
      page.goto(f"{FRONTEND}/login")
      page.fill("#email", email)
      page.fill("#password", password)
      page.click("button[type=submit]")
      page.wait_for_url("**/dashboard")
  ```

  Call it inside the first step of each authenticated case so the login itself is
  captured.

- **Reuse storage state** across cases when login is expensive and you accept shared
  auth: log in once, `state = ctx.storage_state()`, then
  `browser.new_context(storage_state=state)` for later cases. You still call
  `session.attach(page)` on each new page. Prefer per-case login unless runtime is a
  real problem — isolation is worth more than speed in a QA report.

Use distinct, disposable accounts/emails per case (`qa+tc01@…`, `qa+tc02@…`) so cases
don't collide in the database.

## Per-case isolation, concretely

```python
for case in cases:
    ctx = browser.new_context()
    page = ctx.new_page()
    session.attach(page)          # ← easy to forget; capture is silent without it
    with session.test_case(case.id, case.title, category=case.category) as tc:
        ...
    ctx.close()
```

`attach()` is idempotent per page and must be called for **every** new page, because
network capture is wired to that specific page's `response` event. A page you never
attached produces empty `api_calls` with no error — if a step's API panel is
mysteriously empty, a missing `attach()` is the first thing to check.

## Network-capture gotchas

- **Only XHR/`fetch` are captured.** Full-page form posts and document navigations
  are intentionally skipped (the harness checks `resource_type`). If the app submits
  forms the classic non-AJAX way, you'll see the DB change and the screenshot but no
  API panel — that's expected, not a bug.
- **Redirect and opaque responses** often have no readable body; the harness records
  a small placeholder instead of crashing.
- **`api_url_filter` is a substring match.** `"localhost:8000"` captures only the
  backend; `"/api"` captures by path (useful behind a dev proxy); `None` captures
  every XHR/fetch (noisy, but fine for small apps).
- **Bodies are truncated** at `max_body_chars` (default 20000) and **sensitive keys
  are redacted** (`password`, `token`, `secret`, …). Add app-specific secret field
  names via `QASession(redact_keys=[...])`.

## Headed vs headless, and debugging

- Default to **headless** (`p.chromium.launch(headless=True)`) for the real run.
- When a selector or flow misbehaves, debug with `headless=False`, or add
  `slow_mo=300` to watch it, or set `PWDEBUG=1` to open the inspector. Remove these
  before the final run.
- The screenshots in the report are your post-hoc debugger: a failed step's
  screenshot almost always shows why (an error banner, a blank page, the wrong
  route).
- Quick first pass: run just one case (comment out the rest, or guard with an env
  var) to confirm servers, selectors, the DB connection, and capture all work end to
  end before running the full suite.

## Troubleshooting checklist

| Symptom | Likely cause |
|---|---|
| All `db_changes` empty | `TEST_DB_URL` points at a different DB than the backend writes to; or `watch_tables` names are wrong |
| `api_calls` always empty | `session.attach(page)` missing on that page; or `api_url_filter` doesn't match the real API origin/path; or the app uses non-AJAX form posts |
| Every case fails on the first step | servers not running, wrong port, or wrong base URL |
| Intermittent failures | missing explicit wait; assert on a settled state, not mid-transition |
| Screenshot is blank/partial | navigated away before the step ended; screenshot is taken at step exit |
| `db snapshot failed` printed | DB driver not installed for the scheme, or the test user lacks read access to a watched table |

## What NOT to do

- **Never point `TEST_DB_URL` at a production database.** The suite creates,
  updates, and deletes real rows. Test/staging only. Refuse to run otherwise.
- **Never hard-code the connection string** in `run_tests.py`. Read it from the
  environment so it isn't written to disk or committed.
- **Don't skip `session.attach(page)`** after `new_context()`/`new_page()`.
- **Don't merge several planned steps into one** to "save time" — per-step capture is
  the whole point; one screenshot/diff per planned action.
- **Don't add sleeps instead of real waits**, and don't assert mid-transition.
- **Don't drop a planned test case** because it's awkward; keep it and let it fail
  visibly so the report stays honest about coverage.
