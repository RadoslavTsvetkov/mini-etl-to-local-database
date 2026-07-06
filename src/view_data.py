"""Prints the contents of the ETL database as readable, color-highlighted tables.

Usage:
    python view_data.py            # shows surveys + run history
    python view_data.py surveys    # shows only the surveys table
    python view_data.py runs       # shows only the etl_runs table
    python view_data.py <survey_id> # drill into one survey's responses
"""

import json
import sys

from colors import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW
from db.setup_db import get_connection

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _print_table(headers: list[str], rows: list[tuple], cell_color=None) -> None:
    """cell_color: optional fn(raw_row, col_index) -> ANSI code or None."""
    if not rows:
        print("  (no rows)")
        return

    str_rows = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_plain(cells):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(BOLD + fmt_plain(headers) + RESET)
    print(DIM + "  ".join("-" * w for w in widths) + RESET)

    for raw_row, str_row in zip(rows, str_rows):
        cells = []
        for i, cell in enumerate(str_row):
            padded = cell.ljust(widths[i])
            code = cell_color(raw_row, i) if cell_color else None
            cells.append(f"{code}{padded}{RESET}" if code else padded)
        print("  ".join(cells))


def _score_color(score) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return GREEN
    if score >= 50:
        return YELLOW
    return RED


def _surveys_cell_color(raw_row, col_index):
    # Columns: survey_id, survey_title, location_name, submitted_at, score,
    #          survey_status, opened, fieldworker_name
    score = raw_row[4]
    opened = raw_row[6]
    if col_index == 4:
        return _score_color(score)
    if col_index == 6:
        return GREEN if opened == "Yes" else RED
    if col_index == 5:
        return CYAN
    return None


def show_surveys(conn) -> None:
    print("\n=== Surveys collected ===")
    rows = conn.execute(
        """
        SELECT survey_id, survey_title, location_name, submitted_at, score,
               survey_status,
               CASE WHEN opened = 1 THEN 'Yes' ELSE 'No' END AS opened,
               fieldworker_name
        FROM surveys
        ORDER BY loaded_at DESC
        """
    ).fetchall()
    _print_table(
        ["Survey ID", "Title", "Location", "Date", "Score", "Status", "Opened?", "Fieldworker"],
        rows,
        cell_color=_surveys_cell_color,
    )
    print(f"\nTotal surveys in database: {len(rows)}")

    errors = conn.execute(
        "SELECT survey_id, open_error FROM surveys WHERE open_error IS NOT NULL"
    ).fetchall()
    if errors:
        print(f"\n{RED}Errors ({len(errors)}):{RESET}")
        for survey_id, error in errors:
            print(f"  {RED}{survey_id}: {error}{RESET}")


def show_survey_responses(conn, survey_id: str) -> None:
    row = conn.execute(
        """
        SELECT survey_title, responses_json, campaign, survey_status, score,
               location_name, fieldworker_name, attachments_count
        FROM surveys WHERE survey_id = ?
        """,
        (survey_id,),
    ).fetchone()
    if not row:
        print(f"No survey found with ID {survey_id}")
        return
    title, responses_json, campaign, status, score, location, fieldworker, attachments = row
    responses = json.loads(responses_json or "[]")

    print(f"\n=== Survey {survey_id}: {title} ===")
    print(f"  Location:     {location}")
    print(f"  Campaign:     {campaign}")
    print(f"  Status:       {CYAN}{status}{RESET}")
    score_code = _score_color(score) or ""
    print(f"  Score:        {score_code}{score}{RESET if score_code else ''}")
    print(f"  Fieldworker:  {fieldworker}")
    print(f"  Attachments:  {attachments or 0}")
    print(f"\n  Responses ({len(responses)}):")
    for r in responses:
        print(f"  - Q{r.get('question_id')}: {r.get('answer_text')}  |  {r.get('comment') or ''}")
    if not responses:
        print("  (no responses recorded)")


def _runs_cell_color(raw_row, col_index):
    # Columns: run_id, started_at, status, extracted, loaded, duplicates, opened, errors
    status = raw_row[2]
    errors = raw_row[7]
    if col_index == 2:
        return {"success": GREEN, "partial": YELLOW, "failed": RED}.get(status)
    if col_index == 7:
        return RED if errors else None
    return None


def show_runs(conn) -> None:
    print("\n=== ETL run history ===")
    rows = conn.execute(
        """
        SELECT run_id, started_at, status, surveys_extracted, surveys_loaded,
               surveys_duplicate, surveys_marked_opened, error_count
        FROM etl_runs
        ORDER BY run_id DESC
        """
    ).fetchall()
    _print_table(
        ["Run", "Started At", "Status", "Extracted", "Loaded", "Duplicates", "Opened", "Errors"],
        rows,
        cell_color=_runs_cell_color,
    )


def main(which: str = "all") -> None:
    conn = get_connection()
    try:
        if which in ("all", "surveys"):
            show_surveys(conn)
        if which in ("all", "runs"):
            show_runs(conn)
        if which not in ("all", "surveys", "runs"):
            # Treat the argument as a survey_id to drill into its responses.
            show_survey_responses(conn, which)
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
