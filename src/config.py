"""Configuration for the Client Analytics Survey ETL pipeline.

Layered, highest precedence first:
1. Real environment variables (e.g. `$env:DB_BACKEND = "..."`, or CLI flags
   like `--mode`/`--db` in etl.py/manage.py, which set config.* attributes
   directly at runtime).
2. `.env` (repo root, gitignored) -- secrets (SHOPMETRICS_CLIENT_ID/SECRET,
   optional SQLSERVER_USER/PASSWORD) and any ad-hoc local overrides.
3. `config/config.json` (repo root, checked into git) -- the project's
   checked-in, non-secret configuration and defaults.
4. Hardcoded fallback in this file, only used if config.json is missing.
"""

import json
import os
import sys

# src/config.py -> parent is the project root (config/, data/, logs/, etc.)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_JSON_PATH = os.path.join(PROJECT_ROOT, "config", "config.json")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def _load_dotenv(path: str) -> None:
    """Minimal .env loader (KEY=VALUE per line, '#' comments). Does not
    override variables already set in the real environment. Keeps the
    project dependency-free (no python-dotenv)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _load_json_config(path: str) -> None:
    """Loads config/config.json as env-var defaults (lowest precedence of
    the three layers -- only fills keys not already set by .env or a real
    environment variable). A missing file is fine (falls back to the
    hardcoded defaults below); a present-but-broken file is not something
    to silently ignore or crash on with a raw traceback -- every command
    imports this module, so this is the one place a bad edit to
    config.json would otherwise take down the entire program."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(
            f"config/config.json is not valid JSON ({e.msg} at line {e.lineno}, column {e.colno}).\n"
            f"Fix the syntax error, or restore the file from git (`git checkout -- config/config.json`)."
        )
    if not isinstance(data, dict):
        sys.exit("config/config.json must be a JSON object ({\"KEY\": \"value\", ...}), "
                 f"got {type(data).__name__}.")
    for key, value in data.items():
        os.environ.setdefault(key, str(value))


# Load order matters: .env first (so it can override config.json), then
# config.json (fills whatever's still unset). Real env vars set before
# either of these runs always win, since setdefault() never overwrites.
_load_dotenv(ENV_PATH)
_load_json_config(CONFIG_JSON_PATH)


def save_env_values(updates: dict) -> None:
    """Writes KEY=VALUE pairs into .env, replacing existing lines for those
    keys (commented or not) and appending any that aren't present. Keeps
    every other line untouched. Used by the interactive credentials prompt."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    remaining = dict(updates)
    for i, line in enumerate(lines):
        stripped = line.strip().lstrip("#").strip()
        key = stripped.partition("=")[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _resolve_path(value: str) -> str:
    """Relative paths in config are relative to the project root."""
    return value if os.path.isabs(value) else os.path.join(PROJECT_ROOT, value)


# --- Local storage ---
# "sqlite" (default, zero-dependency) or "sqlserver" (local SQL Server /
# SSMS, requires the pyodbc package -- see requirements-sqlserver.txt).
DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite")

DB_PATH = _resolve_path(os.environ.get("DB_PATH", "data/etl.db"))
SCHEMA_PATH = os.path.join(SRC_DIR, "db", "schema.sql")

# SQL Server connection settings, used only when DB_BACKEND=sqlserver.
# Defaults match a local SQL Server Express instance managed via SSMS with
# Windows Authentication (Trusted_Connection) -- no password needed.
SQLSERVER_DRIVER = os.environ.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
SQLSERVER_SERVER = os.environ.get("SQLSERVER_SERVER", r".\SQLEXPRESS")
SQLSERVER_DATABASE = os.environ.get("SQLSERVER_DATABASE", "ShopmetricsETL")
SQLSERVER_TRUSTED_CONNECTION = os.environ.get("SQLSERVER_TRUSTED_CONNECTION", "yes")
SQLSERVER_USER = os.environ.get("SQLSERVER_USER")
SQLSERVER_PASSWORD = os.environ.get("SQLSERVER_PASSWORD")
SQLSERVER_TRUST_SERVER_CERTIFICATE = os.environ.get("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes")
SCHEMA_SQLSERVER_PATH = os.path.join(SRC_DIR, "db", "schema_sqlserver.sql")

SURVEYS_SOURCE_PATH = _resolve_path(os.environ.get("SURVEYS_SOURCE_PATH", "data/sample_surveys.json"))

# Open the regenerated HTML dashboard in the default browser after each
# run / dashboard command. Override per-run with --no-open.
OPEN_DASHBOARD = os.environ.get("OPEN_DASHBOARD", "true").strip().lower() in ("1", "true", "yes", "on")
LOG_PATH = _resolve_path(os.environ.get("LOG_PATH", "logs/etl.log"))

# --- Pipeline mode switches ---
# "api" calls the real Shopmetrics Query API v2 (the default -- a new
# install should scrape real data out of the box, not sample data); "file"
# reads SURVEYS_SOURCE_PATH instead, for fully offline/no-credentials use.
EXTRACTION_MODE = os.environ.get("EXTRACTION_MODE", "api")
# "mock" simulates a successful Command API call; "live" calls the real endpoint.
COMMAND_MODE = os.environ.get("COMMAND_MODE", "mock")

# --- Shopmetrics API v2 (see SPECIFICATION.md section 2 for how these map to
# the real Shopmetrics Query/Command/Auth APIs) ---
SHOPMETRICS_BASE_URL = os.environ.get(
    "SHOPMETRICS_BASE_URL", "https://training212.shopmetrics.com"
).rstrip("/")
SHOPMETRICS_CLIENT_ID = os.environ.get("SHOPMETRICS_CLIENT_ID")
SHOPMETRICS_CLIENT_SECRET = os.environ.get("SHOPMETRICS_CLIENT_SECRET")
SHOPMETRICS_CLIENT_OR_FORM_IDS = os.environ.get("SHOPMETRICS_CLIENT_OR_FORM_IDS", "-995")
# Caps how many survey instances a single API-mode run will pull/process.
# Set high enough (5000) to collect this account's full backlog (~1800
# unopened surveys) in one run. This stays within the KB's Fair Use policy
# (APIINT: no high-volume *consecutive* calls) because a run is always just
# 2 API calls — one list query, one responses query — however many rows
# come back. Lower it per-run with --max-records if you want a small batch.
SHOPMETRICS_MAX_RECORDS_PER_RUN = int(os.environ.get("SHOPMETRICS_MAX_RECORDS_PER_RUN", "5000"))

TOKEN_ENDPOINT = f"{SHOPMETRICS_BASE_URL}/oauth/connect/token"
QUERY_ENDPOINT = f"{SHOPMETRICS_BASE_URL}/api/v2/execute"
# Used by the superseded grant_client_access_live() -- see SPECIFICATION.md
# section 10.2. The actual "mark opened" call (BulkProcessing_SetReadStatus)
# goes through QUERY_ENDPOINT instead, per section 2.
COMMAND_QC_ENDPOINT = f"{SHOPMETRICS_BASE_URL}/api/v2/command/JobSetJobQualityControlAttributesRequests"

CLIENT_ANALYTICS_DATASET = "/Apps/SM/APIv2/Query/ClientAnalytics/ClientAnalytics"

QC_IMPORT_NOTE = "Automated ETL Grant Client Access"
