"""Creates/opens the ETL database, dispatching on config.DB_BACKEND:

- "sqlite" (default): opens data/etl.db, creating it from schema.sql if needed.
  Zero third-party dependencies.
- "sqlserver": opens a local SQL Server database (viewable in SSMS),
  creating the database and tables from schema_sqlserver.sql if needed.
  Requires the pyodbc package (see requirements-sqlserver.txt).
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Columns added after the initial schema shipped. New installs get them via
# schema.sql/schema_sqlserver.sql directly; existing databases get them
# migrated in here (ALTER TABLE ADD COLUMN IF NOT EXISTS) so no data is lost.
_NEW_SURVEY_COLUMNS = [
    # (column name, SQLite type, SQL Server type)
    ("campaign", "TEXT", "NVARCHAR(50)"),
    ("survey_status", "TEXT", "NVARCHAR(100)"),
    ("attachments_count", "INTEGER", "INT"),
    ("fieldworker_login", "TEXT", "NVARCHAR(100)"),
    ("fieldworker_name", "TEXT", "NVARCHAR(200)"),
    ("workflow_step_id", "INTEGER", "INT"),
]

# Columns that were added in a later pass (to capture the full Client
# Analytics field set) and then reverted -- nothing in this codebase
# (dashboard, view, delete-surveys filters) ever actually read them, so
# they were dropped again rather than left as dead NULL columns. Kept here
# so any database that picked up the add-migration (this project's own
# included) gets cleanly cleaned up too, via ALTER TABLE DROP COLUMN
# (SQLite 3.35+ and SQL Server both support it) -- a database that never
# had them just no-ops on each one.
_REMOVED_SURVEY_COLUMNS = [
    "location_address1", "location_address2", "location_city", "location_state",
    "location_postal_code", "location_photo_url", "points", "points_of",
    "custom_location_property_1", "custom_location_property_2", "custom_location_property_3",
    "client_access_status_id", "rfa_status_id", "rfas_open", "rfas_closed",
    "is_being_exported", "is_export_completed_but_failed", "is_ok_for_export",
    "hold_export", "is_export_completed", "section_level1_weight_defined",
    "client_audit_mode", "last_validated_at",
]


def _migrate_sqlite_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(surveys)")}
    for name, sqlite_type, _ in _NEW_SURVEY_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE surveys ADD COLUMN {name} {sqlite_type}")
    for name in _REMOVED_SURVEY_COLUMNS:
        if name in existing:
            conn.execute(f"ALTER TABLE surveys DROP COLUMN {name}")
    conn.commit()


def _migrate_sqlserver_columns(conn) -> None:
    for name, _, sqlserver_type in _NEW_SURVEY_COLUMNS:
        conn.execute(
            f"IF COL_LENGTH('dbo.surveys', '{name}') IS NULL "
            f"ALTER TABLE dbo.surveys ADD {name} {sqlserver_type} NULL;"
        )
    for name in _REMOVED_SURVEY_COLUMNS:
        conn.execute(
            f"IF COL_LENGTH('dbo.surveys', '{name}') IS NOT NULL "
            f"ALTER TABLE dbo.surveys DROP COLUMN {name};"
        )
    conn.commit()


def _get_sqlite_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    except sqlite3.DatabaseError as e:
        sys.exit(
            f"{config.DB_PATH} doesn't look like a valid SQLite database ({e}).\n"
            f"It may be corrupted (e.g. an interrupted write) or not a database file at\n"
            f"all. If you don't need what's in it, delete/rename it and re-run -- a fresh\n"
            f"one is created automatically. Otherwise restore it from a backup."
        )
    except FileNotFoundError as e:
        sys.exit(
            f"Missing schema file: {e.filename}\n"
            f"Your checkout may be incomplete -- try re-cloning the repository."
        )
    _migrate_sqlite_columns(conn)
    return conn


def _sqlserver_connection_string(database: str) -> str:
    parts = [
        f"DRIVER={{{config.SQLSERVER_DRIVER}}}",
        f"SERVER={config.SQLSERVER_SERVER}",
        f"DATABASE={database}",
        f"TrustServerCertificate={config.SQLSERVER_TRUST_SERVER_CERTIFICATE}",
    ]
    if config.SQLSERVER_USER:
        parts.append(f"UID={config.SQLSERVER_USER}")
        parts.append(f"PWD={config.SQLSERVER_PASSWORD}")
    else:
        parts.append(f"Trusted_Connection={config.SQLSERVER_TRUSTED_CONNECTION}")
    return ";".join(parts) + ";"


def _get_sqlserver_connection():
    try:
        import pyodbc
    except ImportError:
        sys.exit(
            "DB_BACKEND=sqlserver needs the 'pyodbc' package, which isn't installed.\n"
            "Run install.bat again (it installs it by default), or manually:\n"
            "  .venv\\Scripts\\python.exe -m pip install -r requirements-sqlserver.txt"
        )

    try:
        # 1. Ensure the target database exists (connect to master to check/create it).
        master_conn = pyodbc.connect(_sqlserver_connection_string("master"), autocommit=True)
        master_conn.execute(
            f"IF DB_ID(N'{config.SQLSERVER_DATABASE}') IS NULL "
            f"CREATE DATABASE [{config.SQLSERVER_DATABASE}];"
        )
        master_conn.close()

        # 2. Connect to the target database and ensure tables exist.
        conn = pyodbc.connect(_sqlserver_connection_string(config.SQLSERVER_DATABASE))
    except pyodbc.Error as e:
        sys.exit(
            f"Could not connect to SQL Server ({config.SQLSERVER_SERVER}): {e}\n"
            f"Check that SSMS/SQL Server Express is installed and SQLSERVER_SERVER\n"
            f"(config/config.json) matches your actual instance name -- see README.md\n"
            f"section 3 for troubleshooting."
        )

    with open(config.SCHEMA_SQLSERVER_PATH, "r", encoding="utf-8") as f:
        conn.execute(f.read())
    conn.commit()
    _migrate_sqlserver_columns(conn)
    return conn


def get_connection():
    if config.DB_BACKEND == "sqlserver":
        return _get_sqlserver_connection()
    return _get_sqlite_connection()


if __name__ == "__main__":
    get_connection().close()
    if config.DB_BACKEND == "sqlserver":
        print(f"Database ready: {config.SQLSERVER_SERVER} / {config.SQLSERVER_DATABASE} (open in SSMS to view)")
    else:
        print(f"Database ready at {config.DB_PATH}")
