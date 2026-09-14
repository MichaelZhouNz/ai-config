#!/usr/bin/env python3
"""
generate_report.py — turn a QA results folder into a PDF report.

Reads `<results-dir>/results.json` (written by qa_harness.QASession) plus the
screenshots it references, builds a self-contained HTML report (screenshots are
embedded as base64 so the file is portable), and converts it to PDF.

The report shows, for every test case, each step with:
  * the screenshot taken at the end of the step,
  * every API call made during the step (method, URL, status, request body,
    response body),
  * the database rows that were added / modified / deleted during the step,
  * a passed / failed badge.

Usage:
    python generate_report.py <results-dir>
    python generate_report.py <results-dir> --title "Acme QA Run"
    python generate_report.py <results-dir> --html-only        # skip PDF conversion

PDF conversion order (first one available wins):
    1. Playwright Chromium  (already installed for the test run; recommended)
    2. WeasyPrint           (pip install weasyprint)
If neither is available the HTML is still written and the path is printed.
"""

import argparse
import base64
import html
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# Styling                                                                      #
# --------------------------------------------------------------------------- #
CSS = """
:root{
  --ink:#1c2230; --muted:#5b6675; --line:#e4e8ef; --bg:#ffffff;
  --pass:#0f9d58; --pass-bg:#e9f7ef; --fail:#d23f31; --fail-bg:#fdeceb;
  --accent:#3a4a63; --code-bg:#f6f8fb; --add:#0f9d58; --del:#d23f31; --mod:#b8860b;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact; print-color-adjust:exact}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink); margin:0; font-size:13px; line-height:1.5; background:var(--bg)}
.wrap{max-width:960px; margin:0 auto; padding:36px 30px}
code,pre{font-family:"SF Mono",ui-monospace,Menlo,Consolas,"Liberation Mono",monospace}

/* cover */
.cover{border-bottom:3px solid var(--accent); padding-bottom:22px; margin-bottom:26px}
.cover h1{font-size:26px; margin:0 0 4px}
.cover .sub{color:var(--muted); font-size:13px}
.scorecards{display:flex; gap:14px; margin-top:20px}
.card{flex:1; border:1px solid var(--line); border-radius:10px; padding:14px 16px; text-align:center}
.card .n{font-size:30px; font-weight:700; line-height:1}
.card .l{font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-top:6px}
.card.pass .n{color:var(--pass)} .card.fail .n{color:var(--fail)}

/* contents table */
.toc{width:100%; border-collapse:collapse; margin-top:24px}
.toc th,.toc td{text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-size:12.5px}
.toc th{color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.04em; font-size:10.5px}

/* badges */
.badge{display:inline-block; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:700;
  text-transform:uppercase; letter-spacing:.03em}
.badge.pass{color:var(--pass); background:var(--pass-bg)}
.badge.fail{color:var(--fail); background:var(--fail-bg)}

/* test case */
.case{border:1px solid var(--line); border-radius:12px; margin:22px 0; overflow:hidden;
  break-inside:avoid; page-break-inside:avoid}
.case.fail{border-color:#f1c3bd}
.case-head{display:flex; align-items:center; gap:12px; padding:13px 16px;
  background:var(--code-bg); border-bottom:1px solid var(--line)}
.case-head.fail{background:var(--fail-bg)}
.case-head .id{font-weight:700; color:var(--accent)}
.case-head .title{font-weight:600; flex:1}
.case-head .cat{font-size:11px; color:var(--muted); border:1px solid var(--line);
  padding:1px 8px; border-radius:20px; background:#fff}
.case-body{padding:6px 16px 14px}
.case-desc{color:var(--muted); font-size:12.5px; margin:8px 0 4px}
.case-error{background:var(--fail-bg); border:1px solid #f1c3bd; border-radius:8px;
  padding:8px 11px; margin:8px 0; color:#8a2b22; font-size:12px; white-space:pre-wrap}

/* step */
.step{border-top:1px dashed var(--line); padding:14px 0; break-inside:avoid; page-break-inside:avoid}
.step:first-child{border-top:none}
.step-head{display:flex; align-items:center; gap:9px; margin-bottom:9px}
.step-num{font-size:11px; font-weight:700; color:#fff; background:var(--accent);
  width:22px; height:22px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center}
.step-desc{font-weight:600; flex:1}

.shot{margin:8px 0; border:1px solid var(--line); border-radius:8px; overflow:hidden}
.shot img{display:block; width:100%}
.shot .ph{padding:18px; text-align:center; color:var(--muted); font-size:12px; background:var(--code-bg)}

.section-label{font-size:10.5px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); font-weight:700; margin:12px 0 6px}

/* api */
.api{border:1px solid var(--line); border-radius:8px; margin:7px 0; overflow:hidden}
.api-line{display:flex; align-items:center; gap:8px; padding:7px 10px; background:var(--code-bg);
  font-size:12px; border-bottom:1px solid var(--line)}
.method{font-weight:700; font-family:inherit; padding:1px 7px; border-radius:4px; background:#e6ebf3; color:var(--accent)}
.url{font-family:"SF Mono",ui-monospace,Menlo,monospace; word-break:break-all; flex:1; font-size:11.5px}
.status{font-weight:700; font-family:inherit}
.status.ok{color:var(--pass)} .status.err{color:var(--fail)}
.kv{padding:8px 10px}
.kv .k{font-size:10.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:3px}
pre{background:var(--code-bg); border:1px solid var(--line); border-radius:6px; padding:8px 10px;
  margin:0 0 8px; font-size:11px; white-space:pre-wrap; word-break:break-word; max-height:360px; overflow:auto}

/* db changes */
.db-table{margin:7px 0}
.db-table .name{font-family:"SF Mono",ui-monospace,Menlo,monospace; font-weight:700; font-size:12px; margin-bottom:4px}
.chg{margin:4px 0 4px 2px; font-size:11px}
.chg .tag{font-weight:700; font-size:10px; text-transform:uppercase; letter-spacing:.04em; margin-right:6px}
.tag.add{color:var(--add)} .tag.del{color:var(--del)} .tag.mod{color:var(--mod)}
.arrow{color:var(--muted); padding:0 6px}
.none{color:var(--muted); font-size:12px; font-style:italic}
.foot{margin-top:30px; padding-top:12px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; text-align:center}
"""


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def esc(x):
    return html.escape(str(x), quote=True)


def pretty(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return str(value)


def img_data_uri(path: Path):
    try:
        raw = path.read_bytes()
    except Exception:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def render_api_call(call):
    status = call.get("status", "")
    ok = isinstance(status, int) and status < 400
    parts = ['<div class="api">']
    parts.append('<div class="api-line">')
    parts.append(f'<span class="method">{esc(call.get("method","?"))}</span>')
    parts.append(f'<span class="url">{esc(call.get("url",""))}</span>')
    parts.append(f'<span class="status {"ok" if ok else "err"}">{esc(status)}</span>')
    parts.append("</div>")
    parts.append('<div class="kv">')
    req = call.get("request_body")
    if req is not None:
        parts.append('<div class="k">Request body</div>')
        parts.append(f"<pre>{esc(pretty(req))}</pre>")
    resp = call.get("response_body")
    parts.append('<div class="k">Response body</div>')
    parts.append(f"<pre>{esc(pretty(resp)) if resp is not None else '<em>empty</em>'}</pre>")
    parts.append("</div></div>")
    return "".join(parts)


def render_db_changes(changes):
    if not changes:
        return '<div class="none">No database changes detected.</div>'
    out = []
    for table, c in changes.items():
        out.append('<div class="db-table">')
        out.append(f'<div class="name">{esc(table)}</div>')
        for row in c.get("added", []):
            out.append('<div class="chg"><span class="tag add">+ added</span>'
                       f"<pre>{esc(pretty(row))}</pre></div>")
        for m in c.get("modified", []):
            out.append('<div class="chg"><span class="tag mod">~ modified</span>'
                       f'<pre>{esc(pretty(m.get("before")))}'
                       f'\n— changed to —\n'
                       f'{esc(pretty(m.get("after")))}</pre></div>')
        for row in c.get("deleted", []):
            out.append('<div class="chg"><span class="tag del">− deleted</span>'
                       f"<pre>{esc(pretty(row))}</pre></div>")
        if c.get("note"):
            out.append(f'<div class="none">{esc(c["note"])}</div>')
        out.append("</div>")
    return "".join(out)


def render_step(step, results_dir: Path):
    badge = "pass" if step.get("status") == "passed" else "fail"
    out = ['<div class="step">']
    out.append('<div class="step-head">')
    out.append(f'<span class="step-num">{step.get("index","?")}</span>')
    out.append(f'<span class="step-desc">{esc(step.get("description",""))}</span>')
    out.append(f'<span class="badge {badge}">{step.get("status","")}</span>')
    out.append("</div>")

    if step.get("error"):
        out.append(f'<div class="case-error">{esc(step["error"])}</div>')

    # Screenshot
    shot = step.get("screenshot")
    out.append('<div class="shot">')
    uri = img_data_uri(results_dir / shot) if shot else None
    if uri:
        out.append(f'<img src="{uri}" alt="step screenshot">')
    else:
        out.append('<div class="ph">No screenshot captured for this step.</div>')
    out.append("</div>")

    # API calls
    out.append('<div class="section-label">API requests &amp; responses</div>')
    calls = step.get("api_calls", [])
    if calls:
        out.extend(render_api_call(c) for c in calls)
    else:
        out.append('<div class="none">No API calls captured during this step.</div>')

    # DB changes
    out.append('<div class="section-label">Database changes (before → after)</div>')
    out.append(render_db_changes(step.get("db_changes", {})))

    if step.get("notes"):
        out.append(f'<div class="case-desc">Notes: {esc(step["notes"])}</div>')

    out.append("</div>")
    return "".join(out)


def render_case(case, results_dir: Path):
    failed = case.get("status") != "passed"
    cls = "fail" if failed else ""
    out = [f'<div class="case {cls}">']
    out.append(f'<div class="case-head {cls}">')
    out.append(f'<span class="id">{esc(case.get("id",""))}</span>')
    out.append(f'<span class="title">{esc(case.get("title",""))}</span>')
    if case.get("category"):
        out.append(f'<span class="cat">{esc(case["category"])}</span>')
    out.append(f'<span class="badge {"fail" if failed else "pass"}">{esc(case.get("status",""))}</span>')
    out.append("</div>")
    out.append('<div class="case-body">')
    if case.get("description"):
        out.append(f'<div class="case-desc">{esc(case["description"])}</div>')
    if case.get("error"):
        out.append(f'<div class="case-error">{esc(case["error"])}</div>')
    steps = case.get("steps", [])
    if steps:
        out.extend(render_step(s, results_dir) for s in steps)
    else:
        out.append('<div class="none">No steps were recorded for this test case.</div>')
    out.append("</div></div>")
    return "".join(out)


def build_html(doc, results_dir: Path, title=None):
    s = doc.get("summary", {})
    title = title or f'QA Report — {doc.get("app_name","Application")}'
    rows = []
    for c in doc.get("test_cases", []):
        b = "pass" if c.get("status") == "passed" else "fail"
        rows.append(
            f'<tr><td>{esc(c.get("id",""))}</td><td>{esc(c.get("title",""))}</td>'
            f'<td>{esc(c.get("category") or "—")}</td>'
            f'<td><span class="badge {b}">{esc(c.get("status",""))}</span></td></tr>'
        )

    cases_html = "".join(render_case(c, results_dir) for c in doc.get("test_cases", []))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
  <div class="cover">
    <h1>{esc(title)}</h1>
    <div class="sub">Generated {esc(doc.get("generated_at",""))}
      &nbsp;·&nbsp; Application: {esc(doc.get("app_name",""))}</div>
    <div class="scorecards">
      <div class="card"><div class="n">{s.get("total",0)}</div><div class="l">Total cases</div></div>
      <div class="card pass"><div class="n">{s.get("passed",0)}</div><div class="l">Passed</div></div>
      <div class="card fail"><div class="n">{s.get("failed",0)}</div><div class="l">Failed</div></div>
    </div>
    <table class="toc">
      <thead><tr><th>ID</th><th>Test case</th><th>Category</th><th>Result</th></tr></thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan=4>No test cases.</td></tr>'}</tbody>
    </table>
  </div>
  {cases_html}
  <div class="foot">Full-stack QA report · {esc(doc.get("app_name",""))} · {esc(doc.get("generated_at",""))}</div>
</div></body></html>"""


# --------------------------------------------------------------------------- #
# PDF conversion                                                               #
# --------------------------------------------------------------------------- #
def html_to_pdf(html_path: Path, pdf_path: Path):
    """Try Chromium, then WeasyPrint. Returns the engine name or None."""
    # 1) Playwright Chromium (already present for the test run)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
            browser.close()
        return "playwright-chromium"
    except Exception as e:
        chromium_err = e

    # 2) WeasyPrint
    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return "weasyprint"
    except Exception as e:
        print(f"  ! Chromium PDF failed: {chromium_err}")
        print(f"  ! WeasyPrint PDF failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Generate a PDF QA report from a results folder.")
    ap.add_argument("results_dir", help="Folder containing results.json and screenshots/")
    ap.add_argument("--title", default=None, help="Report title")
    ap.add_argument("--html-only", action="store_true", help="Write HTML but skip PDF conversion")
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    results_json = results_dir / "results.json"
    if not results_json.exists():
        print(f"❌ {results_json} not found.")
        sys.exit(1)

    doc = json.loads(results_json.read_text())
    html_doc = build_html(doc, results_dir, title=args.title)

    html_path = results_dir / "report.html"
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"✅ HTML report: {html_path}")

    if args.html_only:
        return

    pdf_path = results_dir / "report.pdf"
    engine = html_to_pdf(html_path, pdf_path)
    if engine:
        print(f"✅ PDF report ({engine}): {pdf_path}")
    else:
        print("⚠️  Could not produce a PDF. The HTML report is complete and printable.")
        print("    Install a PDF engine, then re-run:")
        print("      playwright install chromium      # recommended")
        print("      # or: pip install weasyprint")


if __name__ == "__main__":
    main()
