-- Client Analytics Survey ETL Pipeline schema
-- See schema.md for a human-readable description and SPECIFICATION.md section 5
-- for how columns map to the real Shopmetrics Client Analytics Query API fields.

CREATE TABLE IF NOT EXISTS surveys (
    survey_id           TEXT PRIMARY KEY,
    client_or_form_id   TEXT,
    survey_title        TEXT,
    location_store_id   TEXT,
    location_name       TEXT,
    submitted_at        TEXT,
    score                REAL,
    responses_json       TEXT,
    loaded_at            TEXT NOT NULL,
    opened                INTEGER NOT NULL DEFAULT 0,
    opened_at             TEXT,
    command_request_id    TEXT,
    open_error             TEXT,
    campaign               TEXT,
    survey_status           TEXT,
    attachments_count        INTEGER,
    fieldworker_login         TEXT,
    fieldworker_name           TEXT,
    workflow_step_id            INTEGER
);

CREATE TABLE IF NOT EXISTS etl_runs (
    run_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at              TEXT NOT NULL,
    finished_at             TEXT,
    surveys_extracted       INTEGER NOT NULL DEFAULT 0,
    surveys_loaded          INTEGER NOT NULL DEFAULT 0,
    surveys_duplicate       INTEGER NOT NULL DEFAULT 0,
    surveys_marked_opened   INTEGER NOT NULL DEFAULT 0,
    error_count             INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'running'
);
