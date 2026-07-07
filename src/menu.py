"""Interactive menu shown after `run.bat`'s default (no-argument) flow
finishes scraping surveys and opening the dashboard. Its whole purpose is
to answer "okay, now what?" for someone who hasn't read README.md and
doesn't know manage.py's subcommand names -- every option below is one of
those subcommands, just picked from a numbered list with a plain-English
description of when you'd want it, instead of typed out by hand.

Every action here just shells out to `manage.py <args>` -- the exact same
entry point `run.bat <command>` uses -- so behavior (confirmation prompts,
output, flags) is identical either way. See README.md for the full
command-line reference this menu is a friendlier front door to.
"""

import os
import subprocess
import sys

from colors import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
MANAGE_PY = os.path.join(SRC_DIR, "manage.py")


def _run(argv: list[str]) -> None:
    """Runs `manage.py <argv>` as a subprocess, inheriting this console's
    stdin/stdout/stderr -- so any confirmation prompt the subcommand itself
    asks (delete-survey's `yes`, clear-surveys' typed count + DELETE ALL,
    etc.) works exactly as if it had been typed on the command line."""
    subprocess.run([sys.executable, MANAGE_PY] + argv)


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _view() -> None:
    print(f"\n{DIM}Press Enter to see everything, or type: surveys | runs | a survey ID{RESET}")
    target = _ask("> ")
    _run(["view", target] if target else ["view"])


def _browse() -> None:
    print(f"\n{DIM}Live Shopmetrics lookup -- read-only, never touches your database.{RESET}")
    print("  1) List the clients/forms you can query")
    print("  2) List survey instances for a client")
    print("  3) Show one survey instance's full detail")
    choice = _ask("> ")
    if choice == "1":
        _run(["browse", "clients"])
    elif choice == "2":
        client = _ask("  Client/Form ID (see option 1 for the list): ")
        if client:
            _run(["browse", "surveys", "--client", client])
    elif choice == "3":
        survey_id = _ask("  Survey instance ID: ")
        if survey_id:
            _run(["browse", "show", survey_id])
    else:
        print(f"{YELLOW}Not one of the options above -- nothing done.{RESET}")


def _dashboard() -> None:
    _run(["dashboard"])


def _serve() -> None:
    print(f"\n{DIM}Starting the live dashboard server -- press Ctrl+C there to stop it")
    print(f"and come back to this menu.{RESET}\n")
    _run(["serve"])


def _run_pipeline() -> None:
    _run(["run", "--mode", "api"])


def _delete_one() -> None:
    survey_id = _ask("\nSurvey ID to delete: ")
    if survey_id:
        _run(["delete-survey", survey_id])


def _delete_filtered() -> None:
    print(f"\n{DIM}Leave any line blank to skip it. Every field you do fill in must all")
    print(f"match (AND) -- e.g. Location + Date narrows to that location in that")
    print(f"range only. Full filter list (score, campaign, fieldworker, opened")
    print(f"yes/no, exact ID lists): README.md section 2.2 or `manage.py")
    print(f"delete-surveys --help`.{RESET}")
    title = _ask("  Title contains: ")
    location = _ask("  Location contains: ")
    status = _ask("  Status contains: ")
    id_min = _ask("  Survey ID from: ")
    id_max = _ask("  Survey ID to: ")
    date_from = _ask("  Date from (YYYY-MM-DD): ")
    date_to = _ask("  Date to (YYYY-MM-DD): ")

    argv = ["delete-surveys"]
    if title:
        argv += ["--title", title]
    if location:
        argv += ["--location", location]
    if status:
        argv += ["--status", status]
    if id_min:
        argv += ["--id-min", id_min]
    if id_max:
        argv += ["--id-max", id_max]
    if date_from:
        argv += ["--date-from", date_from]
    if date_to:
        argv += ["--date-to", date_to]

    if len(argv) == 1:
        print(f"{YELLOW}No filters entered -- nothing to do. (Option 8 deletes everything,")
        print(f"on purpose, if that's actually what you want.){RESET}")
        return
    _run(argv)


def _clear_all() -> None:
    _run(["clear-surveys"])


# (key, one-line label shown in the menu, section header it's grouped
# under, the function to call)
_MENU = [
    ("1", "View the collected surveys & run history (in this terminal)", "EXPLORE YOUR DATA", _view),
    ("2", "Look around live Shopmetrics data (read-only lookup)", "EXPLORE YOUR DATA", _browse),
    ("3", "Refresh the dashboard (regenerate the HTML report)", "EXPLORE YOUR DATA", _dashboard),
    ("4", "Open the dashboard with LIVE Delete buttons (serve mode)", "EXPLORE YOUR DATA", _serve),
    ("5", "Run the pipeline again (scrape newest surveys from Shopmetrics)", "GET MORE DATA", _run_pipeline),
    ("6", "Delete ONE survey, by its ID", "REMOVE DATA — see README.md §2.2 first", _delete_one),
    ("7", "Delete surveys matching a filter (title / location / date / ID range / ...)", "REMOVE DATA — see README.md §2.2 first", _delete_filtered),
    ("8", "Delete ALL surveys — drastic, asks for extra confirmation", "REMOVE DATA — see README.md §2.2 first", _clear_all),
]


def _print_menu() -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN} What would you like to do next?{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{DIM}Full command-line details for everything below are in README.md.{RESET}\n")

    last_section = None
    for key, label, section, _ in _MENU:
        if section != last_section:
            print(f"  {BOLD}{section}{RESET}")
            last_section = section
        print(f"    {BOLD}{key}{RESET})  {label}")
    print(f"\n    {BOLD}0{RESET})  Exit")
    print(f"\n{DIM}(Type a number, or \"menu\" to see this list again.){RESET}")


def main() -> int:
    _print_menu()
    while True:
        choice = _ask(f"\n{CYAN}> {RESET}").lower()
        if choice in ("0", "exit", "quit", "q"):
            print("Bye!")
            return 0
        if choice in ("", "menu", "help", "?"):
            _print_menu()
            continue

        match = next((m for m in _MENU if m[0] == choice), None)
        if match is None:
            print(f"{RED}Not a number from the list above -- type one of 1-8, \"menu\", or 0 to exit.{RESET}")
            continue

        match[3]()
        print(f"\n{GREEN}Done.{RESET} {DIM}Type another number, \"menu\" to see the list again, or 0 to exit.{RESET}")


if __name__ == "__main__":
    sys.exit(main())
