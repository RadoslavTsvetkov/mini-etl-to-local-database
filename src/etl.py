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
from colors import BOLD, CYAN, GREEN, RED, RESET, YELLOW
from db.setup_db import get_connection
from logger import get_logger

logger = get_logger()


def _prompt_for_credentials() -> bool:
    """Asks for both credential values in the console and writes them to
    .env. Returns False if the user cancels or leaves either one empty."""
    try:
        client_id = input("  Shopmetrics Client ID: ").strip()
        client_secret = input("  Shopmetrics Client Secret: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{RED}Cancelled — fill in .env manually and run again.{RESET}")
        return False

    if not client_id or not client_secret:
        print(f"\n{RED}Both values are required — nothing saved. Fill in .env (see")
        print(f".env.example) or run this again and enter them at the prompt.{RESET}")
        return False

    config.SHOPMETRICS_CLIENT_ID = client_id
    config.SHOPMETRICS_CLIENT_SECRET = client_secret
    config.save_env_values(
        {"SHOPMETRICS_CLIENT_ID": client_id, "SHOPMETRICS_CLIENT_SECRET": client_secret}
    )
    print(f"\n{GREEN}Credentials saved to .env (gitignored — they stay on this machine).{RESET}")
    return True


def ensure_api_credentials() -> bool:
    """Called before any run that talks to the real Shopmetrics API
    (EXTRACTION_MODE=api or COMMAND_MODE=live). Missing credentials are
    asked for right here in the console; credentials the API *rejects*
    (mistyped, deactivated, or regenerated in Shopmetrics) trigger the same
    prompt so they can be re-entered and rewritten in .env. Every attempt —
    including already-saved credentials — is verified with a real token
    request before the run proceeds (no extra API cost: the token is needed
    for extraction anyway and is cached for the rest of the run).
    Returns False (after explaining what to do) when valid credentials
    can't be obtained."""
    interactive = sys.stdin.isatty()

    if not (config.SHOPMETRICS_CLIENT_ID and config.SHOPMETRICS_CLIENT_SECRET):
        print(f"\n{BOLD}{YELLOW}Shopmetrics API credentials are not set up yet.{RESET}")
        print("This run needs the real API, which requires a Client ID and Client Secret")
        print("(created in Shopmetrics under Administration → Tools and Settings →")
        print("Site Settings → Other → API v2 Authorization – Client Credentials).\n")
        if not interactive:
            print(f"{RED}Fill in SHOPMETRICS_CLIENT_ID and SHOPMETRICS_CLIENT_SECRET in the")
            print(f".env file (see .env.example), then run this again.{RESET}")
            return False
        if not _prompt_for_credentials():
            return False

    while True:
        print("Verifying credentials against the API...", end=" ", flush=True)
        try:
            api_client.get_access_token()
            print(f"{GREEN}OK.{RESET}")
            return True
        except api_client.ShopmetricsAPIError as e:
            print(f"{RED}failed.{RESET}")
            reason = str(e)[:300]
            if "Network error" in reason:
                # Can't tell anything about the credentials if the API is
                # unreachable — don't ask to rewrite values that may be fine.
                print(f"{RED}Could not reach the API to verify credentials: {reason}{RESET}")
                print(f"{RED}Check your connection / SHOPMETRICS_BASE_URL and run again.{RESET}")
                return False
            print(f"{RED}The API rejected these credentials: {reason}{RESET}")
            if not interactive:
                print(f"{RED}Update SHOPMETRICS_CLIENT_ID / SHOPMETRICS_CLIENT_SECRET in .env")
                print(f"(or reactivate/regenerate them in Shopmetrics), then run again.{RESET}")
                return False
            print(f"\n{YELLOW}Let's re-enter them (the values in .env will be rewritten):{RESET}")
            if not _prompt_for_credentials():
                return False


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
    parser.add_argument("--no-open", action="store_true", help="Don't open the regenerated dashboard in the browser")
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
    if getattr(args, "no_open", False):
        config.OPEN_DASHBOARD = False


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
    if (config.EXTRACTION_MODE == "api" or config.COMMAND_MODE == "live") and not ensure_api_credentials():
        return 1

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
            opened_note = ""
            if config.OPEN_DASHBOARD and generate_dashboard.open_in_browser(dashboard_path):
                opened_note = " (opened in your browser — pass --no-open to skip)"
            print(f"\n{BOLD}{CYAN}Dashboard updated{opened_note}: {dashboard_path}{RESET}\n")
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
