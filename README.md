# Client Analytics Survey ETL — Usage Guide

A small Python ETL pipeline: extract new Client Analytics survey instances,
load them into a local database (SQLite or SQL Server — your choice), mark
them as opened via the Shopmetrics Command API, and log every run. See
`SPECIFICATION.md` for the full design (including the detailed project
structure) and `schema.md` for the database schema.

## 0. Getting started (new clone / new machine)

**Double-click `install.bat`.** Run it once. A console window opens and:
creates a virtual environment (`.venv/`), installs everything needed
(including the optional SQL Server support), and creates your local `.env`
from the template. It ends with "Press any key to continue . . ." — that's
normal, it's just keeping the window open so you can read the result; press
any key (or just close the window) once you've seen "Install complete!".

Requires Python 3.10+ already installed and on `PATH` — if the window says
Python wasn't found, install it from
[python.org](https://www.python.org/downloads/) (check **"Add python.exe to
PATH"** during install) and double-click `install.bat` again.

**Then, any time you want to use the pipeline: double-click `run.bat`.**
That's it — no manual `pip install`, no activating a venv by hand, no
terminal required. Double-clicking `run.bat` with no arguments scrapes the
newest unopened surveys from the live Shopmetrics Query API (read-only; the
mark-opened step stays mocked), refreshes the dashboard, opens it in your
browser, then waits for a key press so you can read the output. The first
time, if `.env` has no API credentials yet, it asks for your Client ID and
Client Secret right in the console, saves them to `.env`, and verifies them
before continuing (§4.1 explains where these come from).

To use the other commands (`view`, `browse`, `dashboard`, `setup-db`, or any
flag), open a terminal in this folder instead and run `run.bat <command>
...` — it forwards whatever you type to the actual program (see the
sections below for the full list). Only the plain double-click (no
arguments) needs the "press any key" pause; running `run.bat` from an
already-open terminal behaves like any normal command.

If you're not on Windows, or prefer running Python directly: every example
below also works as `python src/manage.py <command> ...` from an activated
virtual environment (see `requirements.txt` / `requirements-sqlserver.txt`
for what to `pip install`).

## Requirements

- Python 3.10+.
- No third-party packages for the default SQLite backend. The optional SQL
  Server backend needs `pyodbc` — `install.bat` installs it automatically.

## 1. Run it

```
run.bat            (double-click: scrapes the live API — same as "run.bat run --mode api")
run.bat run        (uses config.json defaults: offline sample data, no network)
run.bat run --mode file   (explicitly offline)
```

Double-clicking `run.bat` pulls real surveys from the Shopmetrics Query API
(read-only) and simulates the "mark opened" step. If credentials are missing
from `.env`, it prompts for them once, saves them, and verifies them against
the API before running. The explicit `run.bat run` command still follows
`config/config.json` defaults (`file`/`mock` — offline sample data). Either
way it's safe to run repeatedly; records already loaded are skipped as
duplicates.

Every run automatically generates a fresh HTML dashboard (§2.1), **opens it
in your default browser**, and prints a callout in the terminal pointing at
it. Reports are numbered (`dashboard1.html`, `dashboard2.html`, …) and never
overwritten — each run writes the next number and keeps the older ones:
```
Dashboard updated (opened in your browser — pass --no-open to skip): C:\...\reports\dashboard7.html
```
Pass `--no-open` (or set `OPEN_DASHBOARD=false` in `config/config.json`/`.env`)
if you'd rather it not pop up a browser tab each run.
(A dashboard regeneration failure is logged as a warning but never fails
the run itself — it's a nice-to-have on top of the actual ETL result.)

Override any setting for just this run with flags, instead of editing
`config/config.json` or `.env`:
```
run.bat run --mode api --command-mode mock --db sqlserver --max-records 500
```
Every flag is optional and falls back to `config/config.json`/`.env`
defaults when omitted — see `--help` for the full list, or the quick
reference in §4.4.

## 2. View the collected data

```
run.bat view            # surveys + run history
run.bat view surveys     # just the surveys table
run.bat view runs        # just the run history
run.bat view <survey_id> # drill into one survey's responses (Q&A, campaign, status, score)
```

Output is color-highlighted in the terminal (green/yellow/red by score,
green/red for opened status, cyan for survey status) — works in Windows
Terminal and VS Code's integrated terminal out of the box.

The raw log is at `logs/etl.log`. The raw database is `data/etl.db` (a plain
SQLite file — you can also open it with a free GUI tool like
[DB Browser for SQLite](https://sqlitebrowser.org/) if you prefer clicking
around instead of the CLI viewer).

## 2.1 Generate an HTML dashboard

`run.bat run` already regenerates this for you every time (§1) — you only
need this command to refresh it on demand *without* running the pipeline
again (e.g. after switching `--db` just to look at the other backend's data):
```
run.bat dashboard
```

Writes a self-contained HTML report to `reports/dashboard<N>.html` — numbered
in order (`dashboard1.html`, `dashboard2.html`, …), never overwriting earlier
reports, so you keep a history; delete old ones whenever you like (each is a
few MB). It opens in your default browser automatically (pass `--no-open` to
skip that; the file also opens fine by double-clicking it later — no server
needed). It
includes KPI tiles (total surveys, opened, average score, errors), a score
distribution chart, breakdowns by status/location/title, recent run history,
and a table of **every** survey in the database. Working with the table:

- **Search** by survey ID (or any title/location/fieldworker text) and
  narrow further with the **All / Opened / Not opened** filter buttons —
  the match counter updates live.
- **Click any row** (or its Details button) to open the survey's full
  record — all stored fields plus the responses (`responses_json`) rendered
  as question-by-question answer chips and comments, with the raw JSON one
  click away.
- **Step through surveys** without closing the detail view: the ‹ › buttons
  (or the ←/→ arrow keys) move through exactly the rows your current
  search/filter/sort shows.
- **Sort** by clicking any column header; hover any chart bar for exact
  counts and percentages.

Supports light and dark mode automatically (follows your OS/browser theme).

## 3. Using SQL Server / SSMS instead of (or alongside) SQLite

The pipeline can also store data in a local SQL Server database, browsable
in SQL Server Management Studio (SSMS), as an alternative to SQLite. Both
have the exact same schema (see `schema.md`) — you pick one per run via
`DB_BACKEND`, so you can freely switch back and forth.

### 3.1 One-time setup

Already done if you ran `install.bat` — it installs `pyodbc` (the only
third-party dependency this project has, and only needed for this backend)
by default. You'll also need a SQL Server ODBC driver (17 or 18) installed —
already present if SSMS/SQL Server Express is installed. If you skipped
`install.bat` and are managing your own environment:
```
pip install -r requirements-sqlserver.txt
```

### 3.2 Run against SQL Server

```
run.bat run --db sqlserver
run.bat view --db sqlserver
```

The first run auto-creates the `ShopmetricsETL` database and its two tables
(`surveys`, `etl_runs`) on your local SQL Server instance — nothing to set
up by hand. Defaults assume a local instance at `.\SQLEXPRESS` with Windows
Authentication (no password); override `SQLSERVER_SERVER`, `SQLSERVER_DATABASE`
in `config/config.json`, or `SQLSERVER_USER`/`SQLSERVER_PASSWORD` in `.env`
if you need SQL Server authentication instead.

### 3.3 View it in SSMS

1. Open **SQL Server Management Studio**.
2. In the "Connect to Server" dialog:
   - **Server name:** `.\SQLEXPRESS` (or whatever you set `SQLSERVER_SERVER`
     to). If your machine has more than one local SQL Server instance (e.g.
     `SQLEXPRESS` *and* `SQLEXPRESS01`), make sure you pick the one matching
     `SQLSERVER_SERVER` — the data won't be on the other one.
   - **Authentication:** Windows Authentication (unless you set
     `SQLSERVER_USER`/`SQLSERVER_PASSWORD` for SQL auth instead).
   - Click **Connect**.
3. In **Object Explorer** (left panel), expand the server node → expand the
   **Databases** folder.
4. `ShopmetricsETL` should be listed there. Expand it → **Tables** →
   right-click `dbo.surveys` or `dbo.etl_runs` → **Select Top 1000 Rows**.

**If `ShopmetricsETL` doesn't show up under Databases:** right-click the
**Databases** folder → **Refresh** (F5) — Object Explorer doesn't
auto-refresh, so if you were already connected before running with
`DB_BACKEND=sqlserver`, SSMS won't show the new database until you refresh.

**To double-check from the command line instead of SSMS** (useful if
something looks off):
```
sqlcmd -S ".\SQLEXPRESS" -E -Q "SELECT name, state_desc FROM sys.databases WHERE name = 'ShopmetricsETL';"
sqlcmd -S ".\SQLEXPRESS" -E -d ShopmetricsETL -Q "SELECT COUNT(*) FROM surveys;"
```

Leaving `DB_BACKEND` unset (or `sqlite`) keeps everything on SQLite as
before — the two backends don't interfere with each other; each just reads/
writes its own storage.

## 4. Using the real Shopmetrics API

The pipeline can also pull real data and make real "mark opened" calls
against an actual Shopmetrics site, instead of the offline sample data.

### 4.1 Set up your credentials — **do this once**

`install.bat` already created `.env` from the template for you. Open it and
fill in your Shopmetrics API credentials:
```
SHOPMETRICS_CLIENT_ID=your-client-id
SHOPMETRICS_CLIENT_SECRET=your-client-secret
```
`src/config.py` loads `.env` automatically — no need to set environment
variables by hand every session. Everything else (base URL, client/form ID,
mode defaults) lives in `config/config.json`; edit that file directly if you
want to change the checked-in defaults, or uncomment the matching line in
`.env` for a local-only override — see `.env.example`.

**`.env` is listed in `.gitignore` and will never be committed.** Never
paste your `client_secret`, `client_id`, or Shopmetrics login into any
tracked file (`SPECIFICATION.md`, `config/config.json`, commit messages,
issues, chat logs you intend to share, etc.) — treat it like a password. If
a secret is ever exposed, deactivate/regenerate it in Shopmetrics
(Administration → Tools and Settings → Site Settings → Other → API v2
Authorization – Client Credentials) rather than just deleting the file.

### 4.2 Browse real Shopmetrics surveys directly

Yes, this is possible — `run.bat browse` talks straight to the live
Shopmetrics Query API to let you look around, without running the ETL
pipeline or touching the local database at all. Needs `.env` set up (§4.1);
it always hits the real API, regardless of `EXTRACTION_MODE`/`COMMAND_MODE`.

```
run.bat browse clients
```
Lists every `ClientOrFormIDs` value this API user can query (client/brand
names and their IDs) — use one of these as `--client` below.

```
run.bat browse surveys --client -995
run.bat browse surveys --client -995 --limit 50
run.bat browse surveys --client -995 --unopened-only
```
Lists survey instances for a client: title, location, date, score, status.
`--limit` caps how many rows print (default 25). `--unopened-only` shows
only surveys this API user hasn't viewed yet.

```
run.bat browse show 10656
```
Shows the full question/answer detail for one survey instance ID (from the
list above).

This is read-only — it can't change anything on your Shopmetrics account,
so there's nothing risky about exploring with it.

### 4.3 Run the full ETL pipeline in live mode

Leave `config/config.json`'s `EXTRACTION_MODE`/`COMMAND_MODE` at their safe
defaults (`file`/`mock`) for everyday use, and override them per-run with
flags instead, so you don't forget a "live" setting turned on:

```
run.bat run --mode api --command-mode mock
```

- `--mode api` calls the real Shopmetrics Query API (read-only — safe to try).
- `--command-mode live` calls the real Command API to mark the survey's
  viewed/read status (`BulkProcessing_SetReadStatus`). **Currently fails with
  HTTP 500 on this account** — the dataset this calls appears to be
  deprecated on newer Shopmetrics platform versions; see `SPECIFICATION.md`
  §10.3 for the test that confirmed this. Stick with `--command-mode mock`
  (the default) for real runs until that's resolved (e.g. by asking
  Shopmetrics support for the current equivalent).

**How much gets pulled:** each API-mode run pulls up to
`SHOPMETRICS_MAX_RECORDS_PER_RUN` survey instances — default **5000**, i.e.
the full backlog for your configured client every run (~1800 unopened
surveys on this account). That's still just 2 API calls total (one list
query, one responses query) regardless of how many rows come back, so it
doesn't run afoul of the KB's fair-use guidance. Use `--max-records` to
pull a smaller batch for a quick test:
```
run.bat run --mode api --max-records 10
```
Run a full pull once with `--db sqlite` and once with `--db sqlserver` if
you want the full dataset in both places.

### 4.4 Quick reference

| Setting | `run.bat run` flag | Config source | Values / effect |
|---|---|---|---|
| Extraction source | `--mode` | `EXTRACTION_MODE` (config.json) | `file` (default, no network) or `api` (real Query API, read-only) |
| Mark-opened mode | `--command-mode` | `COMMAND_MODE` (config.json) | `mock` (default, no network) or `live` (real Command API, **writes real data** — currently returns HTTP 500 on this account, §10.3) |
| Database backend | `--db` | `DB_BACKEND` (config.json) | `sqlite` (default, `data/etl.db`, no extra install) or `sqlserver` (local SQL Server, viewable in SSMS) |
| Records per run | `--max-records` | `SHOPMETRICS_MAX_RECORDS_PER_RUN` (config.json) | `5000` (default — collects the full backlog every `api` run). Lower it for a small test batch. |
| Auto-open dashboard | `--no-open` | `OPEN_DASHBOARD` (config.json/.env) | `true` (default): open the newly numbered `reports/dashboard<N>.html` in the browser after `run`/`dashboard`. |
| SQL Server instance | — | `SQLSERVER_SERVER` (config.json) | `.\SQLEXPRESS` (default) |
| SQL Server database | — | `SQLSERVER_DATABASE` (config.json) | `ShopmetricsETL` (default); created automatically if missing |
| API credentials | — | `SHOPMETRICS_CLIENT_ID`/`_SECRET` (`.env` only) | *(unset)*; required for `api`/`live` |

`--db`/`--mode`/`--command-mode`/`--max-records` also work on `run.bat view`,
`dashboard`, and `setup-db` where applicable (each accepts `--db`; `run` accepts all four).

## Troubleshooting

- **`install.bat` says Python wasn't found**: install Python 3.10+ from
  [python.org](https://www.python.org/downloads/) and make sure "Add Python
  to PATH" was checked during install, then re-run `install.bat`.
- **`run.bat` says the virtual environment wasn't found**: run `install.bat`
  first (once per machine/clone).
- **HTTP 403 / Cloudflare error 1010**: already handled — `api_client.py`
  sends a browser-style `User-Agent` header, which this site's WAF requires.
- **"SHOPMETRICS_CLIENT_ID / SHOPMETRICS_CLIENT_SECRET are not set"**: you're
  in `api`/`live` mode without a filled-in `.env`. Follow §4.1 above.
- **SQL Server: "Login failed" / driver not found**: confirm SSMS or SQL
  Server Express is installed, and that `install.bat` completed the pyodbc
  install step without error. Check `SQLSERVER_SERVER` matches your actual
  instance name (see it in SSMS's connection dialog).
- **`ShopmetricsETL` doesn't appear under Databases in SSMS**: refresh the
  Databases folder (F5) — SSMS doesn't auto-detect new databases created
  after you connected. Also double check you connected to the same instance
  name as `SQLSERVER_SERVER` (machines can have more than one local SQL
  Server instance).
- **Command API validation errors** (e.g. survey status): these are real
  responses from Shopmetrics' business rules, not bugs — read the message,
  it names the exact constraint that failed.
