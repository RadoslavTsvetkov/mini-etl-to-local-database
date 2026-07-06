"""Main entry point for the Client Analytics Survey ETL pipeline.

Flow: extract -> load (dedup) -> mark opened via Command API -> log run summary.
See SPECIFICATION.md for the full design and how this maps to the real
Shopmetrics API v2.
"""

import argparse
import sys
from datetime import datetime, timezone

import api_client
import config
import extract
import generate_dashboard
import load
from colors import BOLD, CYAN, RESET
from db.setup_db import get_connection
from logger import get_logger

logger = get_logger()


def build_arg_parser(add_help: bool = True) -> argparse.ArgumentParser:
    """CLI flags that override the corresponding .env/config value for this
    run only -- .env itself is left untouched. Shared with manage.py (which
    reuses this via `parents=`, hence add_help=False there)."""
    parser = argparse.ArgumentParser(
        description="Run the Client Analytics Survey ETL pipeline.", add_help=add_help
    )
    parser.add_argument("--mode", choices=["file", "api"], help="Extraction source (default: EXTRACTION_MODE from .env)")
    parser.add_argument("--command-mode", choices=["mock", "live"], help="Mark-opened Command API mode (default: COMMAND_MODE from .env)")
    parser.add_argument("--db", choices=["sqlite", "sqlserver"], help="Database backend (default: DB_BACKEND from .env)")
    parser.add_argument("--max-records", type=int, help="Max survey instances to pull in api mode (default: SHOPMETRICS_MAX_RECORDS_PER_RUN from .env)")
    return parser


def apply_overrides(args: argparse.Namespace) -> None:
    if args.mode:
        config.EXTRACTION_MODE = args.mode
    if args.command_mode:
        config.COMMAND_MODE = args.command_mode
    if args.db:
        config.DB_BACKEND = args.db
    if args.max_records:
        config.SHOPMETRICS_MAX_RECORDS_PER_RUN = args.max_records


def start_run(conn) -> int:
    now = datetime.now(timezone.utc).isoformat()
    if config.DB_BACKEND == "sqlserver":
        # pyodbc cursors have no lastrowid; use OUTPUT to get the new IDENTITY value.
        cursor = conn.execute(
            "INSERT INTO etl_runs (started_at, status) OUTPUT INSERTED.run_id VALUES (?, 'running')",
            (now,),
        )
        run_id = cursor.fetchone()[0]
        conn.commit()
        return run_id

    cursor = conn.execute(
        "INSERT INTO etl_runs (started_at, status) VALUES (?, 'running')", (now,)
    )
    conn.commit()
    return cursor.lastrowid


def finish_run(conn, run_id: int, extracted: int, loaded: int, duplicates: int,
                marked_opened: int, error_count: int, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE etl_runs
        SET finished_at = ?, surveys_extracted = ?, surveys_loaded = ?,
            surveys_duplicate = ?, surveys_marked_opened = ?, error_count = ?, status = ?
        WHERE run_id = ?
        """,
        (now, extracted, loaded, duplicates, marked_opened, error_count, status, run_id),
    )
    conn.commit()


def run() -> int:
    logger.info("=== ETL run starting (EXTRACTION_MODE=%s, COMMAND_MODE=%s) ===",
                config.EXTRACTION_MODE, config.COMMAND_MODE)

    try:
        conn = get_connection()
    except Exception as e:
        logger.error("Fatal: could not initialize database: %s", e)
        return 1

    run_id = start_run(conn)
    error_count = 0

    try:
        records, extract_errors = extract.extract()
        for err in extract_errors:
            logger.warning("Extraction error: %s", err)
        error_count += len(extract_errors)
        logger.info("Extracted %d survey record(s)", len(records))

        inserted_ids, duplicate_count = load.load_surveys(conn, records)
        logger.info(
            "Loaded %d new survey(s), skipped %d duplicate(s)",
            len(inserted_ids), duplicate_count,
        )

        marked_opened = 0
        for survey_id in inserted_ids:
            try:
                request_id = api_client.mark_survey_opened(survey_id)
                load.mark_opened(conn, survey_id, request_id)
                marked_opened += 1
                logger.info("Marked survey %s as opened (request_id=%s)", survey_id, request_id)
            except api_client.ShopmetricsAPIError as e:
                load.mark_open_error(conn, survey_id, str(e))
                error_count += 1
                logger.error("Failed to mark survey %s as opened: %s", survey_id, e)

        status = "success" if error_count == 0 else "partial"
        finish_run(conn, run_id, len(records), len(inserted_ids), duplicate_count,
                   marked_opened, error_count, status)

        logger.info(
            "=== ETL run finished: status=%s extracted=%d loaded=%d duplicates=%d "
            "marked_opened=%d errors=%d ===",
            status, len(records), len(inserted_ids), duplicate_count, marked_opened, error_count,
        )

        try:
            dashboard_path = generate_dashboard.generate()
            print(f"\n{BOLD}{CYAN}Dashboard updated — check it out: {dashboard_path}{RESET}\n")
        except Exception as e:
            logger.warning("Could not regenerate the dashboard: %s", e)

        return 0

    except Exception as e:
        logger.exception("Fatal error during ETL run: %s", e)
        finish_run(conn, run_id, 0, 0, 0, 0, error_count + 1, "failed")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    apply_overrides(build_arg_parser().parse_args())
    sys.exit(run())
