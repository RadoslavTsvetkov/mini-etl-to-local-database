"""Single entry point for the Client Analytics Survey ETL pipeline's tools.

Usage:
    python manage.py run [--mode file|api] [--command-mode mock|live] [--db sqlite|sqlserver] [--max-records N]
    python manage.py view [all|surveys|runs|<survey_id>]
    python manage.py browse clients
    python manage.py browse surveys --client -995 [--limit N] [--unopened-only]
    python manage.py browse show <survey_id>
    python manage.py dashboard [output_path]
    python manage.py delete-survey <survey_id> [--yes]
    python manage.py delete-surveys [--title ...] [--location ...] [--id-min N --id-max N] [...] [--yes --expect-count N]
    python manage.py clear-surveys [--yes --expect-count N]
    python manage.py serve [--port 8765]
    python manage.py setup-db

Each subcommand is a thin wrapper around the corresponding standalone script
(etl.py, view_data.py, browse_surveys.py, generate_dashboard.py, db/setup_db.py)
-- those still work directly too. This just gives you one script to remember.
"""

import argparse
import sys

import backup
import browse_surveys
import etl
import generate_dashboard
import load
import view_data
from colors import BOLD, GREEN, RED, RESET, YELLOW
from db.setup_db import get_connection
from logger import get_logger


def _db_parent() -> argparse.ArgumentParser:
    """--db flag shared by subcommands that read/write the database but
    aren't the full "run" pipeline (which gets it from etl.build_arg_parser)."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", choices=["sqlite", "sqlserver"], help="Database backend (default: DB_BACKEND from .env)")
    return parser


def _apply_db_override(args: argparse.Namespace) -> None:
    if getattr(args, "db", None):
        import config

        config.DB_BACKEND = args.db


def cmd_run(args: argparse.Namespace) -> int:
    etl.apply_overrides(args)
    return etl.run()


def cmd_view(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    view_data.main(args.target)
    return 0


def cmd_browse(args: argparse.Namespace) -> int:
    browse_surveys.main(args.browse_args)
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    import config

    path = generate_dashboard.generate(args.output)
    opened = not args.no_open and config.OPEN_DASHBOARD and generate_dashboard.open_in_browser(path)
    print(f"Dashboard written to {path}" + (" (opened in your browser)" if opened else ""))
    return 0


def _refresh_dashboard_after_change(args: argparse.Namespace, log_message: str, level: str = "info") -> None:
    """Shared by delete-survey/clear-surveys: writes an audit-trail line to
    logs/etl.log (same logger as the ETL pipeline, so it shows up in the
    same file) and regenerates the dashboard so it reflects the change
    immediately -- mirrors etl.py's own post-run dashboard refresh."""
    import config

    logger = get_logger()
    getattr(logger, level)(log_message)
    try:
        path = generate_dashboard.generate()
        want_open = config.OPEN_DASHBOARD and not getattr(args, "no_open", False)
        opened = want_open and generate_dashboard.open_in_browser(path)
        print(f"Dashboard updated{' (opened in your browser)' if opened else ''}: {path}")
    except Exception as e:
        print(f"{YELLOW}Could not regenerate the dashboard: {e}{RESET}")


def cmd_delete_survey(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    conn = get_connection()
    try:
        record = load.fetch_survey(conn, args.survey_id)
        if record is None:
            print(f"{RED}No survey found with ID {args.survey_id}.{RESET}")
            return 1

        title = record.get("survey_title") or "(untitled)"
        location = record.get("location_name") or "(unknown location)"
        print(f"\n{BOLD}Survey {args.survey_id}{RESET}: {title} — {location}")

        if not args.yes:
            if not sys.stdin.isatty():
                print(f"{RED}Refusing to delete without --yes in a non-interactive context.{RESET}")
                return 1
            try:
                answer = input(f"{YELLOW}Delete this survey permanently? Type 'yes' to confirm: {RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{RED}Cancelled — nothing deleted.{RESET}")
                return 1
            if answer != "yes":
                print("Cancelled — nothing deleted.")
                return 1

        backup_path = backup.backup_survey(record)
        if not load.delete_survey(conn, args.survey_id):
            print(f"{RED}Survey {args.survey_id} was not found when deleting (already removed?).{RESET}")
            return 1

        print(f"{GREEN}Deleted survey {args.survey_id}.{RESET} Backup saved to {backup_path}")
        _refresh_dashboard_after_change(args, f"Deleted survey {args.survey_id} via manage.py delete-survey (backup: {backup_path})")
        return 0
    finally:
        conn.close()


_FILTER_LABELS = {
    "ids": "Survey IDs", "id_min": "Survey ID from", "id_max": "Survey ID to",
    "title": "Title contains", "location": "Location contains", "status": "Status contains",
    "campaign": "Campaign contains", "fieldworker": "Fieldworker contains",
    "date_from": "Date from", "date_to": "Date to (inclusive)",
    "score_min": "Score at least", "score_max": "Score at most", "opened": "Opened",
}


def _args_to_filters(args: argparse.Namespace) -> dict:
    return {
        "ids": [s.strip() for s in args.ids.split(",") if s.strip()] if args.ids else None,
        "id_min": args.id_min,
        "id_max": args.id_max,
        "title": args.title,
        "location": args.location,
        "status": args.status,
        "campaign": args.campaign,
        "fieldworker": args.fieldworker,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "score_min": args.score_min,
        "score_max": args.score_max,
        "opened": {"yes": True, "no": False}.get(args.opened),
    }


def _print_filter_summary(active_filters: dict) -> None:
    for key, value in active_filters.items():
        if key == "opened":
            value = "Yes" if value else "No"
        elif key == "ids":
            value = ", ".join(value)
        print(f"  {_FILTER_LABELS.get(key, key)}: {value}")


def cmd_delete_surveys(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    filters = _args_to_filters(args)
    active_filters = {k: v for k, v in filters.items() if v not in (None, [])}
    if not active_filters:
        print(f"{RED}No filters given — delete-surveys refuses to run with none (that would")
        print(f"match every survey). Use `clear-surveys` if that's actually what you want.{RESET}")
        return 1

    try:
        where_sql, params = load.build_survey_filter(filters)
    except load.FilterError as e:
        print(f"{RED}{e}{RESET}")
        return 1

    conn = get_connection()
    try:
        records = load.fetch_matching_surveys(conn, where_sql, params)
        total = len(records)
        if total == 0:
            print("No surveys match these filters — nothing to delete.")
            return 0

        print(f"\n{BOLD}{RED}This will permanently delete {total:,} survey(s) matching:{RESET}")
        _print_filter_summary(active_filters)
        preview_n = min(10, total)
        print(f"\n{BOLD}Preview (first {preview_n} of {total:,}):{RESET}")
        for r in records[:10]:
            print(f"  {r['survey_id']}  {r.get('survey_title') or '(untitled)'} — "
                  f"{r.get('location_name') or '(unknown)'} — {(r.get('submitted_at') or '')[:10]}")
        if total > 10:
            print(f"  ... and {total - 10:,} more")
        print()

        if args.yes or args.expect_count is not None:
            if not args.yes or args.expect_count != total:
                print(f"{RED}Refusing: needs both --yes and --expect-count {total} (the exact")
                print(f"current match count) to confirm you know what you're about to delete.")
                print(f"Got --expect-count={args.expect_count}.{RESET}")
                return 1
        else:
            if not sys.stdin.isatty():
                print(f"{RED}Refusing without --yes --expect-count {total} in a non-interactive context.{RESET}")
                return 1
            try:
                answer = input(f"Type the number of surveys to confirm ({total}): ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{RED}Cancelled — nothing deleted.{RESET}")
                return 1
            if answer != str(total):
                print("Cancelled — number didn't match. Nothing deleted.")
                return 1

        # Re-check right before deleting -- protects against drift between
        # the confirmation and the delete (same idea as clear-surveys).
        current = load.count_matching_surveys(conn, where_sql, params)
        if current != total:
            print(f"{RED}Match count changed (now {current}) — re-run to see the fresh set. Nothing deleted.{RESET}")
            return 1

        backup_path = backup.backup_filtered_surveys(records)
        deleted = load.delete_matching_surveys(conn, where_sql, params)

        print(f"{GREEN}Deleted {deleted:,} survey(s).{RESET} Backup saved to {backup_path}")
        _refresh_dashboard_after_change(
            args, f"Deleted {deleted} surveys via manage.py delete-surveys (filters: {active_filters}; backup: {backup_path})",
            level="warning",
        )
        return 0
    finally:
        conn.close()


def cmd_clear_surveys(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    conn = get_connection()
    try:
        total = load.count_surveys(conn)
        if total == 0:
            print("No surveys in the database — nothing to clear.")
            return 0

        print(f"\n{BOLD}{RED}This will permanently delete ALL {total:,} surveys from the database.{RESET}")
        print(f"{RED}A JSON backup is written first, but restoring from it is a manual step —{RESET}")
        print(f"{RED}this is not undoable from within the app.{RESET}\n")

        if args.yes or args.expect_count is not None:
            if not args.yes or args.expect_count != total:
                print(f"{RED}Refusing: clear-surveys in a script needs BOTH --yes and")
                print(f"--expect-count {total} (the exact current row count) to confirm you")
                print(f"know what you're about to delete. Got --expect-count={args.expect_count}.{RESET}")
                return 1
        else:
            if not sys.stdin.isatty():
                print(f"{RED}Refusing to clear all surveys without --yes --expect-count {total} in a non-interactive context.{RESET}")
                return 1
            try:
                count_answer = input(f"Type the number of surveys to confirm ({total}): ").strip()
                if count_answer != str(total):
                    print("Cancelled — number didn't match. Nothing deleted.")
                    return 1
                phrase_answer = input('Type "DELETE ALL" to confirm: ').strip()
                if phrase_answer != "DELETE ALL":
                    print("Cancelled — phrase didn't match. Nothing deleted.")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print(f"\n{RED}Cancelled — nothing deleted.{RESET}")
                return 1

        records = load.fetch_all_surveys(conn)
        backup_path = backup.backup_all_surveys(records)
        deleted = load.clear_all_surveys(conn)

        print(f"{GREEN}Deleted {deleted:,} surveys.{RESET} Backup saved to {backup_path}")
        _refresh_dashboard_after_change(
            args, f"Cleared ALL {deleted} surveys via manage.py clear-surveys (backup: {backup_path})", level="warning"
        )
        return 0
    finally:
        conn.close()


def cmd_serve(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    import server

    return server.run(port=args.port, no_open=args.no_open)


def cmd_setup_db(args: argparse.Namespace) -> int:
    _apply_db_override(args)
    import config

    get_connection().close()
    if config.DB_BACKEND == "sqlserver":
        print(f"Database ready: {config.SQLSERVER_SERVER} / {config.SQLSERVER_DATABASE} (open in SSMS to view)")
    else:
        print(f"Database ready at {config.DB_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Client Analytics Survey ETL pipeline.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", parents=[etl.build_arg_parser(add_help=False)], help="Run the ETL pipeline.")
    p_run.set_defaults(func=cmd_run)

    p_view = sub.add_parser("view", parents=[_db_parent()], help="View collected data.")
    p_view.add_argument("target", nargs="?", default="all", help="all | surveys | runs | <survey_id> (default: all)")
    p_view.set_defaults(func=cmd_view)

    p_browse = sub.add_parser("browse", help="Browse live Shopmetrics data directly (read-only).")
    p_browse.add_argument("browse_args", nargs=argparse.REMAINDER, help="clients | surveys --client ... | show <id>")
    p_browse.set_defaults(func=cmd_browse)

    p_dash = sub.add_parser("dashboard", parents=[_db_parent()], help="Generate the HTML dashboard.")
    p_dash.add_argument("output", nargs="?", default=None, help="Output path (default: reports/dashboard.html)")
    p_dash.add_argument("--no-open", action="store_true", help="Don't open the dashboard in the browser")
    p_dash.set_defaults(func=cmd_dashboard)

    p_del = sub.add_parser("delete-survey", parents=[_db_parent()], help="Permanently delete one survey (backed up to JSON first).")
    p_del.add_argument("survey_id", help="Survey ID to delete")
    p_del.add_argument("--yes", action="store_true", help="Skip the interactive confirmation (required in non-interactive contexts)")
    p_del.add_argument("--no-open", action="store_true", help="Don't open the refreshed dashboard in the browser")
    p_del.set_defaults(func=cmd_delete_survey)

    p_delf = sub.add_parser(
        "delete-surveys", parents=[_db_parent()],
        help="Permanently delete surveys matching filters (title/location/status/campaign/fieldworker/ID range/date/score/opened). Backed up to JSON first.",
    )
    p_delf.add_argument("--ids", help="Comma-separated exact survey IDs, e.g. 10001,10002,10005")
    p_delf.add_argument("--id-min", type=int, help="Survey ID range start (inclusive)")
    p_delf.add_argument("--id-max", type=int, help="Survey ID range end (inclusive)")
    p_delf.add_argument("--title", help="Substring match (case-insensitive) on survey title")
    p_delf.add_argument("--location", help="Substring match on location name")
    p_delf.add_argument("--status", help="Substring match on survey status")
    p_delf.add_argument("--campaign", help="Substring match on campaign")
    p_delf.add_argument("--fieldworker", help="Substring match on fieldworker name or login")
    p_delf.add_argument("--date-from", help="YYYY-MM-DD, inclusive")
    p_delf.add_argument("--date-to", help="YYYY-MM-DD, inclusive")
    p_delf.add_argument("--score-min", type=float, help="Minimum score (inclusive)")
    p_delf.add_argument("--score-max", type=float, help="Maximum score (inclusive)")
    p_delf.add_argument("--opened", choices=["yes", "no"], help="Filter by opened status")
    p_delf.add_argument("--yes", action="store_true", help="Non-interactive confirmation, part 1 of 2 (also requires --expect-count)")
    p_delf.add_argument("--expect-count", type=int, default=None, help="Non-interactive confirmation, part 2 of 2: must equal the exact current match count")
    p_delf.add_argument("--no-open", action="store_true", help="Don't open the refreshed dashboard in the browser")
    p_delf.set_defaults(func=cmd_delete_surveys)

    p_clear = sub.add_parser(
        "clear-surveys", parents=[_db_parent()],
        help="Permanently delete ALL surveys (backed up to JSON first). Requires extra confirmation.",
    )
    p_clear.add_argument("--yes", action="store_true", help="Non-interactive confirmation, part 1 of 2 (also requires --expect-count)")
    p_clear.add_argument("--expect-count", type=int, default=None, help="Non-interactive confirmation, part 2 of 2: must equal the exact current row count")
    p_clear.add_argument("--no-open", action="store_true", help="Don't open the refreshed dashboard in the browser")
    p_clear.set_defaults(func=cmd_clear_surveys)

    p_serve = sub.add_parser(
        "serve", parents=[_db_parent()],
        help="Serve the dashboard locally (127.0.0.1) with working Delete / Clear-all buttons.",
    )
    p_serve.add_argument("--port", type=int, default=8765, help="Local port to listen on (default: 8765)")
    p_serve.add_argument("--no-open", action="store_true", help="Don't open the dashboard in the browser on start")
    p_serve.set_defaults(func=cmd_serve)

    p_setup = sub.add_parser("setup-db", parents=[_db_parent()], help="Create/verify the database for the current DB_BACKEND.")
    p_setup.set_defaults(func=cmd_setup_db)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
