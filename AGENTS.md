# AGENTS.md — guide for AI coding agents working in this repo

This file orients an AI agent (or a human) picking up this codebase cold —
no memory of prior sessions, just the files on disk. Read this first; it
tells you where the deeper documentation lives and, more importantly, the
non-obvious conventions and traps that aren't visible from the code alone.

## What this project is

A small, self-contained Python ETL pipeline for **Shopmetrics Client
Analytics surveys**: it extracts survey instances (from a local sample file
or the real Shopmetrics Query API v2), loads them into a local database
(SQLite or SQL Server), marks them "opened" via the Shopmetrics Command API,
logs every run, and generates/serves an HTML dashboard — including the
ability to delete data through that dashboard or the command line. Windows
is the primary target (`.bat` launchers, `os.startfile`), but every Python
module is written to run cross-platform via `python src/manage.py`.

**Zero third-party dependencies** for the default SQLite path — stdlib
only (`sqlite3`, `urllib`, `json`, `http.server`, `argparse`, `logging`).
`pyodbc` is the *only* third-party package in the whole project, and it's
optional (only needed for `DB_BACKEND=sqlserver`). Don't add a dependency
without a very good reason — this constraint is deliberate and has been
maintained through several rounds of feature additions (a local delete/edit
web UI included).

## Quickstart — zero to scraping real surveys on a brand-new machine

This is the exact, mechanical procedure. Follow it in order; every step
says what should happen so you can tell immediately if something's wrong.

**Prerequisites:** Windows (primary target; see "cross-platform" below for
Mac/Linux), Python 3.10 or newer on `PATH`. Nothing else — no database
server, no Node, no build tools.

**Step 1 — Install.** From the repo root, double-click `install.bat` (or
run it from a terminal: `.\install.bat`). This creates `.venv\`, installs
dependencies (none for SQLite; `pyodbc` for the optional SQL Server
backend), and copies `.env.example` to `.env` if `.env` doesn't already
exist. It ends with "Install complete!" and a pause. If it instead says
Python wasn't found or is too old, install Python 3.10+ from
python.org (check "Add python.exe to PATH") and re-run.

**Step 2 — Get Shopmetrics API credentials.** You need exactly two pieces
of information from whoever administers the target Shopmetrics site:
a **Client ID** and a **Client Secret**. These are created in the
Shopmetrics web UI at: **Administration → Tools and Settings → Site
Settings → Other → API v2 Authorization – Client Credentials** (an admin
user creates a "Create New" entry there and can auto-generate the secret).
Nothing else is required — the site URL (`https://training212.shopmetrics.com`)
and the client/account scope (`ClientOrFormIDs=-995`) are already the
checked-in defaults in `config/config.json`, matching the account this
project has been built and tested against ("Delight Coffee (CX Analytics
Demo)"). If you're pointing this at a *different* Shopmetrics site or
account, change `SHOPMETRICS_BASE_URL`/`SHOPMETRICS_CLIENT_OR_FORM_IDS` in
`config/config.json` (or `.env` for a local-only override) — see
"Configuration system" below.

**Step 3 — Run it.** Double-click `run.bat` (or from a terminal:
`.\run.bat`, or cross-platform `python src/manage.py run`). Two outcomes:

- **First time, credentials not yet saved:** the console prints "Shopmetrics
  API credentials are not set up yet" and prompts:
  ```
    Shopmetrics Client ID:
    Shopmetrics Client Secret:
  ```
  Paste in the two values from Step 2 (typing is fine too — paste just
  saves keystrokes). It then prints "Credentials saved to .env" and
  "Verifying credentials against the API... OK." and the run proceeds
  immediately — you do **not** need to re-run the command.
- **Already saved (this or a later run):** it goes straight to "Verifying
  credentials against the API... OK." with no prompt.

Either way, what happens next is the actual scrape:
```
=== ETL run starting (EXTRACTION_MODE=api, COMMAND_MODE=mock) ===
Extracted 1804 survey record(s)
Loaded 1804 new survey(s), skipped 0 duplicate(s)
Marked survey <id> as opened (request_id=MOCK-REQUEST-<id>)   [one line per survey]
=== ETL run finished: status=success extracted=1804 loaded=1804 duplicates=0 marked_opened=1804 errors=0 ===
Dashboard updated (opened in your browser): C:\...\reports\dashboard1.html
```
**1804 is the current live count** of unopened survey instances under
`ClientOrFormIDs=-995` on the configured account — this number will drift
over time as new surveys are submitted and/or marked opened elsewhere, and
is themselves a live fact from the API, not a constant to hardcode
anywhere. On a second run, "Extracted" stays the same or grows, but
"Loaded" drops to near-zero and "duplicates" rises to match, since
already-loaded surveys are skipped (see "Configuration system" for exactly
why re-running doesn't re-download from scratch).

Bare `run.bat` then drops you into a numbered menu (§ "The interactive
menu" below) — type `0` or `exit` to close it.

**If you only see "Extracted 3 survey record(s)" instead of ~1800+:** that
3 is the file-mode sample-data count (`data/sample_surveys.json` has
exactly 3 records), meaning `EXTRACTION_MODE` resolved to `file`, not
`api`, for this run — go straight to "Troubleshooting: why am I only
getting 3 surveys" further down; don't assume the API integration is
broken, because the far more likely cause is a stale override sitting in
front of the (already-`api`) default.

**Cross-platform (no `.bat` files):** every step above has a direct
equivalent — `python -m venv .venv` + `pip install -r requirements.txt`
instead of `install.bat`; `python src/manage.py run` (from the activated
venv) instead of `run.bat`. The credentials prompt, the extraction count,
and everything else behaves identically; only the `.bat` convenience
wrappers and `os.startfile()`-based dashboard auto-open are Windows-only
(the dashboard still gets *written*, just opened via `webbrowser.open()`
on other platforms — see `generate_dashboard.open_in_browser()`).

## Read these first, in this order

1. **`README.md`** — user-facing usage guide. If you're asked to change
   user-visible behavior, this is the doc that has to stay in sync.
2. **`SPECIFICATION.md`** — the technical design doc and source of truth for
   *why* things are built the way they are, including how every field maps
   to the real Shopmetrics API, and a section-by-section history of
   corrections made after testing against the real API (§10, §11 — read
   these before assuming a "cleaner" implementation is correct; several
   things here look like they could be simplified but are deliberately
   shaped around real API quirks that were discovered the hard way).
3. **`schema.md`** — the two-table database schema (`surveys`, `etl_runs`),
   plain-English column-by-column.
4. **`TASK_001.md`** — the original one-paragraph task brief this project
   started from. Useful for understanding the "definition of done" baseline
   (§9 of SPECIFICATION.md maps it explicitly), but the project has grown
   well past it since.
5. **`_KNOWLEDGEBASE/023-APIs/`** — the actual Shopmetrics API documentation
   (60+ articles) this whole integration is built from. If you're touching
   `api_client.py` or anything that talks to the real API, the answer to
   "is this right?" is almost always in here, not in general REST/OAuth
   knowledge — Shopmetrics has several non-obvious conventions (see
   "API quirks" below).

**Whenever you change behavior that's documented in README.md or
SPECIFICATION.md, update those files in the same change.** They have
drifted out of sync with the code before in this project's history and it
was confusing; keeping them current is treated as part of the task, not an
optional follow-up.

## Repository layout

```
specification/                        (repo root)
├── install.bat / run.bat             # Windows entry points -- see below
├── README.md / SPECIFICATION.md / schema.md / TASK_001.md
├── requirements.txt                  # empty (SQLite needs nothing)
├── requirements-sqlserver.txt        # pyodbc only
├── .env.example / .env               # secrets + local overrides (.env gitignored)
├── config/config.json                # checked-in non-secret settings
├── _KNOWLEDGEBASE/023-APIs/          # source-of-truth Shopmetrics API docs
├── src/
│   ├── manage.py                     # single CLI entry point (all subcommands)
│   ├── menu.py                       # interactive menu shown after run.bat's default flow
│   ├── etl.py                        # pipeline orchestration + credential prompt/verify
│   ├── extract.py                    # file-mode / API-mode extraction
│   ├── load.py                       # insert/delete/filter-query DB helpers (dual-backend)
│   ├── api_client.py                 # OAuth2 + Query API + Command API client
│   ├── backup.py                     # JSON backups written before any delete
│   ├── server.py                     # local-only (127.0.0.1) web server for live dashboard actions
│   ├── generate_dashboard.py         # builds the self-contained HTML dashboard
│   ├── browse_surveys.py             # read-only live-API explorer CLI
│   ├── view_data.py                  # colorized terminal view of the local DB
│   ├── logger.py / colors.py / config.py
│   └── db/
│       ├── schema.sql / schema_sqlserver.sql
│       └── setup_db.py               # creates/migrates whichever backend is selected
├── data/                              # sample_surveys.json (checked in), etl.db, backups/ (gitignored)
├── logs/etl.log                       # gitignored
└── reports/dashboard<N>.html          # gitignored, numbered, never overwritten
```

## Running things

Everything goes through **`src/manage.py`** as the single CLI entry point;
`run.bat <args>` on Windows just forwards to it (`python src/manage.py
<args>` works identically on any OS from an activated venv).

| Command | What it does |
|---|---|
| `run.bat` *(no args)* | The primary double-click flow: `run --mode api --no-open`, opens the new dashboard via `start`, then launches `menu.py`. Only this exact invocation shows the menu. |
| `manage.py run [--mode file\|api] [--command-mode mock\|live] [--db sqlite\|sqlserver] [--max-records N] [--no-open]` | Full pipeline: extract → load (dedup) → mark opened → log → regenerate dashboard. |
| `manage.py view [all\|surveys\|runs\|<survey_id>]` | Colorized terminal view of the local DB (read-only). |
| `manage.py browse clients` / `browse surveys --client <id>` / `browse show <id>` | Read-only live Shopmetrics lookup — **never touches the local DB**, always hits the real API regardless of `EXTRACTION_MODE`. |
| `manage.py dashboard [output_path] [--no-open]` | Regenerate the HTML dashboard without running the pipeline. |
| `manage.py delete-survey <id> [--yes]` | Delete one survey (backs up first). |
| `manage.py delete-surveys [--title/--location/--status/--campaign/--fieldworker/--id-min/--id-max/--ids/--date-from/--date-to/--score-min/--score-max/--opened] [--yes --expect-count N]` | Bulk delete by filter (AND-combined). **Refuses with zero filters.** |
| `manage.py clear-surveys [--yes --expect-count N]` | Delete every survey. Heaviest confirmation in the project (see below). |
| `manage.py serve [--port 8765] [--no-open]` | Serves the dashboard over `http://127.0.0.1` with *working* Delete/Delete-by-filter/Clear-all buttons (a static dashboard file can't do this — no server behind it). |
| `manage.py setup-db` | Create/verify the DB for the current backend. |

**There is no automated test suite.** Verification in this project has
always meant: run the actual command, inspect real output/DB state, and —
for anything destructive — do it against a **disposable copy** of the
database (see "Testing destructive changes" below). If you add a test
suite, that's a welcome addition, but don't assume one exists.

## Configuration system (`src/config.py`)

Four layers, highest precedence first: **real env vars / CLI flags** →
**`.env`** (gitignored secrets + local overrides) → **`config/config.json`**
(checked-in defaults) → **hardcoded fallback in `config.py`**. Every
`config.json` key name is identical to its env var name (`os.environ.
setdefault(key, str(value))`), so there's no name-translation to keep track
of. `config.save_env_values()` rewrites specific keys in `.env` in place
without disturbing the rest of the file — used by the interactive
credentials prompt (`etl.ensure_api_credentials`), which fires whenever a
run needs the live API and `.env` is missing credentials *or the API
rejects them* (HTTP 400 `invalid_client` re-triggers the same prompt).

**Useful trick for testing without touching the real database:** set the
`DB_PATH` environment variable before invoking anything — it overrides
`config.json`'s value and nothing else needs to change. `backup.py`'s
`BACKUPS_DIR`, however, is **not** parameterized by `DB_PATH` — it always
writes to the real project's `data/backups/` regardless of which database
was actually read. Keep this in mind if you're testing delete operations
against a copy: the backup JSON still lands in the real repo.

**Trap: changing a `config/config.json` default doesn't change behavior if
`.env` has a stale explicit override for that same key.** Since `.env` is
loaded *before* `config.json` (both via `setdefault`), a leftover line like
`EXTRACTION_MODE=file` in a real `.env` — e.g. from earlier local testing —
silently keeps winning even after `config.json`'s own default is edited to
`api`. This bit exactly this project once: `EXTRACTION_MODE` was changed to
default to `api` in `config.json`, but the repo's own working `.env` still
had an explicit `EXTRACTION_MODE=file` line from earlier sessions, so the
real project kept running in file mode until that stale line was removed.
If you change a config default and it doesn't seem to take effect, check
`.env` for a stale override of the same key before assuming the code is
broken.

### Troubleshooting: "I'm only getting 3 surveys, not ~1800"

This is always a config-resolution question, never an API/network problem
(if the API were unreachable or credentials were rejected, the run would
say so explicitly and stop before extracting anything — see
`etl.ensure_api_credentials`). **3** is the exact record count of
`data/sample_surveys.json` (file mode); the real number (currently **1804**,
but this drifts — it's a live count on the Shopmetrics side, not a
constant) only comes back when `EXTRACTION_MODE` resolves to `api`.

Diagnose by checking where `EXTRACTION_MODE` is actually coming from, in
precedence order (first one found wins):

1. **A real shell/session environment variable.** Check it directly:
   PowerShell: `$env:EXTRACTION_MODE`; cmd: `echo %EXTRACTION_MODE%`; also
   check persistent Windows env vars, which survive across sessions and are
   easy to forget about: `[Environment]::GetEnvironmentVariable("EXTRACTION_MODE", "User")`
   and the same with `"Machine"`. If any of these print `file`, that's your
   answer — remove it (`[Environment]::SetEnvironmentVariable("EXTRACTION_MODE", $null, "User")`
   for a persistent one, or just don't set it in the current shell).
2. **An explicit `--mode file` CLI flag** on the command actually run —
   check the exact command line used, including anything a wrapper script
   or menu option passed. (`run.bat run --mode file`, `manage.py run
   --mode file`, and the menu's option 5 all call the pipeline explicitly
   without `--mode`, i.e. they don't force file mode — only an intentional
   `--mode file` does.)
3. **`.env`** — open it and look for an `EXTRACTION_MODE=` line. If present
   and set to `file`, that's almost certainly it (this is the exact trap
   documented above — a stale line surviving from earlier testing).
4. **`config/config.json`** — check the `"EXTRACTION_MODE"` value. Should
   be `"api"`. If it's been hand-edited to `"file"`, that's a real,
   deliberate change to the checked-in default, not a bug.
5. **The hardcoded fallback** in `config.py` (`EXTRACTION_MODE =
   os.environ.get("EXTRACTION_MODE", "api")`) — only reached if
   `config/config.json` is missing entirely. Should say `"api"` in the
   source; if someone changed the string literal here back to `"file"`,
   that's the bug.

The fastest single check that cuts through all five layers at once —
run this from the repo root and read off exactly what the program itself
will use, no guessing:
```
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import config; print(config.EXTRACTION_MODE)"
```
It should print `api`. If it prints `file`, work down the list above in
order (1 through 5) until you find the layer that's setting it, starting
with the environment-variable checks since those are the easiest to forget
about and the highest precedence.

## Database backends — portability rules

Both `sqlite3` and `pyodbc` (SQL Server) are driven with **`?`-style
placeholders** throughout — this is deliberate so the same parameterized
SQL string mostly works against either backend without a dialect branch.
A few things to know if you touch `load.py` or `db/`:

- `CAST(col AS INTEGER)` works on **both** backends — SQL Server accepts
  `INTEGER` as an ISO synonym for `INT`. This is how `survey_id` (stored as
  `TEXT`) gets numeric range comparisons (`--id-min`/`--id-max`) without a
  dialect split.
- Row access must go through `cursor.description` + `zip()` to build dicts
  (`fetch_survey`, `fetch_all_surveys`, `fetch_matching_surveys`,
  `preview_matching_surveys` in `load.py`) — **not** `sqlite3.Row`, since
  that API doesn't exist on `pyodbc` rows. This pattern is already
  established; copy it for any new fetch helper rather than inventing a
  new one.
- Date-range filtering avoids `SUBSTR`/`SUBSTRING` (spelled differently in
  each dialect) by comparing the full ISO-8601 string lexicographically:
  `submitted_at >= 'YYYY-MM-DD'` (a shorter prefix sorts before any longer
  string that starts with it) and `submitted_at < (date_to + 1 day)` for an
  inclusive upper bound. See `load.build_survey_filter()`.
- `INSERT OR IGNORE` (SQLite) vs. `IF NOT EXISTS ... INSERT` (SQL Server) is
  the one place that *does* need a real dialect branch — see
  `load._insert_survey_sqlite` / `_insert_survey_sqlserver`.
- New columns go in **both** `schema.sql` and `schema_sqlserver.sql`, plus
  the `_NEW_SURVEY_COLUMNS` migration list in `db/setup_db.py` so existing
  databases get an `ALTER TABLE ADD COLUMN` automatically. Don't forget any
  one of these three — a column present on fresh installs but missing on
  upgraded databases is a real failure mode this project explicitly guards
  against.

## Deleting data — three tiers, by design

The project deliberately has **three separate commands**, not one
parameterized one, because the "how sure are you?" weight should be visibly
different:

1. **`delete-survey <id>`** — one typed `yes`.
2. **`delete-surveys [filters]`** — shows a match count + 10-row preview,
   then requires typing the exact count back (interactive) or
   `--yes` + `--expect-count N` matching the live count (scripted).
   **Refuses to run with zero filters** — that's what tier 3 is for,
   spelled differently on purpose so muscle memory can't confuse them.
3. **`clear-surveys`** — same count-typing as tier 2, *plus* typing the
   literal phrase `DELETE ALL`. The most heavily gated action in the repo.

Every tier backs up whatever it's about to remove to a timestamped JSON
file in `data/backups/` (`backup.py`) **before** deleting, unconditionally.
There's no restore command — re-importing is a manual job, the backup is
insurance, not an undo button. All three also call
`manage._refresh_dashboard_after_change()` afterward, which logs an audit
line (`logger.warning` for the two bulk tiers, `logger.info` for the single
delete) and regenerates the dashboard.

**None of this touches the Shopmetrics side.** Deleting locally has no
API call behind it — if the survey is still unopened on Shopmetrics, the
next `--mode api` extraction just re-downloads it. This is a documented,
intentional property, not a gap.

## The dashboard (`generate_dashboard.py`)

A single self-contained HTML file — inline CSS (`_STYLE`), inline SVG
charts (hand-built paths, no charting library), and inline vanilla JS
(`_SCRIPT`) — no CDN, no build step. Reports are numbered
(`reports/dashboard<N>.html`, `next_output_path()`/`latest_report_filename()`
scan the directory for the highest existing number) and never overwritten.

Two rendering modes controlled by one parameter:
`generate_dashboard.generate(server_token=None)`. When `server_token` is
set (only `manage.py serve` / `src/server.py` does this), the emitted page
embeds `window.__DASHBOARD_LIVE__ = true` plus the token, and its own JS
un-hides the `.live-only` elements (Delete button in the survey modal,
"Delete by filter…" and "Clear ALL surveys…" in the toolbar) — otherwise
those stay hidden behind a `.static-only` note pointing at `serve`. A
double-clicked/static dashboard file has no server to call, so those
buttons genuinely cannot work there — this isn't a bug to "fix" by trying
to make static HTML mutate a database.

If you add a chart or a UI element, match the existing conventions already
in this file: categorical breakdowns get one quiet hue per bar (not a
rainbow), the score distribution uses an ordinal light→dark ramp, bars have
a 2px surface gap and rounded data-ends, every value hover shows an exact
count/percentage via the shared `#tip` tooltip element, and colors are
CSS custom properties (`--series-1`, `--ord-1..5`, `--good`/`--warn`/`--bad`,
etc.) defined once for light mode and again inside `@media
(prefers-color-scheme: dark)` — never a hardcoded hex outside that block.

## The local server (`manage.py serve` / `src/server.py`)

Stdlib `http.server.ThreadingHTTPServer` only — no Flask/FastAPI. Bound to
**`127.0.0.1` only**, never `0.0.0.0`. Serves static files from `reports/`
(basename-only matching + `realpath()` containment check against path
traversal) and four `POST /api/*` JSON endpoints (`delete-survey`,
`clear-surveys`, `preview-filtered`, `delete-filtered`) dispatched via a
`ROUTES = {path: handler}` dict on `DashboardHandler`.

**Every** `/api/*` call — including the read-only preview endpoint — must
carry a `X-Dashboard-Token` header matching a `secrets.token_hex(16)`
generated fresh each time `serve` starts and embedded in the page. This
exists because same-origin policy stops a malicious page in another tab
from *reading* a response from `127.0.0.1:<port>`, but does **not** stop it
from *sending* a request there (classic local-CSRF shape) — the token is
the mitigation, and it works specifically because SOP also stops that other
page from reading *this* page's DOM to steal the token. If you add a new
mutating endpoint, it must go through the same token check; don't skip it
for a "read-only" one either — the uniform rule ("every `/api/*` call needs
it, no exceptions") is the point.

Mutating endpoints re-validate `expected_count` against the database's
*actual* current count server-side before deleting (never trust the
browser's number) — same "stale count" protection the CLI's
`--expect-count` has. Reuses the exact same `load.py`/`backup.py` functions
the CLI commands use; there is no separate deletion logic to keep in sync.

**Windows trap, already fixed — don't revert it:** the server is a
`_DashboardServer(ThreadingHTTPServer)` subclass with `allow_reuse_address =
False`, not a bare `ThreadingHTTPServer`. The stdlib default
(`allow_reuse_address = True`, i.e. `SO_REUSEADDR`) lets a *second* `serve`
process silently bind the *same already-occupied port* on Windows — POSIX
rejects this, Windows doesn't — with no error on either side and undefined
routing of incoming requests between the two processes. This was reproduced
directly (two `serve` processes both "successfully" listening on the same
port) before the fix. If you ever refactor this class, keep
`allow_reuse_address = False`.

## The interactive menu (`src/menu.py`)

Shown only after `run.bat`'s bare double-click flow. It shells out to
`manage.py <args>` via `subprocess.run()` with **no stdio redirection** —
this is deliberate, so any confirmation prompt a subcommand asks (typed
`yes`, typed count, `DELETE ALL`) behaves identically to typing the command
directly, including its existing `sys.stdin.isatty()` refusal in a
non-interactive context. Don't refactor this to call the `cmd_*` functions
in-process — the subprocess boundary is what keeps the menu's behavior
provably identical to the documented CLI.

`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` is set at
import time (same pattern in `view_data.py`) — without it, Python can pick
a non-UTF-8 default encoding for stdout whenever it isn't attached to a
real console (piping, some redirected contexts), which corrupts the
em-dashes and section markers used throughout this project's terminal
output. If you add new print-heavy scripts, carry this line over.

## Credentials & secrets

`SHOPMETRICS_CLIENT_ID`/`SHOPMETRICS_CLIENT_SECRET` live only in `.env`
(gitignored) — never in `config/config.json`, code, commit messages, or
docs. `etl.ensure_api_credentials()` is the single gate every live-API run
passes through: verifies with a real token request every time (cheap — the
token is needed for extraction anyway), prompts interactively if missing or
rejected, and refuses cleanly (exit 1, explanatory message) when it can't
prompt. If a secret is ever actually exposed, the fix is to regenerate it
in Shopmetrics admin (Administration → Tools and Settings → Site Settings →
Other → API v2 Authorization – Client Credentials) — deleting the local
copy doesn't revoke the old value.

## Exactly how a scrape happens — the literal request/response mechanics

Everything below is what `api_client.py` actually does, spelled out
mechanically (endpoint, payload shape, real example values from this
account) so it can be understood or reconstructed without reading the
module line by line. Every live-mode run (`EXTRACTION_MODE=api`) makes
exactly **3 real network round-trips total**, no matter how many surveys
come back — 1 auth + 2 query calls:

**1. Authenticate — OAuth2 Client Credentials Grant**
```
POST https://training212.shopmetrics.com/oauth/connect/token
Content-Type: application/x-www-form-urlencoded
Body: client_id=<SHOPMETRICS_CLIENT_ID>&client_secret=<SHOPMETRICS_CLIENT_SECRET>&grant_type=client_credentials
```
Response: `{"access_token": "<opaque token, ~900 chars>", "expires_in": 1800, ...}`.
`api_client._token_cache` holds this in memory (module-level dict) and
reuses it for the rest of the process's lifetime until 30 seconds before
`expires_in` elapses. This request happens exactly **once** per run —
`etl.ensure_api_credentials()` triggers it first, as a verification step
before extraction even starts (so a bad credential is caught and reported
immediately, not mid-run); the two query calls below (steps 2 and 3) each
also call `api_client.get_access_token()`, but that function checks the
cache first and returns the already-fetched token instantly — neither of
them makes a second token request.

**2. List unopened survey instances**
```
POST https://training212.shopmetrics.com/api/v2/execute
Content-Type: application/x-www-form-urlencoded      <-- NOT application/json, see quirk below
Authorization: Bearer <token>
Body (form field "post", value is this JSON *string*):
{
  "action": "exec",
  "dataset": {"datasetname": "/Apps/SM/APIv2/Query/ClientAnalytics/ClientAnalytics"},
  "parameters": [
    {"name": "QuerySpecification", "value": "[InstanceID][Title][Loc ID][Location Name][Date][ScorePctXX.XX][SurveyStatusName][AttachmentsCount][Login][Shopper Name][WorkflowStepID][Campaign][IsSurveyInstanceViewedBySecurityUser][WHERE:IsSurveyInstanceViewedBySecurityUser|0][ORDERBY:Date|DESC]"},
    {"name": "ClientOrFormIDs", "value": "-995"}
  ]
}
```
Response shape: `{"dataset": {"data": [[ {row1 fields...}, {row2 fields...}, ... ]]}}`
— note the double nesting, `data` is a list containing one list of row
objects (`api_client._execute_dataset` unwraps this to `response["dataset"]["data"][0]`).
Confirmed live: every returned row has `IsSurveyInstanceViewedBySecurityUser
== 0` — the `[WHERE:...]` clause is a genuine server-side filter, not just
decorative. Result is capped client-side to `SHOPMETRICS_MAX_RECORDS_PER_RUN`
(default `5000`) via a plain Python slice (`rows[:limit]`) — the API itself
returns everything matching the filter in one shot; there is no
server-side pagination in this call.

**3. Fetch each returned survey's responses**
```
POST https://training212.shopmetrics.com/api/v2/execute   (same endpoint, same transport)
Body (form field "post"):
{
  "action": "exec",
  "dataset": {"datasetname": "/Apps/SM/APIv2/Query/ClientAnalytics/ClientAnalytics"},
  "parameters": [
    {"name": "QuerySpecification", "value": "[InstanceID][QuestionID][ProtoAnswerText][Question Comment]"},
    {"name": "SurveyInstanceIDs", "value": "10001,10004,10008,..."}   <-- CSV of every InstanceID from step 2
  ]
}
```
Rows come back ungrouped (one row per question per survey); `api_client.
get_survey_responses()` groups them into
`{instance_id: [{"question_id", "answer_text", "comment"}, ...]}` by
`InstanceID`. **Every survey instance seen has returned every answer
option for every question**, not only the one the shopper picked (e.g. a
34-answer-row survey with ~a dozen questions) — this is a confirmed,
unresolved upstream data-shape gap, not a bug in this codebase (SPECIFICATION §10.4).

**That's the whole live extraction — exactly 2 `/api/v2/execute` calls per
run** (steps 2 and 3), regardless of whether 3 surveys or 3,000 come back,
plus the one cached token request (step 1). This is what
keeps a full-backlog pull (`SHOPMETRICS_MAX_RECORDS_PER_RUN=5000`, larger
than the account's current backlog) within the KB's fair-use guidance
against high-volume *consecutive* calls — volume of data isn't the same as
volume of *requests*, and this design only ever issues 2 requests no
matter which.

**Mark-opened (separate step, after load, only when `COMMAND_MODE=live`)**
uses the *same* `/api/v2/execute` transport but a **command** dataset
(`/Apps/SM/APIv2/Command/SurveyInstances/BulkProcessing_SetReadStatus`,
parameters `SurveyInstancesIDsCSV` + `ReadStatus=1`) rather than a query —
this flips `IsSurveyInstanceViewedBySecurityUser` back to `1`, which is
what would make step 2's `[WHERE:...]` filter exclude it on the next run.
**Currently returns HTTP 500 on this account** (confirmed, SPECIFICATION
§10.3) — this is why `COMMAND_MODE` defaults to `mock`
(`api_client.mark_survey_opened_mock`, no network call, always "succeeds")
and why re-running the pipeline keeps re-fetching the same surveys (they
never actually get marked opened on the Shopmetrics side) — `load.py`'s own
`survey_id` dedup is what prevents them from being re-inserted locally,
which is a completely separate mechanism from the "opened" flag on the
Shopmetrics side.

## API quirks worth knowing before touching `api_client.py`

These were discovered by testing against the real account, not documented
obviously in the KB — see SPECIFICATION.md §10 for the full story:

- `POST /api/v2/execute` looks like a JSON endpoint but actually wants a
  **form-encoded** body with a single `post` field whose value is a JSON
  *string* — a real JSON request body gets rejected outright.
- The site's WAF blocks Python's default `urllib` User-Agent (HTTP 403 /
  Cloudflare 1010) — `api_client.py` always sends a browser-style one.
- `BulkProcessing_SetReadStatus` (the documented "mark opened" command) is
  called through the *dataset* convention (same `/api/v2/execute` endpoint
  as queries), not the dedicated REST `/api/v2/command/<Name>` path some
  other commands use — don't assume one calling convention applies
  project-wide.
- `COMMAND_MODE=live` (the real mark-opened call) currently returns
  **HTTP 500** on this account — treat it as non-functional; `mock` is the
  default and what real runs should use until Shopmetrics confirms a
  replacement dataset name.
- The responses query returns **every possible answer option** per
  question, not just the one selected (confirmed, unresolved upstream gap —
  SPECIFICATION §10.4). Don't build a feature that assumes `responses_json`
  contains only the chosen answer.

## Testing destructive changes — do this, not that

This project has no automated tests, and several commands permanently
delete data. The established, safe pattern (used throughout this project's
own development) is:

```powershell
Copy-Item data\etl.db <scratchdir>\test_copy.db
$env:DB_PATH = "<scratchdir>\test_copy.db"
$env:OPEN_DASHBOARD = "false"          # avoid popping browser windows during testing
# ... run whatever destructive command you're verifying ...
Remove-Item Env:DB_PATH, Env:OPEN_DASHBOARD
```

Never point a destructive command at the real `data/etl.db` to "just check
it works." Verify row counts before/after against the **copy**, and remember
`backup.py` writes to the real repo's `data/backups/` regardless of
`DB_PATH` (see above) — clean those up if they were purely for testing, but
check timestamps first: a backup file might be from the *user's own* real
usage between your sessions, not something you created. When in doubt,
correlate its timestamp against real database row-count changes before
deleting it.

**Same trap applies to `reports/`:** `generate_dashboard.REPORTS_DIR` is
also not parameterized by `DB_PATH` — any command that regenerates the
dashboard (`run`, `dashboard`, `delete-survey`/`delete-surveys`/
`clear-surveys` after a change, and every `serve` startup) writes a new
numbered file into the *real* `reports/` even while reading a scratch
database. Check a suspicious dashboard's embedded source path (grep it for
`SQLite ·` — it names the exact `.db` path it was built from) before
deleting or trusting it. `manage.py run --mode file` is *not* a safe
no-op to "just check the happy path" either — it's idempotent against
duplicates already in the database, but sample IDs not yet present (e.g.
after a real `clear-surveys` happened between sessions) get inserted for
real. If you need to sanity-check the happy path, do it against a copy
like everything else here, not the live `data/etl.db`.

If you're testing something interactive (a confirmation prompt) from an
automated shell, be aware `sys.stdin.isatty()` will be `False` under most
forms of input redirection/piping, and every confirmation prompt in this
project correctly refuses in that case — that's the code working as
designed, not a bug to route around. On Windows specifically, prefer
`cmd /c "... < inputfile"` over PowerShell's `|` pipe to a native process
when you need to feed scripted input — PowerShell 5.1's own text encoding
when piping to native executables can corrupt non-ASCII output in ways
that look like a real bug but aren't (a fresh `sys.stdout.reconfigure`
before piping output usually resolves what's left).

## Robustness hardening already in place — don't regress these

A pass was made specifically to catch places where a bad input, a
misspelling, or a broken environment would surface as a raw Python
traceback instead of a clear message — since this project is meant to be
usable by someone who doesn't know what a traceback is. If you're adding a
new failure path anywhere near these, match the existing standard rather
than reverting to a bare exception:

- **`config/config.json` present but broken** (invalid JSON, or valid JSON
  that isn't an object): `config._load_json_config()` catches this and
  calls `sys.exit()` with a one-line, actionable message. This matters more
  than an ordinary config file would, because `config.py` is imported by
  *every* entry point — an unhandled exception here takes down the whole
  program, not one feature. A missing file is fine (falls back to hardcoded
  defaults) and was already handled before this pass.
- **A corrupted or non-SQLite `data/etl.db`** (interrupted write, wrong
  file renamed to `.db`, antivirus interference): `_get_sqlite_connection()`
  in `db/setup_db.py` catches `sqlite3.DatabaseError` and explains what to
  do (delete/rename it — a fresh one is created automatically — or restore
  from a backup) instead of surfacing `sqlite3.DatabaseError: file is not a
  database` as a bare traceback.
- **`pyodbc` not installed** when `DB_BACKEND=sqlserver`: caught as
  `ImportError` and pointed at `install.bat`/`requirements-sqlserver.txt`,
  rather than the bare `ModuleNotFoundError` that used to surface deep in a
  call stack.
- **SQL Server unreachable** (`pyodbc.Error` — wrong instance name, driver
  not installed, service not running): caught and pointed at README's SQL
  Server troubleshooting section, rather than a raw pyodbc traceback.
- **Python older than 3.10**: `install.bat` now hard-stops (`pause` +
  `exit /b 1`) instead of warning and continuing — the codebase's `X | Y`
  union type hints and `list[T]` generics are a `SyntaxError`, not a
  graceful degradation, on anything older, so warn-and-continue just meant
  "fail more confusingly, several steps later."
- **argparse-level validation** (`choices=`, `type=int`/`type=float` on
  every numeric flag, `required=True` subparsers) already covers misspelled
  subcommands, missing required arguments, invalid `--db`/`--mode`/
  `--opened` values, and non-numeric `--id-min`/`--score-min`/`--port`/
  `--max-records` — these produce argparse's own clean usage errors (exit
  code 2), not custom handling. Don't add manual validation for something
  argparse's own `type=`/`choices=` already covers.
- **Malformed individual records** in file-mode extraction (missing
  required fields) are already skipped per-record with a warning, not fatal
  to the run (`extract.py`'s `REQUIRED_FIELDS` check) — this predates the
  hardening pass and was confirmed still correct, not something to
  "improve" into a hard failure.
- **`menu.py`'s main loop used to spin forever on true EOF.** `_ask()`
  mapped both a blank Enter *and* EOFError to `""`, and `main()` treated
  `""` as "reprint the menu and loop again" — fine for a blank Enter, but
  once stdin actually hits EOF (closed, or redirected input that ran out),
  every subsequent `input()` call raises EOFError again immediately, so the
  loop reprinted the full menu banner as fast as possible, forever
  (reproduced directly: the output file hit 59MB in ~7 seconds before being
  killed). Fixed with a separate `_ask_top()` used only by `main()`'s own
  loop, which returns `None` specifically on EOF so `main()` can exit
  instead of looping; every other call site still uses plain `_ask()`,
  where treating EOF the same as a blank Enter is harmless (each of those
  prompts is a single read, not a loop). If you touch `menu.py`'s input
  handling, keep this distinction — don't collapse `_ask`/`_ask_top` back
  into one function without re-testing true EOF specifically (a blank line
  *followed by* more input doesn't exercise this path; only genuine stream
  exhaustion does).

## Style conventions already established in this repo

- No docstring/comment bloat: a one-line module docstring stating purpose,
  occasional inline comments only where the reasoning is genuinely
  non-obvious (a workaround, a KB citation, a "why not the simpler way").
  Don't add comments that restate what the code already says.
- Every `.bat` file resolves paths via `%~dp0`, never the current working
  directory, so double-click (Explorer sets cwd to the file's folder) and
  terminal invocation behave identically.
- CLI flags always fall back to `config/config.json`/`.env` when omitted —
  never require a flag for something that has a sensible configured
  default.
- Destructive CLI commands always support both an interactive path (typed
  confirmation) and a non-interactive path (explicit flags matching a
  live-checked value) — never just one or the other.
