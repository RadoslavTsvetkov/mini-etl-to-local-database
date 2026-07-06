"""Writes JSON backups of survey rows before a destructive delete, so
`manage.py delete-survey` / `clear-surveys` (and the equivalent dashboard
actions in `manage.py serve`) are recoverable even though the operation
itself is permanent in the database. Zero third-party dependencies.
"""

import json
import os
from datetime import datetime, timezone

import config

BACKUPS_DIR = os.path.join(config.PROJECT_ROOT, "data", "backups")


def _write(records: list[dict], filename: str) -> str:
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    path = os.path.join(BACKUPS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False, default=str)
    return path


def backup_survey(record: dict) -> str:
    """Backs up a single survey before `delete-survey`. Filename includes
    the survey ID and a timestamp so repeated deletes never collide."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _write([record], f"survey_{record.get('survey_id', 'unknown')}_deleted_{stamp}.json")


def backup_all_surveys(records: list[dict]) -> str:
    """Backs up every survey before `clear-surveys` wipes the table."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _write(records, f"all_surveys_backup_{stamp}.json")


def backup_filtered_surveys(records: list[dict]) -> str:
    """Backs up the rows matched by a filter before `delete-surveys` (CLI)
    or the dashboard's "Delete by filter" action removes them."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _write(records, f"filtered_surveys_backup_{stamp}.json")
