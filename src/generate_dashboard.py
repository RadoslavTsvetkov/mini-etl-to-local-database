"""Generates a self-contained HTML dashboard summarizing the collected
survey data: KPI tiles, score distribution, status/location/title
breakdowns, run history, and a sortable data table. No external
dependencies (no JS charting library, no CDN) -- plain inline SVG marks
plus a small vanilla-JS layer for hover tooltips and table sorting.

Chart styling follows the dataviz reference palette (validated for
colorblind safety and light/dark surface contrast): single categorical
hue for one-series breakdowns, an ordinal blue ramp for the ordered
score buckets, thin bars with a 4px rounded data-end, hairline axes.

Usage:
    python generate_dashboard.py [output_path]   # default: reports/dashboard.html
"""

import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

import config
from db.setup_db import get_connection

REPORTS_DIR = os.path.join(config.PROJECT_ROOT, "reports")


def _highest_report_number() -> int:
    highest = 0
    if os.path.isdir(REPORTS_DIR):
        for name in os.listdir(REPORTS_DIR):
            m = re.fullmatch(r"dashboard(\d+)\.html", name, re.IGNORECASE)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest


def next_output_path() -> str:
    """Reports are numbered and never overwritten: dashboard1.html,
    dashboard2.html, ... — each generation writes the next free number."""
    return os.path.join(REPORTS_DIR, f"dashboard{_highest_report_number() + 1}.html")


def latest_report_filename() -> str | None:
    """The newest existing dashboard<N>.html, or None if reports/ is empty.
    Used by `manage.py serve` (src/server.py) to know what to redirect '/' to."""
    highest = _highest_report_number()
    return f"dashboard{highest}.html" if highest else None


def _top_n(sql: str, n: int) -> str:
    """Portable "top N rows" -- SQLite uses trailing LIMIT, SQL Server uses
    a leading TOP after SELECT."""
    if config.DB_BACKEND == "sqlserver":
        return sql.replace("SELECT", f"SELECT TOP {n}", 1)
    return f"{sql} LIMIT {n}"


def _fetch_all(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def build_data(conn):
    total = _fetch_all(conn, "SELECT COUNT(*) FROM surveys")[0][0]
    opened = _fetch_all(conn, "SELECT COUNT(*) FROM surveys WHERE opened = 1")[0][0]
    errors = _fetch_all(conn, "SELECT COUNT(*) FROM surveys WHERE open_error IS NOT NULL")[0][0]
    scores = [r[0] for r in _fetch_all(conn, "SELECT score FROM surveys WHERE score IS NOT NULL")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    run_count = _fetch_all(conn, "SELECT COUNT(*) FROM etl_runs")[0][0]

    buckets = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100.001)]
    bucket_labels = ["0–19", "20–39", "40–59", "60–79", "80–100"]
    bucket_counts = [0] * len(buckets)
    for s in scores:
        for i, (lo, hi) in enumerate(buckets):
            if lo <= s < hi:
                bucket_counts[i] += 1
                break

    statuses = Counter(r[0] or "(unknown)" for r in _fetch_all(conn, "SELECT survey_status FROM surveys"))
    locations = Counter(r[0] or "(unknown)" for r in _fetch_all(conn, "SELECT location_name FROM surveys"))
    titles = Counter(r[0] or "(unknown)" for r in _fetch_all(conn, "SELECT survey_title FROM surveys"))

    runs = _fetch_all(
        conn,
        _top_n(
            """
            SELECT run_id, started_at, status, surveys_extracted, surveys_loaded,
                   surveys_duplicate, surveys_marked_opened, error_count
            FROM etl_runs ORDER BY run_id DESC
            """,
            10,
        ),
    )

    surveys = _fetch_all(
        conn,
        """
        SELECT survey_id, survey_title, location_name, submitted_at, score,
               survey_status, opened, fieldworker_name, campaign,
               fieldworker_login, location_store_id, client_or_form_id,
               attachments_count, workflow_step_id, loaded_at, opened_at,
               command_request_id, open_error, responses_json
        FROM surveys ORDER BY loaded_at DESC
        """,
    )

    # Per-survey detail payload embedded in the page for the Details modal.
    # Responses are compacted to [question_id, answer, comment] triples to
    # keep the (single-file) HTML as small as possible.
    details = {}
    for s in surveys:
        try:
            responses = json.loads(s[18]) if s[18] else []
        except (TypeError, ValueError):
            responses = []
        details[str(s[0])] = {
            "title": s[1], "location": s[2], "date": s[3], "score": s[4],
            "status": s[5], "opened": bool(s[6]), "fieldworker": s[7],
            "campaign": s[8], "login": s[9], "store_id": s[10],
            "client_or_form_id": s[11], "attachments": s[12],
            "workflow_step": s[13], "loaded_at": s[14], "opened_at": s[15],
            "request_id": s[16], "open_error": s[17],
            "responses": [
                [r.get("question_id"), r.get("answer_text"), r.get("comment")]
                for r in responses
                if isinstance(r, dict)
            ],
        }

    if config.DB_BACKEND == "sqlserver":
        source = f"SQL Server · {config.SQLSERVER_SERVER} / {config.SQLSERVER_DATABASE}"
    else:
        source = f"SQLite · {os.path.relpath(config.DB_PATH, config.PROJECT_ROOT)}"

    return {
        "total": total,
        "opened": opened,
        "errors": errors,
        "avg_score": avg_score,
        "scored_count": len(scores),
        "run_count": run_count,
        "bucket_labels": bucket_labels,
        "bucket_counts": bucket_counts,
        "statuses": statuses.most_common(8),
        "status_distinct": len(statuses),
        "locations": locations.most_common(8),
        "location_distinct": len(locations),
        "titles": titles.most_common(8),
        "title_distinct": len(titles),
        "runs": runs,
        "surveys": surveys,
        "details": details,
        "source": source,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _hbar_path(x: float, y: float, w: float, h: float) -> str:
    """Horizontal bar: square at the baseline (left), 4px rounded data-end."""
    r = min(4, w / 2, h / 2)
    return (
        f"M{x},{y} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} "
        f"v{h - 2 * r:.1f} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z"
    )


def _vbar_path(x: float, y_top: float, w: float, h: float) -> str:
    """Vertical bar: square at the baseline (bottom), 4px rounded cap."""
    r = min(4, w / 2, h / 2)
    return (
        f"M{x},{y_top + h:.1f} v-{h - r:.1f} a{r},{r} 0 0 1 {r},-{r} "
        f"h{w - 2 * r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - r:.1f} z"
    )


def _bar_chart_breakdown(counts: list[tuple], total: int) -> str:
    """Horizontal bars for a one-series categorical breakdown: one hue
    (categorical slot 1) for every bar -- the labels carry identity, color
    stays quiet. Value at the bar tip; full-row hover target."""
    if not counts:
        return "<p class='empty'>No data yet — run the pipeline first.</p>"
    max_count = max(c for _, c in counts) or 1
    bar_h, band, label_w, chart_w, right_pad = 18, 30, 170, 290, 56
    svg_h = len(counts) * band
    svg_w = label_w + chart_w + right_pad
    rows = []
    for i, (name, count) in enumerate(counts):
        y = i * band + (band - bar_h) / 2
        w = max(2, round((count / max_count) * chart_w))
        share = f"{count / total * 100:.0f}%" if total else ""
        label = name if len(name) <= 24 else name[:23] + "…"
        rows.append(
            f'<g class="row" data-tip-label="{_esc(name)}" data-tip-value="{count:,} · {share}">'
            f'<rect class="hit" x="0" y="{i * band}" width="{svg_w}" height="{band}" />'
            f'<text x="{label_w - 10}" y="{y + bar_h / 2 + 4}" text-anchor="end" class="axis-label">{_esc(label)}</text>'
            f'<path class="bar" d="{_hbar_path(label_w, y, w, bar_h)}" fill="var(--series-1)" />'
            f'<text x="{label_w + w + 7}" y="{y + bar_h / 2 + 4}" class="value-label">{count:,}</text>'
            f'</g>'
        )
    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" style="max-width:{svg_w}px" role="img">'
        f'<line x1="{label_w}" y1="0" x2="{label_w}" y2="{svg_h}" class="baseline" />'
        + "".join(rows)
        + "</svg>"
    )


def _bar_chart_scores(labels: list[str], counts: list[int]) -> str:
    """Columns for the score distribution. The buckets are ordered, so the
    fill steps through an ordinal ramp of the sequential blue (light->dark
    with score) -- ramp steps come from the validated reference palette."""
    if not counts or not any(counts):
        return "<p class='empty'>No score data yet.</p>"
    max_count = max(counts) or 1
    bar_w, band, chart_h = 24, 64, 132
    top_pad, base_y = 22, 22 + 132
    svg_w, svg_h = len(counts) * band, base_y + 26
    total = sum(counts)
    cols = []
    for i, (label, count) in enumerate(zip(labels, counts)):
        x = i * band + (band - bar_w) / 2
        h = max(2, round((count / max_count) * chart_h))
        y = base_y - h
        share = f"{count / total * 100:.0f}%" if total else ""
        cols.append(
            f'<g class="row" data-tip-label="Score {_esc(label)}" data-tip-value="{count:,} · {share}">'
            f'<rect class="hit" x="{i * band}" y="0" width="{band}" height="{svg_h}" />'
            f'<path class="bar" d="{_vbar_path(x, y, bar_w, h)}" fill="var(--ord-{i + 1})" />'
            f'<text x="{x + bar_w / 2}" y="{y - 7}" text-anchor="middle" class="value-label">{count:,}</text>'
            f'<text x="{x + bar_w / 2}" y="{base_y + 17}" text-anchor="middle" class="axis-label">{_esc(label)}</text>'
            f'</g>'
        )
    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" style="max-width:{svg_w + 60}px" role="img">'
        + "".join(cols)
        + f'<line x1="0" y1="{base_y}" x2="{svg_w}" y2="{base_y}" class="baseline" />'
        + "</svg>"
    )


# Status chips always pair a symbol with the word -- color never carries
# the state alone (colorblind/print safe).
_RUN_STATUS_CHIP = {
    "success": ("chip-good", "✓"),
    "partial": ("chip-warn", "⚠"),
    "failed": ("chip-bad", "✕"),
    "running": ("chip-muted", "…"),
}


def _run_status_chip(status: str) -> str:
    cls, icon = _RUN_STATUS_CHIP.get(status, ("chip-muted", ""))
    return f'<span class="chip {cls}">{icon} {_esc(status)}</span>'


# CSS/JS are plain strings (not f-strings) so braces stay literal.
_STYLE = """
<style>
  :root {
    --surface-1: #fcfcfb; --page: #f9f9f7; --text-primary: #0b0b0b;
    --text-secondary: #52514e; --text-muted: #898781; --grid: #e1e0d9;
    --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6;
    --ord-1: #86b6ef; --ord-2: #5598e7; --ord-3: #2a78d6; --ord-4: #1c5cab; --ord-5: #104281;
    --good: #006300; --warn: #8a5b00; --bad: #d03b3b;
    --good-bg: rgba(12,163,12,0.12); --warn-bg: rgba(250,178,25,0.16); --bad-bg: rgba(208,59,59,0.10);
    --row-hover: rgba(11,11,11,0.03);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface-1: #1a1a19; --page: #0d0d0d; --text-primary: #ffffff;
      --text-secondary: #c3c2b7; --text-muted: #898781; --grid: #2c2c2a;
      --baseline: #383835; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5;
      --ord-1: #9ec5f4; --ord-2: #6da7ec; --ord-3: #3987e5; --ord-4: #256abf; --ord-5: #184f95;
      --good: #0ca30c; --warn: #fab219; --bad: #e66767;
      --good-bg: rgba(12,163,12,0.16); --warn-bg: rgba(250,178,25,0.14); --bad-bg: rgba(230,103,103,0.14);
      --row-hover: rgba(255,255,255,0.04);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 32px 24px 48px; background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 1180px; margin: 0 auto; }
  header { margin-bottom: 24px; }
  h1 { font-size: 22px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .subtitle { color: var(--text-secondary); font-size: 13px; }
  .subtitle .sep { color: var(--text-muted); margin: 0 6px; }
  h2 { font-size: 14px; margin: 0 0 14px; color: var(--text-secondary); font-weight: 600; }
  h2 .count { color: var(--text-muted); font-weight: 400; }
  .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .tile {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px 12px;
  }
  .tile-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
  .tile-value { font-size: 28px; font-weight: 600; line-height: 1.1; }
  .tile-value.bad { color: var(--bad); }
  .tile-sub { font-size: 11px; color: var(--text-muted); margin-top: 6px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 14px; margin-bottom: 20px; }
  .card {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 18px 20px; overflow-x: auto;
  }
  .card.span { margin-bottom: 20px; }
  .axis-label { font-size: 11px; fill: var(--text-muted); }
  .value-label { font-size: 11px; fill: var(--text-secondary); font-variant-numeric: tabular-nums; }
  .baseline { stroke: var(--baseline); stroke-width: 1; }
  .empty { color: var(--text-muted); font-size: 13px; }
  svg .hit { fill: transparent; }
  svg g.row:hover .bar { filter: brightness(1.12); }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th, td { text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  th {
    color: var(--text-secondary); font-weight: 600; cursor: pointer; user-select: none;
    position: sticky; top: 0; background: var(--surface-1); z-index: 1;
  }
  th::after { content: "\\2195"; margin-left: 5px; color: var(--text-muted); opacity: 0; font-size: 10px; }
  th:hover::after { opacity: 0.7; }
  th.sort-asc::after { content: "\\2191"; opacity: 1; }
  th.sort-desc::after { content: "\\2193"; opacity: 1; }
  td { font-variant-numeric: tabular-nums; }
  tbody tr:hover td { background: var(--row-hover); }
  .chip {
    display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 11.5px; font-weight: 600;
  }
  .chip-good { color: var(--good); background: var(--good-bg); }
  .chip-warn { color: var(--warn); background: var(--warn-bg); }
  .chip-bad { color: var(--bad); background: var(--bad-bg); }
  .chip-muted { color: var(--text-muted); background: var(--row-hover); }
  .yes { color: var(--good); }
  .no { color: var(--text-muted); }
  .table-wrap { max-height: 70vh; overflow-y: auto; }
  th:empty { cursor: default; }
  th:empty::after { content: none; }
  #survey-tbody tr { cursor: pointer; }
  .empty-cell { text-align: center; color: var(--text-muted); padding: 26px 0; }
  .err-count { color: var(--bad); font-weight: 600; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; flex: none; }
  .seg-btn {
    font: inherit; font-size: 12px; padding: 7px 13px; background: transparent;
    border: none; border-right: 1px solid var(--border); color: var(--text-secondary); cursor: pointer;
  }
  .seg-btn:last-child { border-right: none; }
  .seg-btn:hover { background: var(--row-hover); }
  .seg-btn.active { background: var(--series-1); color: #fff; }
  #modal-nav { display: flex; gap: 6px; }
  #modal-nav button {
    font: inherit; font-size: 16px; line-height: 1; padding: 5px 11px; background: transparent;
    border: 1px solid var(--border); border-radius: 8px; color: var(--text-secondary); cursor: pointer;
  }
  #modal-nav button:hover:not(:disabled) { background: var(--row-hover); color: var(--text-primary); }
  #modal-nav button:disabled { opacity: 0.35; cursor: default; }
  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  .toolbar input[type=search] {
    flex: 1; min-width: 220px; max-width: 440px; padding: 8px 12px; font: inherit; font-size: 13px;
    color: var(--text-primary); background: var(--page); border: 1px solid var(--border);
    border-radius: 8px; outline: none;
  }
  .toolbar input[type=search]:focus { border-color: var(--series-1); }
  .toolbar .count { font-size: 12px; color: var(--text-muted); }
  .btn {
    font: inherit; font-size: 11.5px; font-weight: 600; color: var(--series-1);
    background: transparent; border: 1px solid var(--border); border-radius: 6px;
    padding: 2px 10px; cursor: pointer;
  }
  .btn:hover { background: var(--row-hover); border-color: var(--series-1); }
  .btn-danger { color: var(--bad); border-color: var(--bad); }
  .btn-danger:hover { background: var(--bad-bg); border-color: var(--bad); }
  .btn-danger:disabled { opacity: 0.5; cursor: default; }
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 20; display: none;
  }
  .modal-backdrop.open { display: flex; align-items: flex-start; justify-content: center; padding: 5vh 16px; }
  .modal-box {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
    max-width: 780px; width: 100%; max-height: 88vh; overflow-y: auto;
    padding: 22px 26px 26px; box-shadow: 0 12px 40px rgba(0,0,0,0.35);
  }
  .modal-head-row { display: flex; align-items: flex-start; gap: 12px; }
  #modal-title { font-size: 17px; font-weight: 600; margin: 0; flex: 1; }
  #modal-sub { font-size: 12.5px; color: var(--text-secondary); margin-top: 3px; }
  #modal-close {
    font: inherit; font-size: 18px; line-height: 1; color: var(--text-secondary);
    background: transparent; border: 1px solid var(--border); border-radius: 8px;
    padding: 5px 10px; cursor: pointer;
  }
  #modal-close:hover { color: var(--text-primary); background: var(--row-hover); }
  .meta-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 12px 20px; margin: 18px 0 6px;
  }
  .meta-item .k { font-size: 11px; color: var(--text-muted); }
  .meta-item .v { font-size: 13px; margin-top: 2px; overflow-wrap: anywhere; }
  .meta-item .v.error { color: var(--bad); }
  .resp-head { margin: 20px 0 4px; display: flex; align-items: baseline; gap: 10px; }
  .resp-head h4 { font-size: 13px; margin: 0; color: var(--text-secondary); }
  .resp-note { font-size: 11px; color: var(--text-muted); }
  .q-block { border-top: 1px solid var(--grid); padding: 10px 0; }
  .q-id { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 7px; }
  .answers { display: flex; flex-wrap: wrap; gap: 6px; }
  .answer-chip {
    font-size: 12px; padding: 2px 9px; border-radius: 6px;
    background: var(--row-hover); border: 1px solid var(--border);
  }
  .q-comment { font-size: 12px; color: var(--text-secondary); margin-top: 7px; font-style: italic; }
  .modal-box details { margin-top: 18px; }
  .modal-box summary { font-size: 12px; color: var(--text-secondary); cursor: pointer; }
  .modal-box pre {
    font-size: 11px; background: var(--page); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; overflow-x: auto; max-height: 300px; overflow-y: auto;
  }
  #filter-modal-title { font-size: 17px; font-weight: 600; margin: 0; flex: 1; }
  .filter-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px 16px; margin: 18px 0;
  }
  .filter-grid label { font-size: 11.5px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 4px; }
  .filter-grid input, .filter-grid select {
    font: inherit; font-size: 13px; padding: 6px 9px; color: var(--text-primary);
    background: var(--page); border: 1px solid var(--border); border-radius: 6px; outline: none;
  }
  .filter-grid input:focus, .filter-grid select:focus { border-color: var(--series-1); }
  .filter-grid .span-2 { grid-column: span 2; }
  #filter-preview { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
  #filter-preview-list { margin-top: 10px; max-height: 220px; overflow-y: auto; }
  .filter-preview-row {
    font-size: 12px; padding: 5px 0; border-bottom: 1px solid var(--grid);
    overflow-wrap: anywhere;
  }
  #filter-actions { margin-top: 18px; display: flex; justify-content: flex-end; }
  footer { margin-top: 24px; color: var(--text-muted); font-size: 12px; }
  footer code { font-size: 11px; }
  #tip {
    position: fixed; pointer-events: none; opacity: 0; z-index: 10;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
    padding: 7px 11px; box-shadow: 0 4px 14px rgba(0,0,0,0.18); transition: opacity 80ms;
  }
  #tip .tip-v { font-size: 14px; font-weight: 600; }
  #tip .tip-l { font-size: 11.5px; color: var(--text-secondary); margin-top: 1px; }
</style>
"""

_SCRIPT = """
<div id="tip"><div class="tip-v"></div><div class="tip-l"></div></div>
<div id="modal-backdrop" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div id="modal" class="modal-box">
    <div class="modal-head-row">
      <div style="flex:1">
        <h3 id="modal-title"></h3>
        <div id="modal-sub"></div>
      </div>
      <div id="modal-nav">
        <button id="modal-prev" aria-label="Previous survey" title="Previous survey (&#8592;)">&#8249;</button>
        <button id="modal-next" aria-label="Next survey" title="Next survey (&#8594;)">&#8250;</button>
      </div>
      <button id="modal-delete" class="btn btn-danger live-only" style="display:none" title="Permanently delete this survey">Delete</button>
      <button id="modal-close" aria-label="Close">&#10005;</button>
    </div>
    <div id="modal-body"></div>
  </div>
</div>
<div id="filter-modal-backdrop" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="filter-modal-title">
  <div class="modal-box">
    <div class="modal-head-row">
      <h3 id="filter-modal-title">Delete surveys by filter</h3>
      <button id="filter-modal-close" aria-label="Close">&#10005;</button>
    </div>
    <div class="filter-grid">
      <label>Title contains <input type="text" id="f-title" placeholder="e.g. Q3 Store Visit" /></label>
      <label>Location contains <input type="text" id="f-location" placeholder="e.g. Geneva" /></label>
      <label>Status contains <input type="text" id="f-status" placeholder="e.g. Completed" /></label>
      <label>Campaign contains <input type="text" id="f-campaign" /></label>
      <label>Fieldworker contains <input type="text" id="f-fieldworker" placeholder="name or login" /></label>
      <label>Opened
        <select id="f-opened"><option value="">Any</option><option value="yes">Yes</option><option value="no">No</option></select>
      </label>
      <label>Survey ID from <input type="number" id="f-id-min" placeholder="e.g. 10001" /></label>
      <label>Survey ID to <input type="number" id="f-id-max" placeholder="e.g. 10050" /></label>
      <label>Date from <input type="date" id="f-date-from" /></label>
      <label>Date to <input type="date" id="f-date-to" /></label>
      <label>Score min <input type="number" id="f-score-min" step="0.1" /></label>
      <label>Score max <input type="number" id="f-score-max" step="0.1" /></label>
    </div>
    <div id="filter-preview">
      <button id="filter-preview-btn" class="btn">Preview matches</button>
      <span id="filter-preview-count" class="count"></span>
    </div>
    <div id="filter-preview-list"></div>
    <div id="filter-actions">
      <button id="filter-delete-btn" class="btn btn-danger" disabled>Delete matching surveys…</button>
    </div>
  </div>
</div>
<script>
(function () {
  /* Delete / Clear-all only work when served by `manage.py serve` (there's
     a real server behind the page to change the database); a plain
     double-clicked file has no such backend. Toggle the two states first,
     before anything else, so there's no flash of the wrong controls. */
  var isLive = !!window.__DASHBOARD_LIVE__;
  document.querySelectorAll(".live-only").forEach(function (n) { n.style.display = isLive ? "" : "none"; });
  document.querySelectorAll(".static-only").forEach(function (n) { n.style.display = isLive ? "none" : ""; });

  function apiPost(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Dashboard-Token": window.__DASHBOARD_TOKEN__ || "" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok || !data.ok) throw new Error(data.error || ("Request failed (HTTP " + r.status + ")"));
        return data;
      });
    });
  }

  var tip = document.getElementById("tip");
  var tipV = tip.querySelector(".tip-v");
  var tipL = tip.querySelector(".tip-l");
  function move(e) {
    var pad = 14, r = tip.getBoundingClientRect();
    var x = e.clientX + pad, y = e.clientY + pad;
    if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function bindTip(node) {
    node.addEventListener("pointerenter", function (e) {
      tipV.textContent = node.dataset.tipValue;   /* textContent: labels are data, never HTML */
      tipL.textContent = node.dataset.tipLabel;
      tip.style.opacity = 1;
      move(e);
    });
    node.addEventListener("pointermove", move);
    node.addEventListener("pointerleave", function () { tip.style.opacity = 0; });
  }
  document.querySelectorAll("[data-tip-label]").forEach(bindTip);

  document.querySelectorAll("table.sortable thead th").forEach(function (th, _, ths) {
    if (!th.textContent.trim()) return;   /* the Details-button column doesn't sort */
    var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
    th.addEventListener("click", function () {
      var table = th.closest("table");
      var tbody = table.querySelector("tbody");
      var dir = th.classList.contains("sort-asc") ? -1 : 1;
      table.querySelectorAll("th").forEach(function (h) { h.classList.remove("sort-asc", "sort-desc"); });
      th.classList.add(dir === 1 ? "sort-asc" : "sort-desc");
      var rows = Array.prototype.slice.call(tbody.rows).filter(function (r) {
        return !r.classList.contains("empty-row");
      });
      rows.sort(function (a, b) {
        var av = a.cells[idx].textContent.trim(), bv = b.cells[idx].textContent.trim();
        var an = parseFloat(av.replace(/,/g, "")), bn = parseFloat(bv.replace(/,/g, ""));
        if (!isNaN(an) && !isNaN(bn)) return dir * (an - bn);
        return dir * av.localeCompare(bv);
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    });
  });

  /* ---- Survey search + opened filter ---- */
  var search = document.getElementById("survey-search");
  var searchCount = document.getElementById("search-count");
  var surveyTbody = document.getElementById("survey-tbody");
  if (search && surveyTbody) {
    var allRows = Array.prototype.slice.call(surveyTbody.rows);
    var rowText = allRows.map(function (row) {
      var parts = [];   /* skip the last cell: the Details button isn't data */
      for (var i = 0; i < row.cells.length - 1; i++) parts.push(row.cells[i].textContent);
      return parts.join(" ").toLowerCase();
    });
    var rowOpened = allRows.map(function (row) {
      return row.cells[6].textContent.indexOf("Yes") !== -1;
    });

    var emptyRow = document.createElement("tr");
    emptyRow.className = "empty-row";
    var emptyCell = document.createElement("td");
    emptyCell.colSpan = 10;
    emptyCell.className = "empty-cell";
    emptyCell.textContent = "No surveys match — clear the search or switch the filter.";
    emptyRow.appendChild(emptyCell);
    emptyRow.style.display = "none";
    surveyTbody.appendChild(emptyRow);

    var openedFilter = "all";
    var applyFilter = function () {
      var q = search.value.trim().toLowerCase();
      var shown = 0;
      allRows.forEach(function (row, idx) {
        var match = (!q || rowText[idx].indexOf(q) !== -1) &&
          (openedFilter === "all" || (openedFilter === "yes") === rowOpened[idx]);
        row.style.display = match ? "" : "none";
        if (match) shown++;
      });
      emptyRow.style.display = shown ? "none" : "";
      searchCount.textContent = shown === allRows.length
        ? allRows.length.toLocaleString() + " surveys"
        : shown.toLocaleString() + " of " + allRows.length.toLocaleString() + " surveys match";
    };
    applyFilter();
    search.addEventListener("input", applyFilter);
    document.querySelectorAll("#opened-filter .seg-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openedFilter = btn.dataset.filter;
        document.querySelectorAll("#opened-filter .seg-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        applyFilter();
      });
    });
  }

  /* ---- Details modal (all content built with textContent — data is untrusted) ---- */
  var DETAILS = {};
  var dataTag = document.getElementById("survey-data");
  if (dataTag) { try { DETAILS = JSON.parse(dataTag.textContent); } catch (e) {} }

  var backdrop = document.getElementById("modal-backdrop");
  var modal = document.getElementById("modal");
  var modalBody = document.getElementById("modal-body");
  var modalTitle = document.getElementById("modal-title");
  var modalSub = document.getElementById("modal-sub");
  var closeBtn = document.getElementById("modal-close");
  var prevBtn = document.getElementById("modal-prev");
  var nextBtn = document.getElementById("modal-next");

  /* Prev/next walks the surveys currently visible in the table, in its
     current sort order — so it navigates exactly what the reader filtered. */
  var navList = [], navIdx = -1;
  function computeNavList() {
    navList = [];
    if (!surveyTbody) return;
    Array.prototype.forEach.call(surveyTbody.rows, function (row) {
      if (row.style.display !== "none" && !row.classList.contains("empty-row")) {
        navList.push(row.cells[0].textContent.trim());
      }
    });
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null && text !== "") n.textContent = text;
    return n;
  }

  function metaItem(label, value, extraCls) {
    if (value === undefined || value === null || value === "") return null;
    var item = el("div", "meta-item");
    item.appendChild(el("div", "k", label));
    item.appendChild(el("div", "v" + (extraCls ? " " + extraCls : ""), String(value)));
    return item;
  }


  var currentSid = null;

  function openModal(sid, keepNav) {
    var d = DETAILS[sid];
    if (!d) return;
    currentSid = sid;
    if (!keepNav) computeNavList();
    navIdx = navList.indexOf(sid);
    prevBtn.disabled = navIdx <= 0;
    nextBtn.disabled = navIdx < 0 || navIdx >= navList.length - 1;

    modalTitle.textContent = d.title || "(untitled survey)";
    var pos = navIdx >= 0 ? " · " + (navIdx + 1).toLocaleString() + " of " + navList.length.toLocaleString() + " shown" : "";
    modalSub.textContent = "Survey ID " + sid + (d.date ? " · " + String(d.date).slice(0, 10) : "") + pos;
    modalBody.textContent = "";

    var grid = el("div", "meta-grid");
    [
      metaItem("Score", d.score),
      metaItem("Status", d.status),
      metaItem("Opened", d.opened ? "\\u2713 Yes" + (d.opened_at ? " (" + String(d.opened_at).slice(0, 19).replace("T", " ") + ")" : "") : "\\u2013 No"),
      metaItem("Location", d.location),
      metaItem("Store ID", d.store_id),
      metaItem("Campaign", d.campaign),
      metaItem("Fieldworker", d.fieldworker ? d.fieldworker + (d.login ? " (" + d.login + ")" : "") : d.login),
      metaItem("Attachments", d.attachments),
      metaItem("Workflow step", d.workflow_step),
      metaItem("Client / form ID", d.client_or_form_id),
      metaItem("Loaded at", d.loaded_at ? String(d.loaded_at).slice(0, 19).replace("T", " ") : null),
      metaItem("Command request", d.request_id),
      metaItem("Open error", d.open_error, "error")
    ].forEach(function (item) { if (item) grid.appendChild(item); });
    modalBody.appendChild(grid);

    var groups = {}, order = [];
    (d.responses || []).forEach(function (r) {
      var q = String(r[0] === null || r[0] === undefined ? "?" : r[0]);
      if (!groups[q]) { groups[q] = { answers: [], comments: [] }; order.push(q); }
      if (r[1] !== null && r[1] !== undefined && r[1] !== "") groups[q].answers.push(String(r[1]));
      if (r[2]) groups[q].comments.push(String(r[2]));
    });

    var head = el("div", "resp-head");
    head.appendChild(el("h4", null, "Responses \\u00b7 " + order.length + " question(s), " + (d.responses || []).length + " row(s)"));
    if (order.length) {
      head.appendChild(el("span", "resp-note", "a question may list several answer options, not only the one given (see SPECIFICATION \\u00a710.4)"));
    }
    modalBody.appendChild(head);

    if (!order.length) {
      modalBody.appendChild(el("p", "empty", "No response data stored for this survey."));
    } else {
      order.forEach(function (q) {
        var block = el("div", "q-block");
        block.appendChild(el("div", "q-id", "Question " + q));
        var answers = el("div", "answers");
        groups[q].answers.forEach(function (a) { answers.appendChild(el("span", "answer-chip", a)); });
        if (!groups[q].answers.length) answers.appendChild(el("span", "empty", "(no answer text)"));
        block.appendChild(answers);
        groups[q].comments.forEach(function (c) { block.appendChild(el("div", "q-comment", "\\u201c" + c + "\\u201d")); });
        modalBody.appendChild(block);
      });
    }

    var raw = el("details");
    raw.appendChild(el("summary", null, "Raw responses_json"));
    var pretty = (d.responses || []).map(function (r) {
      return { question_id: r[0], answer_text: r[1], comment: r[2] };
    });
    raw.appendChild(el("pre", null, JSON.stringify(pretty, null, 2)));
    modalBody.appendChild(raw);

    backdrop.classList.add("open");
    closeBtn.focus();
  }

  function closeModal() { backdrop.classList.remove("open"); }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".btn-details") : null;
    if (btn) openModal(btn.dataset.sid);
  });
  if (surveyTbody) {
    /* The whole row is a Details target, not just the button */
    surveyTbody.addEventListener("click", function (e) {
      if (e.target.closest(".btn-details")) return;   /* button handler covers it */
      var row = e.target.closest("tr");
      if (!row || row.classList.contains("empty-row")) return;
      openModal(row.cells[0].textContent.trim());
    });
  }
  function navStep(delta) {
    var target = navIdx + delta;
    if (navIdx < 0 || target < 0 || target >= navList.length) return;
    openModal(navList[target], true);
  }
  prevBtn.addEventListener("click", function () { navStep(-1); });
  nextBtn.addEventListener("click", function () { navStep(1); });

  var deleteBtn = document.getElementById("modal-delete");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      if (!currentSid) return;
      var d = DETAILS[currentSid];
      var label = currentSid + (d && d.title ? " — " + d.title : "");
      if (!window.confirm("Permanently delete survey " + label + "?\\n\\nA backup JSON is saved on the server first, but this cannot be undone from the dashboard.")) return;
      deleteBtn.disabled = true;
      apiPost("/api/delete-survey", { survey_id: currentSid })
        .then(function (data) { window.location = data.redirect || "/"; })
        .catch(function (e) { window.alert("Delete failed: " + e.message); deleteBtn.disabled = false; });
    });
  }

  var clearAllBtn = document.getElementById("clear-all-btn");
  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", function () {
      var total = Object.keys(DETAILS).length;
      if (!window.confirm("Permanently delete ALL " + total.toLocaleString() + " surveys?\\n\\nA backup JSON is saved on the server first, but this cannot be undone from the dashboard. This is a big deal — make sure you mean it.")) return;
      var typed = window.prompt('Type DELETE ALL (exact capitals) to confirm deleting all ' + total.toLocaleString() + ' surveys:');
      if (typed !== "DELETE ALL") { window.alert("Cancelled — text didn't match \\"DELETE ALL\\" exactly. Nothing was deleted."); return; }
      clearAllBtn.disabled = true;
      apiPost("/api/clear-surveys", { confirm: "DELETE ALL", expected_count: total })
        .then(function (data) { window.location = data.redirect || "/"; })
        .catch(function (e) { window.alert("Clear failed: " + e.message); clearAllBtn.disabled = false; });
    });
  }

  /* ---- Delete-by-filter modal (title/location/status/campaign/fieldworker,
     ID range, date range, score range, opened yes/no -- combined with AND) ---- */
  var filterBackdrop = document.getElementById("filter-modal-backdrop");
  var openFilterBtn = document.getElementById("open-filter-modal-btn");
  var filterCloseBtn = document.getElementById("filter-modal-close");
  var filterPreviewBtn = document.getElementById("filter-preview-btn");
  var filterDeleteBtn = document.getElementById("filter-delete-btn");
  var filterPreviewCount = document.getElementById("filter-preview-count");
  var filterPreviewList = document.getElementById("filter-preview-list");
  var lastPreviewTotal = null;
  var lastPreviewFilters = null;

  function fVal(id) { return document.getElementById(id).value.trim(); }

  function collectFilters() {
    var filters = {};
    if (fVal("f-title")) filters.title = fVal("f-title");
    if (fVal("f-location")) filters.location = fVal("f-location");
    if (fVal("f-status")) filters.status = fVal("f-status");
    if (fVal("f-campaign")) filters.campaign = fVal("f-campaign");
    if (fVal("f-fieldworker")) filters.fieldworker = fVal("f-fieldworker");
    if (fVal("f-id-min")) filters.id_min = parseInt(fVal("f-id-min"), 10);
    if (fVal("f-id-max")) filters.id_max = parseInt(fVal("f-id-max"), 10);
    if (fVal("f-date-from")) filters.date_from = fVal("f-date-from");
    if (fVal("f-date-to")) filters.date_to = fVal("f-date-to");
    if (fVal("f-score-min")) filters.score_min = parseFloat(fVal("f-score-min"));
    if (fVal("f-score-max")) filters.score_max = parseFloat(fVal("f-score-max"));
    var opened = document.getElementById("f-opened").value;
    if (opened) filters.opened = opened === "yes";
    return filters;
  }

  function resetFilterPreview() {
    lastPreviewTotal = null;
    lastPreviewFilters = null;
    filterDeleteBtn.disabled = true;
    filterPreviewCount.textContent = "";
    filterPreviewList.textContent = "";
  }

  if (openFilterBtn) {
    openFilterBtn.addEventListener("click", function () {
      resetFilterPreview();
      filterBackdrop.classList.add("open");
    });
  }
  if (filterCloseBtn) filterCloseBtn.addEventListener("click", function () { filterBackdrop.classList.remove("open"); });
  if (filterBackdrop) {
    filterBackdrop.addEventListener("click", function (e) { if (e.target === filterBackdrop) filterBackdrop.classList.remove("open"); });
  }

  if (filterPreviewBtn) {
    filterPreviewBtn.addEventListener("click", function () {
      var filters = collectFilters();
      if (!Object.keys(filters).length) { window.alert("Set at least one filter first — an empty filter would match everything (use Clear ALL surveys for that, on purpose)."); return; }
      resetFilterPreview();
      filterPreviewBtn.disabled = true;
      filterPreviewCount.textContent = "Checking…";
      apiPost("/api/preview-filtered", { filters: filters })
        .then(function (data) {
          lastPreviewTotal = data.total;
          lastPreviewFilters = filters;
          filterPreviewCount.textContent = data.total.toLocaleString() + " survey(s) match";
          data.preview.forEach(function (p) {
            var row = el("div", "filter-preview-row");
            row.textContent = p.survey_id + " — " + (p.title || "(untitled)") + " — " + (p.location || "(unknown)") +
              (p.date ? " — " + String(p.date).slice(0, 10) : "");
            filterPreviewList.appendChild(row);
          });
          if (data.total > data.preview.length) {
            filterPreviewList.appendChild(el("div", "count", "…and " + (data.total - data.preview.length) + " more"));
          }
          filterDeleteBtn.disabled = data.total === 0;
        })
        .catch(function (e) { filterPreviewCount.textContent = ""; window.alert("Preview failed: " + e.message); })
        .then(function () { filterPreviewBtn.disabled = false; });
    });
  }

  if (filterDeleteBtn) {
    filterDeleteBtn.addEventListener("click", function () {
      if (lastPreviewTotal === null || !lastPreviewFilters) return;
      var total = lastPreviewTotal;
      if (!window.confirm("Permanently delete " + total.toLocaleString() + " survey(s) matching these filters?\\n\\nA backup JSON is saved on the server first, but this cannot be undone from the dashboard.")) return;
      if (total > 1) {
        var typed = window.prompt("Type the number of surveys to confirm (" + total + "):");
        if (typed !== String(total)) { window.alert("Cancelled — number didn't match. Nothing deleted."); return; }
      }
      filterDeleteBtn.disabled = true;
      apiPost("/api/delete-filtered", { filters: lastPreviewFilters, expected_count: total })
        .then(function (data) { window.location = data.redirect || "/"; })
        .catch(function (e) { window.alert("Delete failed: " + e.message); filterDeleteBtn.disabled = false; });
    });
  }

  closeBtn.addEventListener("click", closeModal);
  backdrop.addEventListener("click", function (e) { if (e.target === backdrop) closeModal(); });
  document.addEventListener("keydown", function (e) {
    if (!backdrop.classList.contains("open")) return;
    if (e.key === "Escape") closeModal();
    else if (e.key === "ArrowLeft") navStep(-1);
    else if (e.key === "ArrowRight") navStep(1);
  });
})();
</script>
"""


def render_html(data: dict) -> str:
    def stat_tile(label, value, sub="", value_class=""):
        cls = f' class="tile-value {value_class}"' if value_class else ' class="tile-value"'
        return (
            f'<div class="tile"><div class="tile-label">{_esc(label)}</div>'
            f'<div{cls}>{value}</div>'
            f'<div class="tile-sub">{_esc(sub)}</div></div>'
        )

    opened_pct = f"{data['opened'] / data['total'] * 100:.0f}% of total" if data["total"] else ""
    kpis = (
        stat_tile("Total surveys", f"{data['total']:,}")
        + stat_tile("Marked opened", f"{data['opened']:,}", opened_pct)
        + stat_tile(
            "Average score",
            _esc(data["avg_score"]) if data["avg_score"] is not None else "—",
            f"across {data['scored_count']:,} scored" if data["scored_count"] else "no scored surveys",
        )
        + stat_tile(
            "Open errors",
            f"{data['errors']:,}",
            "mark-opened failures" if data["errors"] else "all clear",
            value_class="bad" if data["errors"] else "",
        )
        + stat_tile("ETL runs", f"{data['run_count']:,}")
    )

    def _err_cell(count) -> str:
        if count:
            return f'<td><span class="err-count">{_esc(count)}</span></td>'
        return f"<td>{_esc(count)}</td>"

    runs_rows = "".join(
        f'<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])[:19].replace("T", " ")}</td>'
        f'<td>{_run_status_chip(r[2])}</td>'
        f'<td>{_esc(r[3])}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td>'
        f'<td>{_esc(r[6])}</td>{_err_cell(r[7])}</tr>'
        for r in data["runs"]
    )

    survey_rows = "".join(
        f'<tr><td>{_esc(s[0])}</td><td>{_esc(s[1])}</td><td>{_esc(s[2])}</td>'
        f'<td>{_esc(s[3])[:10]}</td><td>{_esc(s[4])}</td><td>{_esc(s[5])}</td>'
        f'<td>{"<span class=yes>✓ Yes</span>" if s[6] else "<span class=no>– No</span>"}</td>'
        f'<td>{_esc(s[7])}</td><td>{_esc(s[8])}</td>'
        f'<td><button class="btn btn-details" data-sid="{_esc(s[0])}">Details</button></td></tr>'
        for s in data["surveys"]
    )

    # Embedded as JSON for the Details modal; "</" is escaped so survey text
    # can never terminate the <script> block early.
    details_json = json.dumps(
        data["details"], ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")

    def shown(n_shown, n_distinct):
        return f' <span class="count">· top {n_shown} of {n_distinct}</span>' if n_distinct > n_shown else ""

    is_live = "true" if data.get("server_token") else "false"
    live_token_json = json.dumps(data.get("server_token") or "")

    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Survey ETL Dashboard</title>
{_STYLE}
<div class="wrap">
<header>
  <h1>Client Analytics Survey ETL</h1>
  <div class="subtitle">
    Generated {_esc(data["generated_at"])}<span class="sep">·</span>{_esc(data["source"])}<span class="sep">·</span>{data["total"]:,} surveys, {data["run_count"]:,} runs
  </div>
</header>

<div class="kpi-row">{kpis}</div>

<div class="grid">
  <div class="card">
    <h2>Score distribution</h2>
    {_bar_chart_scores(data["bucket_labels"], data["bucket_counts"])}
  </div>
  <div class="card">
    <h2>Surveys by status{shown(len(data["statuses"]), data["status_distinct"])}</h2>
    {_bar_chart_breakdown(data["statuses"], data["total"])}
  </div>
  <div class="card">
    <h2>Top locations{shown(len(data["locations"]), data["location_distinct"])}</h2>
    {_bar_chart_breakdown(data["locations"], data["total"])}
  </div>
  <div class="card">
    <h2>Top survey titles / forms{shown(len(data["titles"]), data["title_distinct"])}</h2>
    {_bar_chart_breakdown(data["titles"], data["total"])}
  </div>
</div>

<div class="card span">
  <h2>Recent ETL runs <span class="count">· latest {len(data["runs"])}</span></h2>
  <table class="sortable">
    <thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Extracted</th><th>Loaded</th><th>Duplicates</th><th>Opened</th><th>Errors</th></tr></thead>
    <tbody>{runs_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>All surveys <span class="count">· click any row for full details &amp; responses · click a column header to sort</span></h2>
  <div class="toolbar">
    <input id="survey-search" type="search" placeholder="Search by ID, title, location, fieldworker…" />
    <div class="seg" id="opened-filter" role="group" aria-label="Filter by opened status">
      <button class="seg-btn active" data-filter="all">All</button>
      <button class="seg-btn" data-filter="yes">Opened</button>
      <button class="seg-btn" data-filter="no">Not opened</button>
    </div>
    <span id="search-count" class="count"></span>
    <button id="open-filter-modal-btn" class="btn btn-danger live-only" style="display:none">Delete by filter…</button>
    <button id="clear-all-btn" class="btn btn-danger live-only" style="display:none">Clear ALL surveys…</button>
    <span class="count static-only">Delete &amp; Clear-all need <code>manage.py serve</code> — see README</span>
  </div>
  <div class="table-wrap">
  <table class="sortable">
    <thead><tr><th>Survey ID</th><th>Title</th><th>Location</th><th>Date</th><th>Score</th><th>Status</th><th>Opened?</th><th>Fieldworker</th><th>Campaign</th><th></th></tr></thead>
    <tbody id="survey-tbody">{survey_rows}</tbody>
  </table>
  </div>
</div>

<footer>
  Refreshes automatically after every <code>run.bat run</code>; regenerate on demand with <code>run.bat dashboard</code>.
</footer>
</div>
<script id="survey-data" type="application/json">{details_json}</script>
<script>window.__DASHBOARD_LIVE__={is_live};window.__DASHBOARD_TOKEN__={live_token_json};</script>
{_SCRIPT}
"""


def generate(output_path: str = None, server_token: str = None) -> str:
    """server_token: set only by `manage.py serve` (src/server.py). Its
    presence is what turns on the dashboard's real Delete / Clear-all
    buttons -- a plain `generate()` call (the default for `run`/`dashboard`)
    produces a static file with those actions disabled, since there's no
    server behind it to actually change the database."""
    output_path = output_path or next_output_path()
    conn = get_connection()
    try:
        data = build_data(conn)
    finally:
        conn.close()
    data["server_token"] = server_token

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    return output_path


def open_in_browser(path: str) -> bool:
    """Opens the generated dashboard in the default browser. On Windows this
    uses os.startfile — identical to double-clicking the file, the most
    reliable route to the default browser. Best-effort: returns False
    instead of raising (headless boxes, odd shells)."""
    try:
        resolved = os.path.abspath(path)
        if os.name == "nt":
            os.startfile(resolved)
            return True
        import webbrowser
        from pathlib import Path

        return webbrowser.open(Path(resolved).as_uri())
    except Exception:
        return False


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result_path = generate(path)
    print(f"Dashboard written to {result_path}")
    if config.OPEN_DASHBOARD:
        open_in_browser(result_path)
