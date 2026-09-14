# Results folder layout & `results.json` schema

This is the contract between the test runner (`run_tests.py`, which you write) and
the report generator (`generate_report.py`). The harness writes this for you — you
normally don't construct `results.json` by hand — but understanding the shape helps
you write good tests and debug a run.

## Folder layout

Everything for one run lives in a single timestamped folder so results are never
mixed between runs and a half-finished run is still self-describing:

```
qa-results-YYYYMMDD-HHMM/
├── results.json        # structured results (written/flushed after every test case)
├── test-plan.md        # copy of the plan that was executed (you copy it here)
├── qa_harness.py       # copy of the harness so run_tests.py can import it
├── run_tests.py        # the runner you generated from the plan
├── screenshots/
│   ├── TC01_step01.png
│   ├── TC01_step02.png
│   └── ...
├── report.html         # produced by generate_report.py
└── report.pdf          # produced by generate_report.py  ← the deliverable
```

The harness flushes `results.json` after **each** test case completes, so if a run
crashes partway you can still generate a report for everything that finished.

## `results.json` schema

```jsonc
{
  "app_name": "Acme App",
  "generated_at": "2026-06-18T12:00:00",
  "summary": { "total": 12, "passed": 10, "failed": 2 },
  "watch_tables": ["users", "orders"],          // tables snapshotted for diffs (or null)
  "test_cases": [
    {
      "id": "TC01",
      "title": "User can register a new account",
      "category": "Authentication",            // optional grouping label
      "description": "Register via the signup form and land on the dashboard",
      "status": "passed",                        // "passed" | "failed"
      "started_at": "2026-06-18T12:00:01",
      "ended_at": "2026-06-18T12:00:05",
      "error": null,                             // case-level error if it aborted
      "checks": [                                // assertions from tc.check()/tc.require()
        { "description": "Lands on dashboard", "passed": true, "detail": null }
      ],
      "steps": [
        {
          "index": 1,
          "description": "Submit the registration form",
          "status": "passed",                    // "passed" | "failed"
          "screenshot": "screenshots/TC01_step01.png",   // path relative to the folder
          "api_calls": [
            {
              "method": "POST",
              "url": "http://localhost:8000/api/register",
              "status": 201,
              "request_body": { "email": "qa@example.com", "password": "***REDACTED***" },
              "response_body": { "id": 42, "email": "qa@example.com" }
            }
          ],
          "db_changes": {
            "users": {
              "added":    [ { "id": 42, "email": "qa@example.com" } ],
              "modified": [ { "before": { "...": "..." }, "after": { "...": "..." } } ],
              "deleted":  [],
              "note": "no primary key — modifications shown as add/delete"  // only when relevant
            }
          },
          "error": null,                         // step-level error if it failed
          "notes": null
        }
      ]
    }
  ]
}
```

### Field notes

- **status** is computed by the harness. A case is `failed` if any step raised, any
  `require()` failed, or any `check()` returned false. A step is `failed` if its body
  raised or a `require()`/`check()` failed while it was the current step.
- **api_calls** contains only XHR/`fetch` calls whose URL matched the session's
  `api_url_filter` (e.g. the backend base URL). Request/response bodies are parsed as
  JSON when possible, otherwise kept as text. Sensitive keys (`password`, `token`,
  `secret`, …) are masked — see `redact_keys` in the harness.
- **db_changes** is the diff of the watched tables between the start and end of the
  step. Empty `{}` means nothing changed. With a primary key, true modifications are
  detected; without one, only add/delete can be reported.
- **screenshot** is captured at the *end* of the step (the resulting state), or at the
  point of failure if the step raised.

## How the report uses this

`generate_report.py` reads `results.json`, embeds each screenshot as base64 (so the
HTML/PDF is self-contained and portable), and renders, per step: the screenshot, an
API panel per captured call (method · URL · status, request body, response body), and
a database-changes panel (added / modified / deleted rows), with a passed/failed badge
on every step and every case, plus a summary scorecard and contents table at the top.
