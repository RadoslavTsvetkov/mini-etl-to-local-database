# Specification: Client Analytics Survey ETL Pipeline

Source task: [TASK_001.md](TASK_001.md)

This version is wired against the **real Shopmetrics API v2**, as documented in `_KNOWLEDGEBASE/023-APIs/`, replacing the placeholder endpoints from the first draft of this spec.

## 1. Overview

A small, self-contained Python ETL pipeline that:

1. **Extracts** new Client Analytics survey instances — either from the real Shopmetrics Query API v2, or from a local sample file for offline testing.
2. **Loads** them into a local SQLite database, skipping records already present.
3. **Marks** each newly loaded survey as "opened" (`BulkProcessing_SetReadStatus`, flipping the same `IsSurveyInstanceViewedBySecurityUser` field the extraction filters on) via the real Shopmetrics Command API v2.
4. **Logs** every run (date, counts, errors) to a log file.

The pipeline runs end-to-end via a single entry point, `etl.py`. The *checked-in config defaults* remain **mock/offline** (file extraction + simulated Command API) so `manage.py run` always works without network access or credentials; the primary Windows entry point, a bare double-clicked `run.bat`, passes `--mode api` and therefore **scrapes the live Query API by default** (read-only; mark-opened stays mocked), prompting once for API credentials if `.env` doesn't have them (§4.2). After every run a new *numbered* HTML dashboard is generated (`reports/dashboard1.html`, `dashboard2.html`, …; older reports are kept) and opened in the default browser automatically.

## 2. How This Maps to the Real Shopmetrics API

Everything below is taken from `_KNOWLEDGEBASE/023-APIs/`, not invented. Article short codes are cited so they can be looked up again.

| Concern | Real Shopmetrics behavior | Source |
|---|---|---|
| Auth | OAuth 2.0 **Client Credentials Grant**. `POST {base_url}/oauth/connect/token` with form fields `client_id`, `client_secret`, `grant_type=client_credentials`. Returns `access_token` + `expires_in` (default 1800s). Used as `Authorization: Bearer <token>` on every Query/Command call. | APIAUT |
| Query API | API v2 uses a single generic endpoint: `POST {base_url}/api/v2/execute`, body `{"post": "<JSON string>"}` where the inner JSON selects a dataset and parameters. | APIQRY, APIINV2 |
| Extraction dataset | `/Apps/SM/APIv2/Query/ClientAnalytics/ClientAnalytics` — the Client Analytics query data model, restricted to surveys with "OK for Client Access" status. Requires a `QuerySpecification` field list plus at least one filter (we use `ClientOrFormIDs`). | APIICA, APICA |
| "New" surveys | The field `IsSurveyInstanceViewedBySecurityUser` marks whether the survey has already been opened/viewed by the client user. We filter for unopened ones with `[WHERE:IsSurveyInstanceViewedBySecurityUser\|0]` in `QuerySpecification`, mirroring the KB's "List of NEW Survey Instances" example. | APICA |
| Survey responses | A second call to the same dataset with `QuerySpecification: [InstanceID][QuestionID][ProtoAnswerText][Question Comment]`, filtered by `SurveyInstanceIDs` (CSV of IDs from the first call), returns the answer rows for those instances. | APICAUC |
| Command API (REST-style, most v2 use cases) | `POST {base_url}/api/v2/command/<CommandName>` with a flat JSON body (e.g. `{"ImportData": ..., "ImportNote": ...}`). Returns a **Request ID** immediately; the actual change runs in the background. Status can be checked via the `/Apps/SM/APIv2/Query/DomainModel/WorkflowExecutions` query resource with `CommandRequestRecordID`. | APICMD |
| Command *datasets* (older v2 convention) | Some commands — including the one we use for "mark opened" — are invoked as a **dataset**, through the exact same generic `POST {base_url}/api/v2/execute` endpoint the Query API uses (`{"post": "{\"action\":\"exec\",\"dataset\":{\"datasetname\":\"<path>\"},\"parameters\":[...]}"}`), not the dedicated REST command path. The response is `dataset.data.RequestUUID` (a single object, not a row array like queries). Status is checked via `/Apps/SM/APIv2/Query/CommandStatus/CommandStatusCheck` with `RequestUUID`, polling until `MainStatus == "Done"`. Don't assume the REST-style convention applies to every command — check the specific use-case article. | SIPB |
| "Mark opened" | The API's actual, purpose-built command for this: `/Apps/SM/APIv2/Command/SurveyInstances/BulkProcessing_SetReadStatus`, called via the command-dataset convention above, with parameters `SurveyInstancesIDsCSV` (CSV of survey instance IDs) and `ReadStatus=1`. This is literally described as marking "the loaded survey instances with Opened Status 1... so that when the Query API is called again, only new surveys will be downloaded" — it flips the exact same `IsSurveyInstanceViewedBySecurityUser` field our extraction filters on, closing the extract→mark-opened loop precisely. This supersedes an earlier, incorrect implementation (see below). | SIPB |

**Decision (corrected):** "Mark opened" = call `BulkProcessing_SetReadStatus` with `ReadStatus=1` for each newly-loaded survey instance ID. This is Shopmetrics' own documented mechanism for precisely this ETL scenario (SIPB is literally titled "Shopmetrics Integration with Power BI via an ETL Process" and walks through extract → load into SQL Server → mark opened → BI consumption — the same shape as this project). **Tested live and currently fails with HTTP 500 — see §10.3** — kept as the default because it's still the conceptually correct match, pending confirmation from Shopmetrics of the current equivalent.

**Superseded decision (kept for context):** the original implementation of this spec used `JobSetJobQualityControlAttributesRequests` to set `ClientAccessStatus = "OK for Client Access"` instead, reasoning that no literal "mark opened" command existed. That reasoning was based on an incomplete read of the knowledgebase — `BulkProcessing_SetReadStatus` was in an Integration Examples article not yet reviewed at the time. The QC-attributes route is a real, valid command (confirmed against the real API — see §10.2) but represents a different concept ("grant Client Access status") than "opened/viewed", per the Operations domain's own event vocabulary (`SURVEY.CLIENTACCESSSTAT.SHOWALL` vs. the distinct `SURVEY.RFA.OPEN`). The code keeps both available; `BulkProcessing_SetReadStatus` is now the default.

## 3. Decisions & Assumptions

| Question | Decision |
|---|---|
| Database | Configurable via `DB_BACKEND`: SQLite (default, file-based, zero-install) or local SQL Server / SSMS (`DB_BACKEND=sqlserver`, requires `pyodbc`). Same logical schema either way — see `schema.md`. |
| Extraction source | Configurable: `EXTRACTION_MODE=file` (default) reads `data/sample_surveys.json`; `EXTRACTION_MODE=api` calls the real Query API v2 as described in §2. |
| Command API mode | Configurable: `COMMAND_MODE=mock` (default) simulates a successful "mark opened" call with no network access; `COMMAND_MODE=live` calls the real Command API v2. |
| Base URL | `SHOPMETRICS_BASE_URL`, default `https://training212.shopmetrics.com` (a Shopmetrics training/sandbox site, per APIINV3's recommendation to test against training before production). |
| Auth credentials | `SHOPMETRICS_CLIENT_ID` / `SHOPMETRICS_CLIENT_SECRET` — account-specific, must be created by an admin in Shopmetrics (Administration → Tools and Settings → Site Settings → Other → API v2 Authorization – Client Credentials, per APIAUT). Unset by default; only required when `EXTRACTION_MODE=api` or `COMMAND_MODE=live`. |
| Client/Form scope | `SHOPMETRICS_CLIENT_OR_FORM_IDS` — the `ClientOrFormIDs` filter value(s) for the Query API; account-specific, must be looked up via the `Parameter_ClientOrFormIDs` dataset (APICAP). Placeholder default `-995`. |
| Configuration format | Split in two: **`config/config.json`** (checked into git) holds all non-secret settings and defaults; **`.env`** (gitignored) holds secrets (API credentials) and any ad-hoc local overrides. See §7. |
| Distribution / setup | Two `.bat` files at the repo root: `install.bat` (one-time: creates a `.venv`, installs dependencies, seeds `.env` from the template) and `run.bat` (forwards to `manage.py`; bare `run.bat` with no args scrapes the live API, prompting once for credentials if `.env` is empty, then generates the next numbered dashboard and opens it in the browser). Goal: clone the repo on any Windows machine with Python 3.10+, run `install.bat` once, then `run.bat` — no manual Python/pip steps, no manual `.env` editing (the credentials prompt fills it). See §4.2. |
| Source layout | All Python modules live under `src/` (with `src/db/` as the database-access sub-package), separate from `config/` (JSON config), `data/` (sample input + generated SQLite file), `logs/`, and `reports/` (generated dashboard). See §4.1. |

## 4. Project Structure

### 4.1 Directory layout

```
specification/                        (repo root)
├── install.bat                       # One-time setup: venv + dependencies + .env seed
├── run.bat                           # Forwards to manage.py; bare call = safe default run
├── README.md                         # Usage guide
├── SPECIFICATION.md                  # This file
├── TASK_001.md                       # Original task brief
├── schema.md                         # Human-readable schema documentation
├── requirements.txt                  # Core deps (none, by default -- SQLite needs nothing)
├── requirements-sqlserver.txt        # Optional: pyodbc, for DB_BACKEND=sqlserver
├── .env.example                      # Template for secrets (copy to .env, never committed)
├── .env                              # Real secrets (gitignored; created by install.bat)
├── .gitignore
│
├── config/
│   └── config.json                   # All non-secret configuration (checked into git) -- see §7.1
│
├── src/                               # All Python source code
│   ├── manage.py                      # Single CLI entry point: run / view / browse / dashboard / setup-db
│   ├── etl.py                          # ETL pipeline orchestration (also runnable directly, with CLI flags)
│   ├── extract.py                      # Extraction step (file or live Query API)
│   ├── load.py                         # Load step (dedup + insert), portable across DB backends
│   ├── api_client.py                   # Auth + Query API + Command API client
│   ├── browse_surveys.py                # Read-only CLI to explore live Shopmetrics data directly
│   ├── view_data.py                      # Readable, color-highlighted CLI view of collected data
│   ├── generate_dashboard.py              # Generates the self-contained HTML dashboard
│   ├── logger.py                          # Logging setup
│   ├── colors.py                           # Shared ANSI color helpers (etl.py, view_data.py)
│   ├── config.py                          # Configuration loader (config.json + .env layering) -- see §7
│   └── db/                                 # Database-access sub-package
│       ├── __init__.py
│       ├── schema.sql                       # DDL for the SQLite backend
│       ├── schema_sqlserver.sql              # DDL for the SQL Server / SSMS backend
│       └── setup_db.py                       # Creates/opens + migrates the DB for whichever backend is selected
│
├── data/
│   ├── sample_surveys.json            # Sample/mock survey records (file mode input)
│   └── etl.db                          # Generated SQLite database (DB_BACKEND=sqlite; created at runtime)
│
├── logs/
│   └── etl.log                         # Append-only run log (created at runtime)
│
├── reports/
│   ├── dashboard1.html                 # Generated HTML dashboards (created at runtime; numbered,
│   └── dashboard2.html ...             #   never overwritten -- each generation takes the next number)
│
└── .venv/                              # Virtual environment (created by install.bat; gitignored)
```

**Why this split:** `src/` isolates all importable code (so nothing here writes to itself at runtime); `config/` is the single checked-in source of truth for non-secret settings; `data/`, `logs/`, `reports/` hold everything generated at runtime (all gitignored except the sample input file) so a fresh clone starts clean and a `.gitignore`'d wipe of those three folders always returns the repo to a pristine state without touching source code or configuration.

### 4.2 `install.bat` / `run.bat`

Both are designed to be **double-clicked in File Explorer** — that's the
primary intended interaction, not just command-line invocation (though both
work identically either way):

- **`install.bat`** (run once per machine): verifies Python is on `PATH`
  (and, non-fatally, that it's 3.10+), creates a virtual environment at
  `.venv/`, installs `requirements.txt` (empty by default) and
  `requirements-sqlserver.txt` (`pyodbc`, installed by default so the SQL
  Server backend works immediately without a second setup step), and copies
  `.env.example` to `.env` if `.env` doesn't already exist. Ends with
  `pause` ("Press any key to continue . . .") so the summary/errors stay
  on screen — a double-clicked `.bat` file's console window would otherwise
  close instantly on completion, before anything could be read.
- **`run.bat`** (every time you want to use the pipeline). With **no
  arguments** (i.e. a plain double-click) it:
  1. Runs `manage.py run --mode api --no-open` — scrapes the live Query
     API (read-only; mark-opened stays mocked per `COMMAND_MODE`). If
     `.env` has no `SHOPMETRICS_CLIENT_ID`/`SECRET`, the run prompts for
     them right in the console, saves them to `.env` (via
     `config.save_env_values`, which preserves the rest of the file), and
     verifies them with a real token request before continuing.
  2. On success, locates the newest `reports\dashboard*.html` (the run just
     generated the next-numbered one), prints its path, and opens it via
     `start` — the batch script owns the open step on this path, which is
     why the Python side is passed `--no-open` (no double-open).
  3. Ends with a `pause` for the same reason as `install.bat`.
  Any invocation *with* arguments (`run.bat view`, `run.bat run --mode
  file`, `run.bat dashboard --db sqlserver`, etc.) is forwarded verbatim to
  `manage.py` and does **not** pause — that path is for an already-open
  terminal, which stays open on its own (and there the *Python* side
  auto-opens newly generated dashboards, unless `--no-open` /
  `OPEN_DASHBOARD=false`).
- Every path both scripts touch is anchored to `%~dp0` (the `.bat` file's
  own directory), not the current working directory — so they behave
  identically whether double-clicked (Explorer sets cwd to the file's own
  folder) or invoked from a terminal open somewhere else.
- Both scripts are idempotent and safe to re-run — `install.bat` doesn't
  overwrite an existing `.env`, and re-running it against an existing
  `.venv` just upgrades/reinstalls packages in place; `run.bat` never
  modifies `config/config.json`, and touches `.env` only through the
  credentials prompt above (writing exactly the two credential keys).
- **Fresh-clone note:** nothing else is needed on a new device — the
  runtime folders (`data/`, `logs/`, `reports/`) and the SQLite database
  are all created automatically on first use (`os.makedirs` in
  `logger.py`/`setup_db.py`/`generate_dashboard.py`), and dashboard
  numbering simply starts at `dashboard1.html` when `reports/` is empty.

## 5. Data Model

### 5.1 `surveys` table

Stores each extracted survey instance and its processing state. Field names follow the real Client Analytics Query API field names (APICA) where applicable.

| Column | Type | Notes |
|---|---|---|
| `survey_id` | TEXT PRIMARY KEY | `InstanceID` / `SurveyInstanceID` from the Client Analytics Query API. Used for dedup on load. |
| `client_or_form_id` | TEXT | The `ClientOrFormIDs` value the record was extracted under (denormalized, from config/query params — not a per-row API field). |
| `survey_title` | TEXT | `Title` field. |
| `location_store_id` | TEXT | `Loc ID` field. |
| `location_name` | TEXT | `Location Name` field. |
| `submitted_at` | TEXT (ISO 8601) | `Date` field. |
| `score` | REAL, nullable | `ScorePctXX.XX` field. |
| `responses_json` | TEXT | Raw `[QuestionID][ProtoAnswerText][Question Comment]` rows from the second query call, stored as JSON text. |
| `loaded_at` | TEXT (ISO 8601) | When this row was inserted by the ETL. |
| `opened` | INTEGER (0/1) | Whether the "mark opened" Command API call succeeded (submitted; the underlying change is async — see `command_request_id`). |
| `opened_at` | TEXT (ISO 8601), nullable | When it was marked opened. |
| `command_request_id` | TEXT, nullable | `RequestUUID` returned by `BulkProcessing_SetReadStatus`, for status lookup via `CommandStatusCheck`. |
| `open_error` | TEXT, nullable | Error message if the mark-opened call failed. |
| `campaign` | TEXT, nullable | `Campaign` field. |
| `survey_status` | TEXT, nullable | `SurveyStatusName` field. |
| `attachments_count` | INTEGER, nullable | `AttachmentsCount` field. |
| `fieldworker_login` | TEXT, nullable | `Login` field (fieldworker/shopper). |
| `fieldworker_name` | TEXT, nullable | `Shopper Name` field. |
| `workflow_step_id` | INTEGER, nullable | `WorkflowStepID` field. |

Added after the initial release; `src/db/setup_db.py` migrates existing databases
onto this schema automatically (`ALTER TABLE ADD COLUMN`), preserving
previously-collected rows.

### 5.2 `etl_runs` table

One row per pipeline execution — the durable record backing the log file.

| Column | Type | Notes |
|---|---|---|
| `run_id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `started_at` | TEXT (ISO 8601) | |
| `finished_at` | TEXT (ISO 8601) | |
| `surveys_extracted` | INTEGER | Count read from the source. |
| `surveys_loaded` | INTEGER | Count newly inserted (excludes duplicates). |
| `surveys_duplicate` | INTEGER | Count skipped as already present. |
| `surveys_marked_opened` | INTEGER | Count successfully marked via Command API. |
| `error_count` | INTEGER | Total errors encountered during the run. |
| `status` | TEXT | `success`, `partial`, or `failed`. |

`schema.md` / `src/db/schema.sql` document both tables.

## 6. Pipeline Steps

### 6.1 Extract (`extract.py`)

- `EXTRACTION_MODE=file` (default): reads `data/sample_surveys.json`. Each record has at least `survey_id`, `client_or_form_id`, `survey_title`, `location_store_id`, `location_name`, `submitted_at`, `score`, `responses`.
- `EXTRACTION_MODE=api`: calls `api_client.query_new_surveys()`, which:
  1. Runs the `ClientAnalytics` dataset with `QuerySpecification` including `SurveyStatusName`, `AttachmentsCount`, `Login`, `Shopper Name`, `WorkflowStepID`, `Campaign`, `IsSurveyInstanceViewedBySecurityUser`, and `[WHERE:IsSurveyInstanceViewedBySecurityUser|0]`, filtered by `SHOPMETRICS_CLIENT_OR_FORM_IDS`.
  2. Collects the returned `InstanceID`s and runs a second `ClientAnalytics` call with `QuerySpecification: [InstanceID][QuestionID][ProtoAnswerText][Question Comment]` filtered by `SurveyInstanceIDs` to get responses.
  3. Merges both into the same normalized record shape as file mode.
- Malformed records are skipped and counted as errors, not fatal to the run.

### 6.2 Load (`load.py`)

- Opens the SQLite connection (creating the DB from `src/db/schema.sql` if it doesn't exist).
- For each extracted record, checks `survey_id` against existing rows.
  - New → insert into `surveys`, `opened = 0`.
  - Existing → skip, count as duplicate.
- Uses the `survey_id` `PRIMARY KEY` constraint as a safety net against races/double-inserts (`INSERT OR IGNORE`).
- Returns `(inserted_ids, duplicate_count)`.

### 6.3 Mark Opened (`api_client.py`)

- For each newly inserted `survey_id`, calls `mark_survey_opened(survey_id)`.
- `COMMAND_MODE=mock` (default): simulates success, no network call — satisfies "simulated ... Command API call" from the DoD and keeps the pipeline runnable offline.
- `COMMAND_MODE=live`: calls `BulkProcessing_SetReadStatus` via the command-dataset convention (§2, SIPB) — `POST {base_url}/api/v2/execute` with:
  ```json
  {
    "post": "{\"action\":\"exec\",\"dataset\":{\"datasetname\":\"/Apps/SM/APIv2/Command/SurveyInstances/BulkProcessing_SetReadStatus\"},\"parameters\":[{\"name\":\"SurveyInstancesIDsCSV\",\"value\":\"<survey_id>\"},{\"name\":\"ReadStatus\",\"value\":\"1\"}]}"
  }
  ```
  and stores the returned `RequestUUID` in `command_request_id`. Tested live and currently fails with HTTP 500 — see §10.3.
- On success: `surveys.opened = 1`, `opened_at = now`.
- On failure (network error, non-2xx): update `surveys.open_error`, leave `opened = 0`, increment the run's `error_count`. Does not abort the run — other surveys continue processing.

### 6.4 Logging (`logger.py`)

- Configures a logger that writes to both console and `logs/etl.log` (append mode).
- Each run logs at minimum: start/end timestamps, counts (extracted, loaded, duplicates, marked opened), and errors (with survey ID + reason).
- On completion, writes the same summary into the `etl_runs` table so the log file and DB stay in sync.
- The post-run dashboard callout (§6.5 step 7) is a separate, direct `print()` in a distinct color (`colors.py`), not routed through the logger — so `logs/etl.log` stays plain text with no ANSI escape codes, while the terminal still gets a highlighted call-to-action.

### 6.5 Main Entry Point (`etl.py`)

Sequential flow, no step is silently swallowed:

1. Initialize logger and DB (idempotent — safe to run repeatedly).
2. Start an `etl_runs` row.
3. Extract → list of survey records (file or live, per `EXTRACTION_MODE`).
4. Load → insert new, skip duplicates.
5. For each newly inserted survey, call the Command API (mock or live, per `COMMAND_MODE`) to mark it opened.
6. Finalize the `etl_runs` row and write the run summary to `logs/etl.log`.
7. Generate a **new numbered** HTML dashboard (`generate_dashboard.generate()` → `reports/dashboard<N>.html`, where `N` is one higher than the highest number already present — earlier reports are never overwritten or deleted) and print a bold cyan callout with its full path. Unless `--no-open` was passed or `OPEN_DASHBOARD=false`, the report is then opened in the default browser (`os.startfile` on Windows — identical to double-clicking the file; `webbrowser` elsewhere). Wrapped in its own try/except — a dashboard failure is logged as a warning but never fails the run, since it's a convenience layered on top of the actual ETL result, not part of the DoD. The dashboard itself is a single self-contained file (inline CSS/SVG/JS, no CDN): KPI tiles, a score-distribution chart, status/location/title breakdowns, run history (error counts highlighted when non-zero), and a table of **every** stored survey with live search (by ID or any text), an All/Opened/Not-opened quick filter, sortable columns, and a **Details** modal (opened by clicking any row) showing the full record plus `responses_json` rendered per-question (answers as chips, comments quoted, raw JSON collapsible), with prev/next navigation (buttons or arrow keys) stepping through the currently filtered/sorted rows.
8. Exit code `0` if the run completed (even with individual survey errors, or a dashboard-generation failure); non-zero only on an unhandled/fatal error in the core pipeline (e.g. DB unreachable), or when API credentials are required but missing and can't be prompted for (§4.2).

`etl.py` accepts CLI flags (`--mode`, `--command-mode`, `--db`, `--max-records`,
`--no-open`) that override the corresponding config value for that invocation
only — `config/config.json` is never touched (and `.env` only by the explicit
credentials prompt, §4.2). `manage.py run` exposes
the same flags via a unified entry point that also wraps `view_data.py`,
`browse_surveys.py`, `generate_dashboard.py`, and `src/db/setup_db.py` (see
`manage.py view|browse|dashboard|setup-db`).

## 7. Configuration

`src/config.py` resolves every setting by layering four sources, **highest
precedence first**:

1. **Real environment variables** — anything already set in the shell, or
   set at runtime by a CLI flag (`--mode`, `--db`, etc., in `etl.py`/`manage.py`).
2. **`.env`** (repo root, gitignored) — secrets and any ad-hoc local override.
3. **`config/config.json`** (repo root, checked into git) — the project's
   checked-in, non-secret configuration and defaults.
4. **Hardcoded fallback** in `config.py` itself, only used if `config.json`
   is missing entirely (defense in depth — the repo always ships one).

This means: edit `config/config.json` for anything you want permanently
changed and shared via git; put secrets or a one-off override in `.env`;
use a CLI flag or shell env var for a one-time override that doesn't touch
either file.

### 7.1 `config/config.json` — non-secret settings

| Key | Default | Purpose |
|---|---|---|
| `DB_BACKEND` | `"sqlite"` | `sqlite` (zero-dependency) or `sqlserver` (local SQL Server / SSMS, requires `pyodbc`). |
| `DB_PATH` | `"data/etl.db"` | SQLite file location (when `DB_BACKEND=sqlite`). Relative paths resolve against the repo root. |
| `SURVEYS_SOURCE_PATH` | `"data/sample_surveys.json"` | Extraction input for file mode. |
| `LOG_PATH` | `"logs/etl.log"` | Log file location. |
| `EXTRACTION_MODE` | `"file"` | `file` or `api`. |
| `COMMAND_MODE` | `"mock"` | `mock` or `live`. |
| `SHOPMETRICS_BASE_URL` | `"https://training212.shopmetrics.com"` | Shopmetrics site base URL. |
| `SHOPMETRICS_CLIENT_OR_FORM_IDS` | `"-995"` | `ClientOrFormIDs` filter value for the Query API. Account-specific placeholder. |
| `SHOPMETRICS_MAX_RECORDS_PER_RUN` | `5000` | Caps survey instances pulled per run in `api` mode. Set high enough to collect this account's full backlog (~1800) in one run; still just 2 API calls per run regardless of row count, so within fair use (APIINT). Lower per-run via `--max-records`. |
| `OPEN_DASHBOARD` | `"true"` | Auto-open the newly generated `reports/dashboard<N>.html` in the default browser after `run`/`dashboard`. Per-run opt-out: `--no-open`. |
| `SQLSERVER_DRIVER` | `"ODBC Driver 18 for SQL Server"` | ODBC driver name for the SQL Server backend. |
| `SQLSERVER_SERVER` | `".\\SQLEXPRESS"` | SQL Server instance name (when `DB_BACKEND=sqlserver`). |
| `SQLSERVER_DATABASE` | `"ShopmetricsETL"` | SQL Server database name; created automatically if missing. |
| `SQLSERVER_TRUSTED_CONNECTION` | `"yes"` | Windows Authentication toggle for the ODBC connection string. |
| `SQLSERVER_TRUST_SERVER_CERTIFICATE` | `"yes"` | Needed for ODBC Driver 18's stricter default TLS validation against a local instance. |

Every key's JSON name matches its environment-variable name exactly
(`config.py` does `os.environ.setdefault(key, str(value))` for each entry),
so overriding any of them via `.env` or a shell variable needs no translation.

### 7.2 `.env` — secrets (never committed)

| Variable | Default | Purpose |
|---|---|---|
| `SHOPMETRICS_CLIENT_ID` | *(unset)* | OAuth2 client_credentials client ID. Required for `api`/`live` modes. |
| `SHOPMETRICS_CLIENT_SECRET` | *(unset)* | OAuth2 client_credentials client secret. Required for `api`/`live` modes. |
| `SQLSERVER_USER` / `SQLSERVER_PASSWORD` | *(unset)* | SQL Server auth; if unset, uses Windows Authentication (Trusted Connection). |

`.env.example` documents these, plus commented-out examples of overriding
any `config/config.json` key locally without editing the checked-in file.

The two credential keys don't have to be filled in by hand: any run that
needs the real API (`EXTRACTION_MODE=api` or `COMMAND_MODE=live`) checks for
them first (`etl.ensure_api_credentials`), and — when running in an
interactive console — prompts for both values, writes them into `.env`
(`config.save_env_values`), and verifies them with a real token request
before proceeding. Non-interactive invocations print instructions and exit
with code 1 instead of hanging on a prompt.

## 8. Sample Data Shape (file mode)

```json
[
  {
    "survey_id": "125746",
    "client_or_form_id": "-995",
    "survey_title": "Q3 Store Visit",
    "location_store_id": "STR-042",
    "location_name": "Acme Retail - Downtown",
    "submitted_at": "2026-06-28T14:32:00Z",
    "score": 87.5,
    "responses": [
      { "question_id": "1791", "answer_text": "Yes", "comment": "Shelf was fully stocked." }
    ]
  }
]
```

## 9. Definition of Done — Mapping

| DoD item | Satisfied by |
|---|---|
| `etl.py` runs end to end on sample data without errors | §6.5 flow over `data/sample_surveys.json` in default `EXTRACTION_MODE=file` / `COMMAND_MODE=mock` |
| Schema documented | `schema.md` / `src/db/schema.sql` (§5) |
| Sample records appear in DB after a run | `load.py` insert step (§6.2) |
| Each loaded survey marked opened (real or simulated) | `api_client.py` (§6.3): mock by default, real `BulkProcessing_SetReadStatus` call when `COMMAND_MODE=live` |
| Log file shows a completed run with counts/errors | `logger.py` + `logs/etl.log` (§6.4) |

## 10. Switching to the Real API

To run against a real Shopmetrics training/production site:

1. Create a Restricted-role user + API Client Credentials in Shopmetrics (Administration → Tools and Settings → Site Settings → Other → API v2 Authorization – Client Credentials). See APIAUT.
2. Look up your `ClientOrFormIDs` value via the `Parameter_ClientOrFormIDs` dataset (APICAP).
3. Put `SHOPMETRICS_CLIENT_ID` and `SHOPMETRICS_CLIENT_SECRET` in `.env` (copy `.env.example` if you haven't already — `install.bat` does this automatically). Set `SHOPMETRICS_BASE_URL` and `SHOPMETRICS_CLIENT_OR_FORM_IDS` either in `.env` or in `config/config.json`.
4. Run `run.bat run --mode api --command-mode live` (or `python src/manage.py run --mode api --command-mode live` without the bat file). The training site is recommended before production (APIINV3).

### 10.1 Verified against the real training212 account

Extraction (`EXTRACTION_MODE=api`) has been run live against `https://training212.shopmetrics.com` with real credentials and confirmed working end to end: OAuth2 token acquisition, the `ClientAnalytics` list query, and the responses query all returned real data (1804 survey instances under `ClientOrFormIDs=-995`, "Delight Coffee (CX Analytics Demo)").

Two implementation details only became clear by hitting the real API (not documented explicitly in the KB articles read so far):

- **Query API transport**: despite `/api/v2/execute` looking like a JSON endpoint, it actually expects a standard form-encoded body with a single `post` field (matching the PowerShell `Invoke-RestMethod -Body @{post=...}` examples) — a JSON request body is rejected with `DatasetValidationErrorEmptyJson`. `api_client._execute_dataset` sends it this way.
- **WAF/User-Agent**: the site blocks Python's default `urllib` User-Agent with an HTTP 403 (Cloudflare error 1010). `api_client.py` sends a browser-style `User-Agent` header on every request to avoid this.

### 10.2 Superseded finding: `JobSetJobQualityControlAttributesRequests` (kept for context)

Before `BulkProcessing_SetReadStatus` (§2) was found, the "mark opened" live Command API call (`COMMAND_MODE=live`) was tested against `JobSetJobQualityControlAttributesRequests` on a real survey instance. It reached the real endpoint successfully (correct auth, URL, and JSON body — this call *is* accepted as plain JSON, unlike the Query API). It returned a genuine business-rule validation error: `"Invalid Survey Status. Survey Instance should be in \"Completed\" status"`. Investigating further:

- The `ClientAnalytics` domain, by definition (APICADQ), only returns surveys already in "OK for Client Access" status — every one of the 1804 rows checked came back as `SurveyStatusName = "Completed Exported"`, i.e. already past the "Completed" stage the QC command requires. No `ClientOrFormIDs` value changes this — it's inherent to the domain.
- A survey eligible for the QC command (still "Completed", not yet exported) would need to come from the **Operations** query domain (APIIOP) instead. Querying `Operations_Fields` for this account returned only one field (`SurveyInstancesCount`, an aggregate), rather than the full field list APIOP documents.
- Why: the configured API user follows the "Client User" API-consumer pattern (per **APIECU**, "Granting Access for Shopmetrics API Consumption") — Client User security role + `Myst.ClientAccess.API` security group + Client Access "View" permission. That combination grants Client-Analytics-flavored access (Clients/Forms/Locations/CustomProperties) only, not Operations/Survey Manager data. The "Administrator - Restricted" role required by `JobSetJobQualityControlAttributesRequests` isn't unique to that command either — every "Command APIs for Fieldwork and Job Management" use case reviewed (Create Survey Instances/APICICR, Import Survey Data/APIIDCR, Return Jobs to Fieldworkers/APIRJCR, Import Attachments v3/APIIACR) requires the same role. So this was never going to work with a Client-User-provisioned credential, regardless of survey status.
- Side note if this route is ever revisited: **APICICR** states any survey instance created via that Command API "will have a status of 'Completed'" — a cheap way to manufacture a test instance eligible for the QC command, if broader access is ever granted.

This command remains implemented in `api_client.py` (`grant_client_access_live`) since it's real and valid — it just answers a different question ("grant Client Access status") than "mark opened" (see §2's corrected decision).

### 10.3 `BulkProcessing_SetReadStatus` — tested live, currently fails (likely deprecated)

Tested against `https://training212.shopmetrics.com` on survey instance `10001` (confirmed `IsSurveyInstanceViewedBySecurityUser = 0` beforehand). The call fails with **HTTP 500 Internal Server Error** (`{"status":"Error","message":"Internal Server Error","trackingId":"..."}`), reproduced twice with two different parameter shapes (with and without the explicit `SecurityObjectUserID`/`MiscSettings` null parameters from SIPB's exact example) — ruling out a parameter-format issue. This platform instance reports `Microsoft SQL Server 2025` as its backing database (per `SELECT @@VERSION` via `sqlcmd`), while SIPB is dated 2023-02-10 — markedly older than every other article in the corpus (2024-2026). The most likely explanation: `/Apps/SM/APIv2/Command/SurveyInstances/BulkProcessing_SetReadStatus` has been renamed, restructured, or removed since SIPB was written, and this training site runs a newer platform version than the dataset targets.

**Net result:** neither "mark opened" candidate actually completes successfully against this account today — `BulkProcessing_SetReadStatus` 500s (this section), and `JobSetJobQualityControlAttributesRequests`/`grant_client_access_live` is blocked by account permissions and survey status (§10.2). The code still implements `BulkProcessing_SetReadStatus` as the default for `COMMAND_MODE=live` because it remains the conceptually correct match if Shopmetrics support confirms the current equivalent dataset name (worth asking them directly, given "Support is available at hourly rates" per APIINT) — but until then, treat `COMMAND_MODE=live` as **not currently functional** on this account, and keep using `COMMAND_MODE=mock` (the default) for real runs.

### 10.4 Known gap: survey responses may include every answer option, not just the one given

Our extraction's second query (`[InstanceID][QuestionID][ProtoAnswerText][Question Comment]`, §2) has been confirmed in practice to return **every possible answer option** per question, not just the one the shopper selected (e.g. a Yes/No question returns both a "Yes" row and a "No" row for the same instance/question). The Operations domain's `SurveyInstanceData` query resource (**APIOSID**) looks like it might return only the answer actually given (it's described as separate rowsets for "questions with comments" vs. "questions with answers"), but this couldn't be verified — it lives in the Operations domain, which the current account can't access (§10.2). Revisit if broader Operations access is ever granted; until then, `responses_json` should be read as "the full answer-option set alongside whichever one carries a comment", not as a clean single-answer record. **Still unresolved** — this is the one open item left from the audit (the other, §10.3, is resolved: tested and confirmed failing).

## 11. Knowledgebase Audit Log

The full `_KNOWLEDGEBASE/023-APIs/` tree (62 articles) has been read at least once as of this revision — the ~20 articles cited throughout §2–§10 directly, plus ~42 more (all remaining Query/Command API resource and use-case articles, both v2 and v3) specifically checked for contradictions with this spec. Outcome:

- **1 correction made**: the "mark opened" mechanism (§2) — see §10.2/§10.3 for the full story.
- **Confirmed, no change needed**: `ClientOrFormIDs` semantics, Query API field names/transport, OAuth2 flow, v2 vs. v3 Command API conventions (structurally different — don't mix them if v3 is ever added), and the general Command-API async-request pattern.
- **1 correction verified live, and it fails**: §10.3 — `BulkProcessing_SetReadStatus` was tested against the real account and returns HTTP 500, likely deprecated on this platform version. `COMMAND_MODE=live` should be treated as non-functional until Shopmetrics confirms a current replacement.
- **1 open item still unresolved**: §10.4 (answer-selection extraction gap), blocked on Operations-domain access this account doesn't have.
- Not read in full (skimmed/skipped as not relevant to this project): Countries/Currencies/Language Locales/State-Regions/Time Zones query resources.
