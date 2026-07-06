"""Browse real Shopmetrics survey data directly, without running the ETL
pipeline or touching the local database. Always talks to the live
Shopmetrics Query API (read-only) -- requires real credentials in .env
(see .env.example), regardless of EXTRACTION_MODE/COMMAND_MODE.

Usage:
    python browse_surveys.py clients
    python browse_surveys.py surveys --client -995
    python browse_surveys.py surveys --client -995 --limit 50 --unopened-only
    python browse_surveys.py show 10656
"""

import argparse
import sys

import api_client
import config


def cmd_clients(_args) -> None:
    rows = api_client.list_client_or_form_ids()
    level1 = [r for r in rows if r.get("HierarchyLevel") == 1]
    print(f"{'ID':<10} Name")
    print("-" * 50)
    for r in level1:
        print(f"{str(r['ID']):<10} {r['Name']}")
    print(f"\n{len(level1)} client/group entries. Pass one of these IDs as --client to 'surveys'.")


def cmd_surveys(args) -> None:
    rows = api_client.list_surveys(args.client, args.limit, unopened_only=args.unopened_only)
    if not rows:
        print("No survey instances found for that client/filter.")
        return
    print(f"{'Survey ID':<10} {'Title':<35} {'Location':<20} {'Date':<12} {'Score':<8} Status")
    print("-" * 100)
    for r in rows:
        print(
            f"{str(r.get('InstanceID')):<10} {str(r.get('Title'))[:35]:<35} "
            f"{str(r.get('Location Name'))[:20]:<20} {str(r.get('Date')):<12} "
            f"{str(r.get('ScorePctXX.XX')):<8} {r.get('SurveyStatusName')}"
        )
    print(f"\n{len(rows)} survey instance(s) shown (limit={args.limit}). Use 'show <id>' for full Q&A.")


def cmd_show(args) -> None:
    responses = api_client.get_survey_responses([args.survey_id])
    rows = responses.get(args.survey_id, [])
    if not rows:
        print(f"No response data found for survey {args.survey_id} (check the ID and that this account can access it).")
        return
    print(f"=== Survey {args.survey_id}: {len(rows)} response row(s) ===")
    for r in rows:
        print(f"- Q{r['question_id']}: {r['answer_text']}  |  {r['comment'] or ''}")


def main(argv: list[str] = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Browse real Shopmetrics survey data (read-only).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("clients", help="List ClientOrFormIDs values this API user can query.")

    p_surveys = sub.add_parser("surveys", help="List survey instances for a client.")
    p_surveys.add_argument(
        "--client", default=config.SHOPMETRICS_CLIENT_OR_FORM_IDS,
        help="ClientOrFormIDs value (default: from .env / config)",
    )
    p_surveys.add_argument("--limit", type=int, default=25, help="Max rows to show (default 25)")
    p_surveys.add_argument(
        "--unopened-only", action="store_true",
        help="Only show surveys not yet opened/viewed by this API user",
    )

    p_show = sub.add_parser("show", help="Show full Q&A detail for one survey instance.")
    p_show.add_argument("survey_id")

    args = parser.parse_args(argv)
    try:
        {"clients": cmd_clients, "surveys": cmd_surveys, "show": cmd_show}[args.command](args)
    except api_client.ShopmetricsAPIError as e:
        print(f"Shopmetrics API error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
