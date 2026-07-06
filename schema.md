# Database Schema

The pipeline supports two interchangeable backends, selected via `DB_BACKEND`
(see `config/config.json` / `.env.example`). Both have the identical logical
schema below; only the DDL dialect and physical location differ:

| Backend | `DB_BACKEND` | Location | DDL file | Viewer |
|---|---|---|---|---|
| SQLite (default) | `sqlite` | `data/etl.db` (a single file) | `src/db/schema.sql` | `view_data.py`, or [DB Browser for SQLite](https://sqlitebrowser.org/) |
| SQL Server | `sqlserver` | Local SQL Server instance (default `.\SQLEXPRESS`, database `ShopmetricsETL`) | `src/db/schema_sqlserver.sql` | SSMS, or `view_data.py` |

Both are created automatically (idempotently) by `src/db/setup_db.py` the
first time `etl.py` or `view_data.py` runs with that backend selected.
Columns added after the initial release are migrated onto existing databases
automatically too (`ALTER TABLE ADD COLUMN` under the hood) — no data loss,
no manual migration step.

## `surveys`

One row per extracted survey instance and its "mark opened" processing state.
Types below are the SQLite types; see `src/db/schema_sqlserver.sql` for the
exact SQL Server equivalents (e.g. `TEXT` → `NVARCHAR`, `INTEGER` 0/1 → `BIT`).

| Column | Type | Notes |
|---|---|---|
| `survey_id` | TEXT PRIMARY KEY | Shopmetrics `InstanceID` / `SurveyInstanceID`. Used for dedup on load. |
| `client_or_form_id` | TEXT | The `ClientOrFormIDs` value the record was extracted under. |
| `survey_title` | TEXT | Survey `Title`. |
| `location_store_id` | TEXT | `Loc ID` of the surveyed location. |
| `location_name` | TEXT | Name of the surveyed location. |
| `submitted_at` | TEXT (ISO 8601) | Survey `Date`. |
| `score` | REAL, nullable | Survey score (`ScorePctXX.XX`). |
| `responses_json` | TEXT | JSON array of `{question_id, answer_text, comment}` response rows. |
| `loaded_at` | TEXT (ISO 8601) | When the ETL inserted this row. |
| `opened` | INTEGER (0/1) | Whether the "mark opened" Command API call was submitted successfully. |
| `opened_at` | TEXT (ISO 8601), nullable | When it was marked opened. |
| `command_request_id` | TEXT, nullable | `RequestUUID` returned by the `BulkProcessing_SetReadStatus` command (async), for status lookup via the `CommandStatusCheck` query resource. |
| `open_error` | TEXT, nullable | Error message if the mark-opened call failed. |
| `campaign` | TEXT, nullable | Survey `Campaign` (e.g. `2022-08`). |
| `survey_status` | TEXT, nullable | Shopmetrics `SurveyStatusName` (e.g. `Completed Exported`). |
| `attachments_count` | INTEGER, nullable | `AttachmentsCount` on the survey instance. |
| `fieldworker_login` | TEXT, nullable | Shopmetrics `Login` of the fieldworker/shopper who submitted the survey. |
| `fieldworker_name` | TEXT, nullable | `Shopper Name`. |
| `workflow_step_id` | INTEGER, nullable | `WorkflowStepID` at time of extraction. |

## `etl_runs`

One row per pipeline execution.

| Column | Type | Notes |
|---|---|---|
| `run_id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `started_at` | TEXT (ISO 8601) | |
| `finished_at` | TEXT (ISO 8601) | |
| `surveys_extracted` | INTEGER | Count read from the source. |
| `surveys_loaded` | INTEGER | Count newly inserted (excludes duplicates). |
| `surveys_duplicate` | INTEGER | Count skipped as already present. |
| `surveys_marked_opened` | INTEGER | Count successfully marked via the Command API. |
| `error_count` | INTEGER | Total errors encountered during the run. |
| `status` | TEXT | `success`, `partial`, or `failed`. |

See `SPECIFICATION.md` sections 2 and 5 for how these columns map to the real
Shopmetrics API v2 fields and endpoints.
