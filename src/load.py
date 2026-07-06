"""Load step: inserts extracted survey records into the database, skipping
duplicates. Works against either backend selected via config.DB_BACKEND
("sqlite" or "sqlserver") -- the SQL dialect for the insert-if-new check
differs between the two, everything else is portable.
"""

import json
from datetime import datetime, timedelta, timezone

import config


class FilterError(ValueError):
    """Raised by build_survey_filter for a filter value it can't use (e.g.
    an unparsable date) -- callers show `str(e)` directly to the user."""


def _survey_values(record: dict, now: str) -> tuple:
    return (
        record["survey_id"],
        record.get("client_or_form_id"),
        record.get("survey_title"),
        record.get("location_store_id"),
        record.get("location_name"),
        record.get("submitted_at"),
        record.get("score"),
        json.dumps(record.get("responses", [])),
        now,
        record.get("campaign"),
        record.get("survey_status"),
        record.get("attachments_count"),
        record.get("fieldworker_login"),
        record.get("fieldworker_name"),
        record.get("workflow_step_id"),
    )


_INSERT_COLUMNS = """
    survey_id, client_or_form_id, survey_title, location_store_id,
    location_name, submitted_at, score, responses_json, loaded_at, opened,
    campaign, survey_status, attachments_count, fieldworker_login,
    fieldworker_name, workflow_step_id
"""
_INSERT_PLACEHOLDERS = "?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?"


def _insert_survey_sqlite(conn, record: dict, now: str) -> bool:
    cursor = conn.execute(
        f"INSERT OR IGNORE INTO surveys ({_INSERT_COLUMNS}) VALUES ({_INSERT_PLACEHOLDERS})",
        _survey_values(record, now),
    )
    return cursor.rowcount == 1


def _insert_survey_sqlserver(conn, record: dict, now: str) -> bool:
    values = _survey_values(record, now)
    cursor = conn.execute(
        f"""
        IF NOT EXISTS (SELECT 1 FROM surveys WHERE survey_id = ?)
        BEGIN
            INSERT INTO surveys ({_INSERT_COLUMNS}) VALUES ({_INSERT_PLACEHOLDERS})
        END
        """,
        (record["survey_id"],) + values,
    )
    return cursor.rowcount == 1


def load_surveys(conn, records: list[dict]) -> tuple[list[str], int]:
    """Inserts new records into the surveys table.

    Returns (inserted_survey_ids, duplicate_count).
    """
    now = datetime.now(timezone.utc).isoformat()
    insert_one = _insert_survey_sqlserver if config.DB_BACKEND == "sqlserver" else _insert_survey_sqlite

    inserted_ids = []
    duplicate_count = 0
    for record in records:
        if insert_one(conn, record, now):
            inserted_ids.append(record["survey_id"])
        else:
            duplicate_count += 1

    conn.commit()
    return inserted_ids, duplicate_count


def mark_opened(conn, survey_id: str, command_request_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE surveys SET opened = 1, opened_at = ?, command_request_id = ?, open_error = NULL WHERE survey_id = ?",
        (now, command_request_id, survey_id),
    )
    conn.commit()


def mark_open_error(conn, survey_id: str, error_message: str) -> None:
    conn.execute(
        "UPDATE surveys SET open_error = ? WHERE survey_id = ?",
        (error_message, survey_id),
    )
    conn.commit()


def count_surveys(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM surveys").fetchone()[0]


def fetch_survey(conn, survey_id: str) -> dict | None:
    """Fetches one full survey row as a dict (all columns), for confirmation
    prompts and backups. Portable across sqlite3/pyodbc: neither guarantees
    dict-like rows, so columns come from cursor.description."""
    cursor = conn.execute("SELECT * FROM surveys WHERE survey_id = ?", (survey_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [d[0] for d in cursor.description]
    return dict(zip(columns, row))


def fetch_all_surveys(conn) -> list[dict]:
    """Fetches every survey row as a list of dicts, for backups before a
    bulk delete. See fetch_survey for the portability note."""
    cursor = conn.execute("SELECT * FROM surveys")
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def delete_survey(conn, survey_id: str) -> bool:
    """Deletes one survey by ID. Returns True if a row was actually deleted."""
    cursor = conn.execute("DELETE FROM surveys WHERE survey_id = ?", (survey_id,))
    conn.commit()
    return cursor.rowcount == 1


def clear_all_surveys(conn) -> int:
    """Deletes every row from the surveys table. Returns the number of rows
    deleted. Caller is responsible for backing up first -- see backup.py."""
    cursor = conn.execute("DELETE FROM surveys")
    conn.commit()
    return cursor.rowcount


# --- Filtered / bulk delete (delete-surveys CLI command, dashboard "Delete
# by filter" modal in `manage.py serve`) ---
#
# Every key is optional; combined with AND. Text filters (title, location,
# status, campaign, fieldworker) are case-insensitive substring matches.
# `ids` is an exact-match list (for an arbitrary/non-contiguous set); id_min/
# id_max is an inclusive numeric range over survey_id (cast to an integer --
# "INTEGER" is accepted by both SQLite and SQL Server, which treats it as a
# synonym for INT). date_from/date_to are "YYYY-MM-DD"; date_to is inclusive
# of the whole day. Callers MUST refuse to run with zero filters supplied --
# this function has no opinion on that and will happily return an empty
# clause, which would match every row.

def build_survey_filter(filters: dict) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    ids = filters.get("ids")
    if ids:
        clauses.append(f"survey_id IN ({','.join('?' for _ in ids)})")
        params.extend(str(i) for i in ids)

    if filters.get("id_min") is not None:
        clauses.append("CAST(survey_id AS INTEGER) >= ?")
        params.append(int(filters["id_min"]))
    if filters.get("id_max") is not None:
        clauses.append("CAST(survey_id AS INTEGER) <= ?")
        params.append(int(filters["id_max"]))

    for key, column in (
        ("title", "survey_title"),
        ("location", "location_name"),
        ("status", "survey_status"),
        ("campaign", "campaign"),
    ):
        if filters.get(key):
            clauses.append(f"LOWER({column}) LIKE ?")
            params.append(f"%{filters[key].lower()}%")

    if filters.get("fieldworker"):
        needle = f"%{filters['fieldworker'].lower()}%"
        clauses.append("(LOWER(fieldworker_name) LIKE ? OR LOWER(fieldworker_login) LIKE ?)")
        params.extend([needle, needle])

    date_from = filters.get("date_from")
    if date_from:
        try:
            datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise FilterError(f'date_from must be "YYYY-MM-DD", got {date_from!r}')
        clauses.append("submitted_at >= ?")
        params.append(date_from)

    date_to = filters.get("date_to")
    if date_to:
        try:
            next_day = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            raise FilterError(f'date_to must be "YYYY-MM-DD", got {date_to!r}')
        clauses.append("submitted_at < ?")  # exclusive upper bound so date_to's whole day is included
        params.append(next_day)

    if filters.get("score_min") is not None:
        clauses.append("score >= ?")
        params.append(float(filters["score_min"]))
    if filters.get("score_max") is not None:
        clauses.append("score <= ?")
        params.append(float(filters["score_max"]))

    if filters.get("opened") is not None:
        clauses.append("opened = ?")
        params.append(1 if filters["opened"] else 0)

    return " AND ".join(clauses), params


def count_matching_surveys(conn, where_sql: str, params: list) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM surveys WHERE {where_sql}", params).fetchone()[0]


def preview_matching_surveys(conn, where_sql: str, params: list, limit: int = 10) -> list[dict]:
    """Lean preview rows (no responses_json) for a confirmation screen --
    intentionally separate from fetch_matching_surveys so previewing a
    large match doesn't pull every row's full response payload."""
    cursor = conn.execute(
        "SELECT survey_id, survey_title, location_name, submitted_at, score "
        f"FROM surveys WHERE {where_sql} ORDER BY loaded_at DESC",
        params,
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()[:limit]]


def fetch_matching_surveys(conn, where_sql: str, params: list) -> list[dict]:
    """Every full row matching the filter -- used for the pre-delete backup."""
    cursor = conn.execute(f"SELECT * FROM surveys WHERE {where_sql}", params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def delete_matching_surveys(conn, where_sql: str, params: list) -> int:
    cursor = conn.execute(f"DELETE FROM surveys WHERE {where_sql}", params)
    conn.commit()
    return cursor.rowcount
