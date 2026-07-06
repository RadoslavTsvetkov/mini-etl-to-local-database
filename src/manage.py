"""Single entry point for the Client Analytics Survey ETL pipeline's tools.

Usage:
    python manage.py run [--mode file|api] [--command-mode mock|live] [--db sqlite|sqlserver] [--max-records N]
    python manage.py view [all|surveys|runs|<survey_id>]
    python manage.py browse clients
    python manage.py browse surveys --client -995 [--limit N] [--unopened-only]
    python manage.py browse show <survey_id>
    python manage.py dashboard [output_path]
    python manage.py setup-db

Each subcommand is a thin wrapper around the corresponding standalone script
(etl.py, view_data.py, browse_surveys.py, generate_dashboard.py, db/setup_db.py)
-- those still work directly too. This just gives you one script to remember.
"""

import argparse
import sys

import browse_surveys
import etl
import generate_dashboard
import view_data
from db.setup_db import get_connection


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
    path = generate_dashboard.generate(args.output)
    print(f"Dashboard written to {path}")
    return 0


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
    p_dash.set_defaults(func=cmd_dashboard)

    p_setup = sub.add_parser("setup-db", parents=[_db_parent()], help="Create/verify the database for the current DB_BACKEND.")
    p_setup.set_defaults(func=cmd_setup_db)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
