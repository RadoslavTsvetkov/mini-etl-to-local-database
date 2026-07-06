"""Load step: inserts extracted survey records into the database, skipping
duplicates. Works against either backend selected via config.DB_BACKEND
("sqlite" or "sqlserver") -- the SQL dialect for the insert-if-new check
differs between the two, everything else is portable.
"""

import json
from datetime import datetime, timezone

import config


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
