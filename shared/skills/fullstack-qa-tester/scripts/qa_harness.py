"""
qa_harness.py — capture toolkit for full-stack QA runs.

This module is the contract between the *test runner* (a `run_tests.py` you write
from the approved test plan) and the *report generator* (`generate_report.py`).
It does three things while a Playwright test executes:

  1. snapshots the test database before and after every step and diffs them,
  2. captures the request/response body of every API call made during a step,
  3. screenshots the page at the end of every step,

and writes it all to a single `results.json` (plus a `screenshots/` folder) that
`generate_report.py` turns into a PDF.

Design notes
------------
* No hard dependency on Playwright. The caller creates the browser/page and hands
  the page to `session.attach(page)`; this module only duck-types the page object.
  That keeps the database + diff logic importable and unit-testable on its own.
* Database drivers are imported lazily, only for the scheme actually used:
    postgresql:// -> psycopg2      (pip install psycopg2-binary)
    mysql://      -> pymysql       (pip install pymysql)
    sqlite://     -> sqlite3       (standard library)
    mongodb://    -> pymongo       (pip install pymongo)
* A failing step fails its test case but the suite keeps running, so one broken
  flow never sinks the whole report.

Typical use (see references/playwright-capture.md for the full pattern):

    from playwright.sync_api import sync_playwright
    from qa_harness import QASession

    session = QASession(
        app_name="Acme App",
        results_dir="qa-results-20260618-1200",
        db_url=os.environ["TEST_DB_URL"],
        watch_tables=["users", "orders"],
        api_url_filter="localhost:8000",     # only capture calls to the backend
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        session.attach(page)
        with session.test_case("TC01", "User can register", category="Auth") as tc:
            with tc.step("Open the registration page"):
                page.goto("http://localhost:3000/register")
            with tc.step("Submit a valid registration"):
                page.fill("#email", "qa@example.com")
                page.fill("#password", "Secret123!")
                page.click("button[type=submit]")
                page.wait_for_url("**/dashboard")
            tc.check("Lands on the dashboard", "/dashboard" in page.url)
        browser.close()
    session.finish()
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import traceback
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse, unquote


# --------------------------------------------------------------------------- #
# JSON-safe value coercion                                                     #
# --------------------------------------------------------------------------- #
def _jsonable(value):
    """Coerce a database value into something json.dumps can handle.

    Real databases return datetimes, Decimals, UUIDs, bytes, etc. Leaving those
    raw makes results.json unwritable and diffs unstable, so normalise here.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8")
        except Exception:
            return f"<{len(bytes(value))} bytes>"
    # Decimal, UUID, ObjectId, and anything else -> string form.
    return str(value)


def _row_to_jsonable(row):
    return {str(k): _jsonable(v) for k, v in dict(row).items()}


# --------------------------------------------------------------------------- #
# Database adapters (lazy-imported drivers)                                    #
# --------------------------------------------------------------------------- #
class DBAdapter:
    """Minimal read-only interface used for snapshotting.

    Subclasses implement list_tables / primary_keys / fetch_rows / close.
    Snapshots are read-only; this harness never writes to the database itself —
    the application under test is what mutates it.
    """

    def list_tables(self):
        raise NotImplementedError

    def primary_keys(self, table):
        raise NotImplementedError

    def fetch_rows(self, table, limit):
        raise NotImplementedError

    def close(self):
        pass

    def snapshot(self, tables=None, limit=2000):
        """Return {table: {"rows": [...], "key": [pk_cols] or None, "truncated": bool}}."""
        if tables is None:
            tables = self.list_tables()
        out = {}
        for t in tables:
            try:
                rows = self.fetch_rows(t, limit + 1)
            except Exception as exc:  # a missing/forbidden table shouldn't abort the run
                out[t] = {"rows": [], "key": None, "error": str(exc)}
                continue
            truncated = len(rows) > limit
            if truncated:
                rows = rows[:limit]
            try:
                key = self.primary_keys(t) or None
            except Exception:
                key = None
            out[t] = {
                "rows": [_row_to_jsonable(r) for r in rows],
                "key": key,
                "truncated": truncated,
            }
        return out


class _PostgresAdapter(DBAdapter):
    def __init__(self, url):
        import psycopg2
        import psycopg2.extras
        self._extras = psycopg2.extras
        self.conn = psycopg2.connect(url)
        self.conn.set_session(readonly=True, autocommit=True)

    def list_tables(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            )
            return [r[0] for r in cur.fetchall()]

    def primary_keys(self, table):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                "AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = %s::regclass AND i.indisprimary "
                "ORDER BY array_position(i.indkey, a.attnum)",
                (table,),
            )
            return [r[0] for r in cur.fetchall()]

    def fetch_rows(self, table, limit):
        with self.conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {table} LIMIT %s", (limit,))
            return cur.fetchall()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class _MySQLAdapter(DBAdapter):
    def __init__(self, url):
        import pymysql
        import pymysql.cursors
        self._pymysql = pymysql
        p = urlparse(url)
        self.conn = pymysql.connect(
            host=p.hostname or "localhost",
            port=p.port or 3306,
            user=unquote(p.username) if p.username else None,
            password=unquote(p.password) if p.password else None,
            database=p.path.lstrip("/") or None,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def list_tables(self):
        with self.conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            return [list(r.values())[0] for r in cur.fetchall()]

    def primary_keys(self, table):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
                "AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION",
                (table,),
            )
            return [r["COLUMN_NAME"] for r in cur.fetchall()]

    def fetch_rows(self, table, limit):
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}` LIMIT %s", (limit,))
            return cur.fetchall()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class _SQLiteAdapter(DBAdapter):
    def __init__(self, url):
        import sqlite3
        # Accept sqlite:///abs/path, sqlite://rel/path, or a bare filesystem path.
        if url.startswith("sqlite://"):
            path = url[len("sqlite://"):]
            if path.startswith("/"):
                path = path[1:] if not path.startswith("//") else path
            path = path or ":memory:"
        else:
            path = url
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def list_tables(self):
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [r[0] for r in cur.fetchall()]

    def primary_keys(self, table):
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        pks = [(r["pk"], r["name"]) for r in cur.fetchall() if r["pk"]]
        pks.sort()
        return [name for _, name in pks]

    def fetch_rows(self, table, limit):
        cur = self.conn.execute(f"SELECT * FROM {table} LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


class _MongoAdapter(DBAdapter):
    def __init__(self, url):
        from pymongo import MongoClient
        self.client = MongoClient(url)
        p = urlparse(url)
        dbname = p.path.lstrip("/").split("?")[0]
        if not dbname:
            raise ValueError(
                "MongoDB connection string must include a database name, "
                "e.g. mongodb://host:27017/mydb"
            )
        self.db = self.client[dbname]

    def list_tables(self):
        return sorted(self.db.list_collection_names())

    def primary_keys(self, table):
        return ["_id"]

    def fetch_rows(self, table, limit):
        return list(self.db[table].find().limit(limit))

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass


def get_adapter(url):
    """Pick a DBAdapter based on the connection-string scheme."""
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme in ("postgres", "postgresql", "postgresql+psycopg2"):
        return _PostgresAdapter(url)
    if scheme in ("mysql", "mariadb", "mysql+pymysql"):
        return _MySQLAdapter(url)
    if scheme.startswith("mongodb"):
        return _MongoAdapter(url)
    if scheme == "sqlite" or url.endswith(".db") or url.endswith(".sqlite") or url.endswith(".sqlite3"):
        return _SQLiteAdapter(url)
    raise ValueError(
        f"Unsupported database scheme '{scheme}'. Supported: postgresql, mysql, "
        f"sqlite, mongodb. Got: {url[:40]}..."
    )


# --------------------------------------------------------------------------- #
# Snapshot diffing                                                            #
# --------------------------------------------------------------------------- #
def diff_snapshots(before, after):
    """Diff two snapshots into {table: {"added":[], "modified":[], "deleted":[]}}.

    Only tables that actually changed are included. When a table has a primary
    key, rows are matched on it so genuine modifications are detected (recorded as
    {"before": {...}, "after": {...}}). Without a key we can only tell rows were
    added or removed, since there's no stable identity to match a modification.
    """
    result = {}
    tables = set(before) | set(after)
    for table in sorted(tables):
        b = before.get(table, {"rows": [], "key": None})
        a = after.get(table, {"rows": [], "key": None})
        key = a.get("key") or b.get("key")

        added, deleted, modified = [], [], []
        if key:
            def _k(row):
                return tuple(row.get(col) for col in key)

            bmap = {_k(r): r for r in b["rows"]}
            amap = {_k(r): r for r in a["rows"]}
            for k, row in amap.items():
                if k not in bmap:
                    added.append(row)
                elif row != bmap[k]:
                    modified.append({"before": bmap[k], "after": row})
            for k, row in bmap.items():
                if k not in amap:
                    deleted.append(row)
        else:
            # No primary key: identity is the whole row. Use a multiset so
            # duplicate rows are handled, then map serialized rows back to dicts.
            def _ser(row):
                return json.dumps(row, sort_keys=True, default=str)

            bcount = Counter(_ser(r) for r in b["rows"])
            acount = Counter(_ser(r) for r in a["rows"])
            for ser, n in (acount - bcount).items():
                added.extend([json.loads(ser)] * n)
            for ser, n in (bcount - acount).items():
                deleted.extend([json.loads(ser)] * n)

        if added or deleted or modified:
            entry = {"added": added, "deleted": deleted, "modified": modified}
            if not key:
                entry["note"] = "no primary key — modifications shown as add/delete"
            result[table] = entry
    return result


# --------------------------------------------------------------------------- #
# Network capture                                                             #
# --------------------------------------------------------------------------- #
def _safe_request_body(request):
    data = request.post_data
    if data is None:
        return None
    try:
        return json.loads(data)
    except Exception:
        return data  # form-encoded / plain text — keep as-is


# Keys whose values are masked in captured request/response bodies so secrets
# don't end up written to results.json or the PDF. Extend via QASession(redact_keys=...).
DEFAULT_REDACT_KEYS = {
    "password", "passwd", "pwd", "token", "access_token", "refresh_token",
    "secret", "client_secret", "authorization", "api_key", "apikey",
    "card_number", "cardnumber", "cvv", "cvc", "ssn",
}


def _redact(obj, keys):
    """Recursively replace values of sensitive keys with a mask."""
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if str(k).lower() in keys else _redact(v, keys))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v, keys) for v in obj]
    return obj


def _safe_response_body(response, max_chars):
    try:
        ctype = (response.headers or {}).get("content-type", "")
    except Exception:
        ctype = ""
    try:
        if "application/json" in ctype:
            return response.json()
        text = response.text()
        try:
            return json.loads(text)
        except Exception:
            return text[:max_chars] + ("…[truncated]" if len(text) > max_chars else "")
    except Exception as exc:
        # Redirects and some opaque responses have no readable body.
        return f"<body unavailable: {exc}>"


# --------------------------------------------------------------------------- #
# Recorders                                                                   #
# --------------------------------------------------------------------------- #
class _StepAbort(Exception):
    """Raised by require() to abort the rest of a test case after a hard failure."""


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


class StepRecorder:
    def __init__(self, case, description, wait_networkidle=True, networkidle_timeout=5000):
        self.case = case
        self.session = case.session
        self.description = description
        self.wait_networkidle = wait_networkidle
        self.networkidle_timeout = networkidle_timeout
        self.index = len(case.steps) + 1
        self._api_start = None
        self._db_before = None
        self.record = None

    def __enter__(self):
        self._api_start = len(self.session._api_buffer)
        self._db_before = self.session._db_snapshot()
        self.record = {
            "index": self.index,
            "description": self.description,
            "status": "passed",
            "screenshot": None,
            "api_calls": [],
            "db_changes": {},
            "error": None,
            "notes": None,
        }
        self.case.steps.append(self.record)
        return self

    def note(self, text):
        self.record["notes"] = (self.record["notes"] + "\n" + text) if self.record["notes"] else text

    def __exit__(self, exc_type, exc, tb):
        page = self.session.page
        failed = exc_type is not None

        # Give late XHRs a chance to land before we read the buffer / snapshot.
        if self.wait_networkidle and page is not None:
            try:
                page.wait_for_load_state("networkidle", timeout=self.networkidle_timeout)
            except Exception:
                pass

        # Screenshot the end state (or the failure state).
        if page is not None:
            shot_rel = f"screenshots/{self.case.id}_step{self.index:02d}.png"
            shot_abs = self.session.results_dir / shot_rel
            try:
                page.screenshot(path=str(shot_abs), full_page=self.session.screenshot_full_page)
                self.record["screenshot"] = shot_rel
            except Exception as e:
                self.note(f"screenshot failed: {e}")

        # API calls captured during this step's window.
        self.record["api_calls"] = list(self.session._api_buffer[self._api_start:])

        # Database diff, before vs after.
        db_after = self.session._db_snapshot()
        if self._db_before is not None and db_after is not None:
            try:
                self.record["db_changes"] = diff_snapshots(self._db_before, db_after)
            except Exception as e:
                self.note(f"db diff failed: {e}")

        if failed:
            self.record["status"] = "failed"
            if exc_type is _StepAbort:
                self.record["error"] = str(exc) or "step aborted by failed requirement"
            else:
                self.record["error"] = "".join(
                    traceback.format_exception_only(exc_type, exc)
                ).strip()
            self.case._fail(self.record["error"])
            # Let the exception propagate to the *test case* context manager, which
            # marks the case failed and swallows it so the rest of the suite runs.
            # This aborts the remaining steps of the current case — by design: once
            # a UI action throws, later steps that depend on it are unreliable. Use
            # tc.check() for a soft assertion that should NOT abort the case.
            return False
        return False


class TestCaseRecorder:
    def __init__(self, session, id, title, category=None, description=None):
        self.session = session
        self.id = id
        self.title = title
        self.category = category
        self.description = description
        self.status = "passed"
        self.error = None
        self.steps = []
        self.checks = []
        self.started_at = None
        self.ended_at = None

    def __enter__(self):
        self.started_at = _now()
        print(f"  ▶ {self.id}: {self.title}")
        return self

    def step(self, description, **kwargs):
        return StepRecorder(self, description, **kwargs)

    def _fail(self, reason=None):
        self.status = "failed"
        if reason and not self.error:
            self.error = reason
        # Reflect onto the current (last) step if one is open/most recent.
        if self.steps and self.steps[-1]["status"] != "failed":
            self.steps[-1]["status"] = "failed"
            if reason and not self.steps[-1]["error"]:
                self.steps[-1]["error"] = reason

    def check(self, description, condition, detail=None):
        """Soft assertion: records pass/fail and fails the case, but keeps going."""
        passed = bool(condition)
        self.checks.append({"description": description, "passed": passed, "detail": detail})
        mark = "✓" if passed else "✗"
        print(f"      {mark} {description}")
        if not passed:
            self._fail(f"check failed: {description}" + (f" ({detail})" if detail else ""))
        return passed

    def require(self, description, condition, detail=None):
        """Hard assertion: like check(), but aborts the rest of the case on failure."""
        passed = self.check(description, condition, detail)
        if not passed:
            raise _StepAbort(f"required check failed: {description}")
        return passed

    def __exit__(self, exc_type, exc, tb):
        self.ended_at = _now()
        if exc_type is _StepAbort:
            # Hard requirement failed outside a step block — already recorded.
            self.status = "failed"
            swallow = True
        elif exc_type is not None:
            self.status = "failed"
            if not self.error:
                self.error = "".join(traceback.format_exception_only(exc_type, exc)).strip()
            swallow = True  # keep the suite alive
        else:
            swallow = False
        print(f"    {'PASS' if self.status == 'passed' else 'FAIL'} — {self.id}")
        self.session._record_case(self)
        return swallow


class QASession:
    """Owns the database connection, the page's network capture, and results.json."""

    def __init__(
        self,
        app_name,
        results_dir,
        db_url=None,
        watch_tables=None,
        api_url_filter=None,
        screenshot_full_page=True,
        max_body_chars=20000,
        max_rows_per_table=2000,
        redact_keys=None,
    ):
        self.app_name = app_name
        self.results_dir = Path(results_dir)
        (self.results_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        self.watch_tables = watch_tables
        self.api_url_filter = api_url_filter
        self.screenshot_full_page = screenshot_full_page
        self.max_body_chars = max_body_chars
        self.max_rows_per_table = max_rows_per_table
        # Case-insensitive set of keys to mask in captured bodies.
        base = set(DEFAULT_REDACT_KEYS)
        if redact_keys:
            base |= {str(k).lower() for k in redact_keys}
        self.redact_keys = base

        self.page = None
        self._attached_pages = set()
        self._api_buffer = []
        self._cases = []

        self._adapter = None
        if db_url:
            try:
                self._adapter = get_adapter(db_url)
                print(f"  • connected to test database ({db_url.split('://',1)[0]})")
            except Exception as e:
                print(f"  ! could not connect to test database: {e}")
                print("    DB before/after capture will be skipped.")
                self._adapter = None

    # -- page / network -----------------------------------------------------
    def attach(self, page):
        """Attach network capture to a page. Call again after new_context()/new_page()."""
        self.page = page
        if id(page) not in self._attached_pages:
            page.on("response", self._on_response)
            self._attached_pages.add(id(page))

    def _on_response(self, response):
        try:
            req = response.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            if self.api_url_filter and self.api_url_filter not in req.url:
                return
            self._api_buffer.append({
                "method": req.method,
                "url": req.url,
                "status": response.status,
                "request_body": _redact(_safe_request_body(req), self.redact_keys),
                "response_body": _redact(
                    _safe_response_body(response, self.max_body_chars), self.redact_keys
                ),
            })
        except Exception:
            # Never let capture raise into the test.
            pass

    # -- database -----------------------------------------------------------
    def _db_snapshot(self):
        if self._adapter is None:
            return None
        try:
            return self._adapter.snapshot(self.watch_tables, limit=self.max_rows_per_table)
        except Exception as e:
            print(f"    ! db snapshot failed: {e}")
            return None

    # -- recording ----------------------------------------------------------
    def test_case(self, id, title, category=None, description=None):
        return TestCaseRecorder(self, id, title, category, description)

    def _record_case(self, case):
        self._cases.append({
            "id": case.id,
            "title": case.title,
            "category": case.category,
            "description": case.description,
            "status": case.status,
            "started_at": case.started_at,
            "ended_at": case.ended_at,
            "error": case.error,
            "checks": case.checks,
            "steps": case.steps,
        })
        self._write_results()  # flush after every case so a crash still yields a report

    def _summary(self):
        passed = sum(1 for c in self._cases if c["status"] == "passed")
        failed = sum(1 for c in self._cases if c["status"] == "failed")
        return {"total": len(self._cases), "passed": passed, "failed": failed}

    def _write_results(self):
        doc = {
            "app_name": self.app_name,
            "generated_at": _now(),
            "summary": self._summary(),
            "watch_tables": self.watch_tables,
            "test_cases": self._cases,
        }
        path = self.results_dir / "results.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    def finish(self):
        """Flush results and close the database connection. Returns the summary."""
        self._write_results()
        if self._adapter is not None:
            self._adapter.close()
        s = self._summary()
        print(f"\n  Done: {s['passed']}/{s['total']} passed, {s['failed']} failed")
        print(f"  Results written to {self.results_dir}/results.json")
        return s
