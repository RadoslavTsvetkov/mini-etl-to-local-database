"""Extraction step: reads new survey records from a local file or the live
Shopmetrics Query API v2, depending on EXTRACTION_MODE (see config.py).
"""

import json

import api_client
import config

REQUIRED_FIELDS = ["survey_id", "survey_title", "submitted_at"]


def _normalize(record: dict) -> dict:
    return {
        "survey_id": str(record["survey_id"]),
        "client_or_form_id": record.get("client_or_form_id"),
        "survey_title": record.get("survey_title"),
        "location_store_id": record.get("location_store_id"),
        "location_name": record.get("location_name"),
        "submitted_at": record.get("submitted_at"),
        "score": record.get("score"),
        "responses": record.get("responses", []),
        "campaign": record.get("campaign"),
        "survey_status": record.get("survey_status"),
        "attachments_count": record.get("attachments_count"),
        "fieldworker_login": record.get("fieldworker_login"),
        "fieldworker_name": record.get("fieldworker_name"),
        "workflow_step_id": record.get("workflow_step_id"),
    }


def extract_from_file(path: str = None) -> tuple[list[dict], list[str]]:
    """Reads survey records from a local JSON file. Returns (records, errors)."""
    path = path or config.SURVEYS_SOURCE_PATH
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_records = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        errors.append(f"Failed to read/parse source file {path}: {e}")
        return [], errors

    records = []
    for i, raw in enumerate(raw_records):
        missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
        if missing:
            errors.append(f"Record {i} missing required fields {missing}: skipped")
            continue
        records.append(_normalize(raw))
    return records, errors


def extract_from_api() -> tuple[list[dict], list[str]]:
    """Queries the live Shopmetrics Query API v2 for new survey instances."""
    errors = []
    try:
        raw_records = api_client.query_new_surveys()
    except api_client.ShopmetricsAPIError as e:
        errors.append(f"Query API extraction failed: {e}")
        return [], errors

    records = []
    for i, raw in enumerate(raw_records):
        missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
        if missing:
            errors.append(f"Record {i} missing required fields {missing}: skipped")
            continue
        records.append(_normalize(raw))
    return records, errors


def extract() -> tuple[list[dict], list[str]]:
    """Extracts survey records per EXTRACTION_MODE. Returns (records, errors)."""
    if config.EXTRACTION_MODE == "api":
        return extract_from_api()
    return extract_from_file()
