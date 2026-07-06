"""Generates a self-contained HTML dashboard summarizing the collected
survey data: KPI tiles, score distribution, status/location/title
breakdowns, and recent run history. No external dependencies (no JS
charting library, no CDN) -- plain inline SVG bars.

Usage:
    python generate_dashboard.py [output_path]   # default: reports/dashboard.html
"""

import html
import os
import sys
from collections import Counter

import config
from db.setup_db import get_connection

DEFAULT_OUTPUT = os.path.join(config.PROJECT_ROOT, "reports", "dashboard.html")


def _top_n(sql: str, n: int) -> str:
    """Portable "top N rows" -- SQLite uses trailing LIMIT, SQL Server uses
    a leading TOP after SELECT."""
    if config.DB_BACKEND == "sqlserver":
        return sql.replace("SELECT", f"SELECT TOP {n}", 1)
    return f"{sql} LIMIT {n}"

# Reference palette (see dataviz skill references/palette.md) -- validated
# categorical theme (fixed order), 8 slots. Actual hex values live in the
# stylesheet as --cat-1..--cat-8 CSS vars (light + dark steps), so bars are
# emitted as `fill="var(--cat-N)"` and swap automatically with color scheme.
CATEGORICAL_SLOT_COUNT = 8


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
    bucket_labels = ["0-19", "20-39", "40-59", "60-79", "80-100"]
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
        _top_n(
            """
            SELECT survey_id, survey_title, location_name, submitted_at, score,
                   survey_status, opened, fieldworker_name, campaign
            FROM surveys ORDER BY loaded_at DESC
            """,
            200,
        ),
    )

    return {
        "total": total,
        "opened": opened,
        "errors": errors,
        "avg_score": avg_score,
        "run_count": run_count,
        "bucket_labels": bucket_labels,
        "bucket_counts": bucket_counts,
        "statuses": statuses.most_common(8),
        "locations": locations.most_common(8),
        "titles": titles.most_common(8),
        "runs": runs,
        "surveys": surveys,
    }


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _bar_chart_categorical(counts: list[tuple]) -> str:
    """Horizontal bar chart, one fixed categorical hue per bar (direct-labeled)."""
    if not counts:
        return "<p class='empty'>No data.</p>"
    max_count = max(c for _, c in counts) or 1
    row_h, gap, label_w, chart_w = 24, 10, 170, 320
    svg_h = len(counts) * (row_h + gap)
    bars = []
    for i, (name, count) in enumerate(counts):
        y = i * (row_h + gap)
        w = max(2, round((count / max_count) * chart_w))
        color = f"var(--cat-{(i % CATEGORICAL_SLOT_COUNT) + 1})"
        bars.append(
            f'<g>'
            f'<text x="{label_w - 8}" y="{y + row_h / 2 + 4}" text-anchor="end" class="axis-label">{_esc(name)[:22]}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w}" height="{row_h}" rx="4" fill="{color}">'
            f'<title>{_esc(name)}: {count}</title>'
            f'</rect>'
            f'<text x="{label_w + w + 6}" y="{y + row_h / 2 + 4}" class="value-label">{count}</text>'
            f'</g>'
        )
    return (
        f'<svg viewBox="0 0 {label_w + chart_w + 50} {svg_h}" width="100%" height="{svg_h}" role="img">'
        + "".join(bars)
        + "</svg>"
    )


def _bar_chart_sequential(labels: list[str], counts: list[int]) -> str:
    """Vertical bar chart, single sequential hue (magnitude -- score distribution)."""
    if not counts or not any(counts):
        return "<p class='empty'>No score data.</p>"
    max_count = max(counts) or 1
    bar_w, gap, chart_h, base_y = 48, 24, 160, 180
    bars = []
    for i, (label, count) in enumerate(zip(labels, counts)):
        x = i * (bar_w + gap)
        h = max(2, round((count / max_count) * chart_h))
        y = base_y - h
        bars.append(
            f'<g>'
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" rx="4" fill="var(--seq)">'
            f'<title>{_esc(label)}: {count}</title>'
            f'</rect>'
            f'<text x="{x + bar_w / 2}" y="{y - 6}" text-anchor="middle" class="value-label">{count}</text>'
            f'<text x="{x + bar_w / 2}" y="{base_y + 20}" text-anchor="middle" class="axis-label">{_esc(label)}</text>'
            f'</g>'
        )
    total_w = len(counts) * (bar_w + gap)
    return (
        f'<svg viewBox="0 0 {total_w} {base_y + 30}" width="100%" height="{base_y + 30}" role="img">'
        f'<line x1="0" y1="{base_y}" x2="{total_w}" y2="{base_y}" class="baseline" />'
        + "".join(bars)
        + "</svg>"
    )


def render_html(data: dict) -> str:
    def stat_tile(label, value, sub=""):
        return (
            f'<div class="tile"><div class="tile-label">{_esc(label)}</div>'
            f'<div class="tile-value">{_esc(value)}</div>'
            f'<div class="tile-sub">{_esc(sub)}</div></div>'
        )

    kpis = (
        stat_tile("Total surveys", data["total"])
        + stat_tile("Marked opened", data["opened"], f"{(data['opened'] / data['total'] * 100):.0f}% of total" if data["total"] else "")
        + stat_tile("Average score", data["avg_score"] if data["avg_score"] is not None else "—")
        + stat_tile("Errors", data["errors"])
        + stat_tile("ETL runs", data["run_count"])
    )

    runs_rows = "".join(
        f'<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])[:19]}</td>'
        f'<td class="status-{_esc(r[2])}">{_esc(r[2])}</td>'
        f'<td>{_esc(r[3])}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td>'
        f'<td>{_esc(r[6])}</td><td>{_esc(r[7])}</td></tr>'
        for r in data["runs"]
    )

    survey_rows = "".join(
        f'<tr><td>{_esc(s[0])}</td><td>{_esc(s[1])}</td><td>{_esc(s[2])}</td>'
        f'<td>{_esc(s[3])[:10]}</td><td>{_esc(s[4])}</td><td>{_esc(s[5])}</td>'
        f'<td>{"Yes" if s[6] else "No"}</td><td>{_esc(s[7])}</td><td>{_esc(s[8])}</td></tr>'
        for s in data["surveys"]
    )

    return f"""<title>Survey ETL Dashboard</title>
<style>
  :root {{
    --surface-1: #fcfcfb; --page: #f9f9f7; --text-primary: #0b0b0b;
    --text-secondary: #52514e; --text-muted: #898781; --grid: #e1e0d9;
    --baseline: #c3c2b7; --seq: #2a78d6; --good: #0ca30c; --warn: #fab219; --bad: #d03b3b;
    --border: rgba(11,11,11,0.10);
    --cat-1: #2a78d6; --cat-2: #1baf7a; --cat-3: #eda100; --cat-4: #008300;
    --cat-5: #4a3aa7; --cat-6: #e34948; --cat-7: #e87ba4; --cat-8: #eb6834;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --surface-1: #1a1a19; --page: #0d0d0d; --text-primary: #ffffff;
      --text-secondary: #c3c2b7; --text-muted: #898781; --grid: #2c2c2a;
      --baseline: #383835; --seq: #3987e5; --good: #0ca30c; --warn: #fab219; --bad: #e66767;
      --border: rgba(255,255,255,0.10);
      --cat-1: #3987e5; --cat-2: #199e70; --cat-3: #c98500; --cat-4: #008300;
      --cat-5: #9085e9; --cat-6: #e66767; --cat-7: #d55181; --cat-8: #d95926;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 0 0 12px; color: var(--text-secondary); font-weight: 600; }}
  .subtitle {{ color: var(--text-secondary); font-size: 13px; margin-bottom: 28px; }}
  .kpi-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
  .tile {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 18px; min-width: 140px; flex: 1;
  }}
  .tile-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }}
  .tile-value {{ font-size: 26px; font-weight: 600; }}
  .tile-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 4px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; margin-bottom: 28px; }}
  .card {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: 18px;
    overflow-x: auto;
  }}
  .axis-label {{ font-size: 11px; fill: var(--text-muted); }}
  .value-label {{ font-size: 11px; fill: var(--text-secondary); font-variant-numeric: tabular-nums; }}
  .baseline {{ stroke: var(--baseline); stroke-width: 1; }}
  .empty {{ color: var(--text-muted); font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  th {{ color: var(--text-secondary); font-weight: 600; }}
  td {{ font-variant-numeric: tabular-nums; }}
  .status-success {{ color: var(--good); }}
  .status-partial {{ color: var(--warn); }}
  .status-failed {{ color: var(--bad); }}
  .table-wrap {{ max-height: 480px; overflow-y: auto; }}
</style>

<h1>Client Analytics Survey ETL &mdash; Dashboard</h1>
<div class="subtitle">Generated from the local database. Re-run <code>python generate_dashboard.py</code> after each ETL run to refresh.</div>

<div class="kpi-row">{kpis}</div>

<div class="grid">
  <div class="card">
    <h2>Score distribution</h2>
    {_bar_chart_sequential(data["bucket_labels"], data["bucket_counts"])}
  </div>
  <div class="card">
    <h2>Surveys by status</h2>
    {_bar_chart_categorical(data["statuses"])}
  </div>
  <div class="card">
    <h2>Top locations</h2>
    {_bar_chart_categorical(data["locations"])}
  </div>
  <div class="card">
    <h2>Top survey titles / forms</h2>
    {_bar_chart_categorical(data["titles"])}
  </div>
</div>

<div class="card" style="margin-bottom: 28px;">
  <h2>Recent ETL runs</h2>
  <table>
    <thead><tr><th>Run</th><th>Started</th><th>Status</th><th>Extracted</th><th>Loaded</th><th>Duplicates</th><th>Opened</th><th>Errors</th></tr></thead>
    <tbody>{runs_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>All surveys (table view, most recent 200)</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Survey ID</th><th>Title</th><th>Location</th><th>Date</th><th>Score</th><th>Status</th><th>Opened?</th><th>Fieldworker</th><th>Campaign</th></tr></thead>
    <tbody>{survey_rows}</tbody>
  </table>
  </div>
</div>
"""


def generate(output_path: str = None) -> str:
    output_path = output_path or DEFAULT_OUTPUT
    conn = get_connection()
    try:
        data = build_data(conn)
    finally:
        conn.close()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    return output_path


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result_path = generate(path)
    print(f"Dashboard written to {result_path}")
