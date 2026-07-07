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
terminal required, and **no commands to memorize**. Double-clicking
`run.bat` with no arguments scrapes the newest unopened surveys from the
live Shopmetrics Query API (read-only; the mark-opened step stays mocked),
refreshes the dashboard, opens it in your browser, and then drops you into
a **numbered menu right there in the console** — "view my data", "look
around Shopmetrics", "delete a survey", "run it again", etc. — so you never
need to know a single `manage.py` flag to do the everyday things (§1.1
covers it). The first time, if `.env` has no API credentials yet, it asks
for your Client ID and Client Secret right in the console, saves them to
`.env`, and verifies them before continuing (§4.1 explains where these come
from). The same happens if the saved credentials are **wrong** — every API
run verifies them upfront, and if Shopmetrics rejects them (mistyped,
deactivated, or regenerated), you're asked to re-enter them and `.env` is
rewritten.

To skip straight to one specific command (`view`, `browse`, `dashboard`,
`serve`, `set-client`, `delete-survey`, `delete-surveys`, `clear-surveys`,
`setup-db`, or any flag) instead of going through the menu, open a terminal in this folder
and run `run.bat <command> ...` — it forwards whatever you type to the
actual program (see the sections below for the full list). Only the plain
double-click (no arguments) shows the menu; running `run.bat <command>`
from an already-open terminal behaves like any normal command and exits
when it's done.

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
run.bat                    (double-click, or "run.bat run": scrapes the live API by default)
run.bat run --mode file    (explicitly offline instead: sample data, no network/credentials)
```

By default — both the bare double-click and the explicit `run.bat run` —
this pulls real surveys from the Shopmetrics Query API (read-only) and
simulates the "mark opened" step. This is deliberate: a new install should
scrape real data out of the box, not sample data. Credentials are verified
against the API before every run: if they're missing from `.env` — or
saved but rejected by Shopmetrics — you're prompted to (re-)enter them and
`.env` is updated (§4.1). Prefer to try it offline first? `--mode file`
switches to the bundled sample data with no network calls and no
credentials needed — see §4.3 for the full list of things `EXTRACTION_MODE`/
`COMMAND_MODE` control. Either way it's safe to run repeatedly; records
already loaded are skipped as duplicates.

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

## 1.1 The menu — "okay, now what?"

After a plain double-clicked `run.bat` finishes scraping and opens the
dashboard, it doesn't just close — it shows a short numbered list right in
the same console window:

```
============================================================
 What would you like to do next?
============================================================
Full command-line details for everything below are in README.md.

  EXPLORE YOUR DATA
    1)  View the collected surveys & run history (in this terminal)
    2)  Look around live Shopmetrics data (read-only lookup)
    3)  Refresh the dashboard (regenerate the HTML report)
    4)  Open the dashboard with LIVE Delete buttons (serve mode)
  GET MORE DATA
    5)  Run the pipeline again (scrape newest surveys from Shopmetrics)
  SETTINGS
    6)  Change which client/form to scrape (lists what your credentials can access)
  REMOVE DATA — see README.md §2.2 first
    7)  Delete ONE survey, by its ID
    8)  Delete surveys matching a filter (title / location / date / ID range / ...)
    9)  Delete ALL surveys — drastic, asks for extra confirmation

    0)  Exit
```

This exists so you never have to know a `manage.py` subcommand name (let
alone its flags) to do any of the everyday things — pick a number, answer
one or two plain-English questions if it asks any (a survey ID, a filter
value, that sort of thing), and it runs the matching command for you
underneath. Typing `menu` (or `help`/`?`) reprints the list if it's
scrolled off; `0` (or `exit`) closes it. Every option that asks for
confirmation (deleting something) asks exactly the same way it would if
you'd typed the command yourself — nothing about safety is skipped or
shortened just because it came from the menu.

Picking option **4** (`serve`) or **5** (`run` again) hands control to that
command directly (a live server you stop with `Ctrl+C`, or a fresh pipeline
run) — once it finishes, you're back at the menu. This menu is purely a
front door to the commands documented in the rest of this file — if you'd
rather skip it and type commands directly, `run.bat <command>` (§0) always
works too, from a terminal, with no menu involved.

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

A plain double-clicked dashboard file has no server behind it, so its
**Delete** / **Clear ALL surveys** controls are disabled (you'll see a note
saying so above the table) — see §2.2 to actually remove data, either from
the dashboard itself (via `run.bat serve`) or from the command line.

## 2.2 Removing surveys from the database

Three ways to permanently delete survey data, from "one specific survey" to
"everything matching a rule" to "literally everything" — all three take a
JSON backup first (in `data/backups/`) and all three refresh the dashboard
automatically afterward. **None of these touch anything on the Shopmetrics
side** — they only remove rows from *your local database* (SQLite or SQL
Server, whichever `--db`/`DB_BACKEND` currently points at); if you extract
again with `--mode api`, a deleted survey that's still unopened on your
Shopmetrics account will simply be re-downloaded, since extraction is keyed
off Shopmetrics' own opened/unopened flag, not your local database's
contents.

### Command line (always available)

**One specific survey, by ID:**
```
run.bat delete-survey 10656
```
Shows the survey's title/location, then asks you to type `yes` to confirm.
Skip the prompt in a script with `--yes` (still writes the backup first).

**Everything matching a rule — title, location, date range, ID range, or
any combination:**
```
run.bat delete-surveys --location Geneva
run.bat delete-surveys --title "Q3 Store Visit" --status Completed
run.bat delete-surveys --id-min 10001 --id-max 10050
run.bat delete-surveys --date-from 2026-01-01 --date-to 2026-03-31
run.bat delete-surveys --opened no --fieldworker "Jane"
```
Every flag is optional and they combine with AND (all given conditions must
match). Text flags (`--title`, `--location`, `--status`, `--campaign`,
`--fieldworker`) match case-insensitive substrings, so `--location geneva`
matches "Geneva" and "Geneva - Airport" alike. `--ids 10001,10002,10005`
targets an arbitrary, non-contiguous set by exact ID instead of a range.
Full flag list: `run.bat delete-surveys --help`.

It shows exactly how many surveys match and a preview of the first 10
(ID, title, location, date) before asking you to confirm — and **refuses
to run with no filters at all**, on purpose, so you can't reach for this
command and accidentally wipe the whole table; use `clear-surveys` for
that. Confirmation works the same way as `clear-surveys` below: type the
exact match count to confirm interactively, or pass both `--yes` and
`--expect-count N` in a script.

**Absolutely everything:**
```
run.bat clear-surveys
```
Because this is the most destructive and hardest-to-undo option, it asks
for **two** separate confirmations, not one:
1. Type the *exact number* of surveys shown (e.g. `1807`) — a typo-guard
   that also makes you actually look at how many rows are about to go.
2. Type `DELETE ALL` (exact capitals).

Only after both match does it back up every row to JSON and delete them.
Get either one wrong (or just press Enter) and nothing is deleted. In a
script, replace both prompts with two flags that must both be correct:
`run.bat clear-surveys --yes --expect-count 1807` — get the count wrong and
it refuses, so a stale/copy-pasted command can't nuke a database that's
since grown or shrunk.

### From the dashboard itself (`run.bat serve`)

A dashboard opened as a plain file can't write to the database — there's no
server behind a `.html` file for it to talk to. `run.bat serve` (or
`python src/manage.py serve`) fixes that by serving the same dashboard over
a small local web server, which turns on three real, working actions above
and inside the survey table: **Delete** (in the survey Details view —
single survey), **Delete by filter…** (a form with the same fields as
`delete-surveys` above — title, location, status, campaign, fieldworker, ID
range, date range, score range, opened yes/no — plus a live "N surveys
match" preview before you commit), and **Clear ALL surveys…**:

```
run.bat serve
```
Opens `http://127.0.0.1:8765/` in your browser (use `--port` to pick a
different port). Every one of the three asks for confirmation via browser
dialogs — single delete just once, the filtered and clear-all actions both
make you type the exact number back (clear-all also requires typing
`DELETE ALL`) — same seriousness as the command line. Every action backs up
first, deletes, regenerates the dashboard, and takes you straight to the
fresh (now-updated) report. Press `Ctrl+C` in the console to stop serving —
it doesn't run unless you start it, and it only listens on `127.0.0.1`
(your machine only, never your network).

### About the backups

Every delete (single or "clear all") writes the full row(s) it's about to
remove to a timestamped JSON file in `data/backups/` (gitignored, like the
rest of `data/`) *before* touching the database, and prints the file path.
Restoring from one isn't a built-in command (re-importing is a manual job:
the JSON is the same shape as the `surveys` table's columns) — treat the
backup as an insurance policy for "oops", not an undo button.

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

This is what the pipeline does **by default** — pull real survey data from
an actual Shopmetrics site (offline sample data is the opt-in alternative,
`--mode file`, for trying things out with no credentials or network).

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

**What "client/form ID" (`SHOPMETRICS_CLIENT_OR_FORM_IDS`) actually means:**
a Shopmetrics API user's credentials can potentially see many different
clients, brands, or survey forms — `ClientOrFormIDs` (a negative number,
e.g. `-995`) is *which one* the pipeline scrapes. It's checked into
`config/config.json` alongside `SHOPMETRICS_BASE_URL`, so cloning this repo
and entering *credentials valid for that same site and scope* reproduces
the same live backlog this project has been built and tested against
(currently "Delight Coffee (CX Analytics Demo)" on
`training212.shopmetrics.com`, ID `-995`) — see the FAQ at the end of this
section if you're unsure whether that applies to you.

- **To see every ID your credentials can access**, run `run.bat browse
  clients` (read-only, always safe) — it prints every ID with its name.
- **To change which one gets scraped**, the easy way is
  `run.bat set-client` (or menu option **6**): it fetches that same list,
  lets you pick a number (or paste an ID directly), and saves your choice
  to `.env` for you — no manual file editing needed. Non-interactive/
  scripted: `run.bat set-client --id -1044` sets it directly.
- **For a one-off run without changing the saved default**, add `--client`
  to `run`: `run.bat run --client -1044`.
- The manual way still works too, if you'd rather: edit
  `SHOPMETRICS_CLIENT_OR_FORM_IDS` directly in `config/config.json` (shared
  default) or `.env` (personal override).

> **FAQ: "I cloned this from GitHub and entered my own credentials — will I
> get the same ~1800 surveys?"** Only if those credentials have access to
> the *same* Shopmetrics site and client scope (`training212.shopmetrics.com`,
> `-995`) this project defaults to. If you have your own, separate
> Shopmetrics account instead, you'll need to point `SHOPMETRICS_BASE_URL`/
> `SHOPMETRICS_CLIENT_OR_FORM_IDS` at *your* account (`run.bat set-client`
> after your credentials are set up, or edit `config/config.json`/`.env`
> directly) — you'll then get *your* account's real, live survey backlog
> instead, whatever size that happens to be. That's the pipeline correctly
> scraping whichever account it's actually authorized against, not a bug.

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

`EXTRACTION_MODE=api` is already the checked-in default in
`config/config.json` — a plain `run.bat` or `run.bat run` already does this,
no flags needed. `COMMAND_MODE` stays at its safe default, `mock`, since the
real "mark opened" call is currently broken upstream (next paragraph) —
override either per-run with flags instead of editing `config/config.json`,
so you don't leave a "live" setting turned on by accident:

```
run.bat run --mode api --command-mode mock
```

- `--mode api` calls the real Shopmetrics Query API (read-only — safe to try;
  this is also just the default, spelled out).
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
| Extraction source | `--mode` | `EXTRACTION_MODE` (config.json) | `api` (**default** — real Query API, read-only, needs credentials) or `file` (offline sample data, no network/credentials) |
| Mark-opened mode | `--command-mode` | `COMMAND_MODE` (config.json) | `mock` (default, no network) or `live` (real Command API, **writes real data** — currently returns HTTP 500 on this account, §10.3) |
| Database backend | `--db` | `DB_BACKEND` (config.json) | `sqlite` (default, `data/etl.db`, no extra install) or `sqlserver` (local SQL Server, viewable in SSMS) |
| Records per run | `--max-records` | `SHOPMETRICS_MAX_RECORDS_PER_RUN` (config.json) | `5000` (default — collects the full backlog every `api` run). Lower it for a small test batch. |
| Client/form scraped | `--client` (one-off) | `SHOPMETRICS_CLIENT_OR_FORM_IDS` (config.json/.env) | `-995` (default). Change the saved value with `run.bat set-client` (interactive picker) or `set-client --id <value>`; see §4.1. |
| Auto-open dashboard | `--no-open` | `OPEN_DASHBOARD` (config.json/.env) | `true` (default): open the newly numbered `reports/dashboard<N>.html` in the browser after `run`/`dashboard`. |
| SQL Server instance | — | `SQLSERVER_SERVER` (config.json) | `.\SQLEXPRESS` (default) |
| SQL Server database | — | `SQLSERVER_DATABASE` (config.json) | `ShopmetricsETL` (default); created automatically if missing |
| API credentials | — | `SHOPMETRICS_CLIENT_ID`/`_SECRET` (`.env` only) | *(unset until you're prompted for them)*; required since `api` is the default mode |

`--db`/`--mode`/`--command-mode`/`--max-records` also work on `run.bat view`,
`dashboard`, and `setup-db` where applicable (each accepts `--db`; `run` accepts all four).

## Troubleshooting

- **`install.bat` says Python wasn't found, or that it's too old**: install
  Python 3.10+ from [python.org](https://www.python.org/downloads/) and make
  sure "Add Python to PATH" was checked during install, then re-run
  `install.bat`. 3.10+ is a hard requirement, not a suggestion — the code
  uses newer type-hint syntax that fails outright on anything older.
- **A command exits with a plain one-line error instead of doing anything**
  (config file, database, or SQL Server connection problems): these are
  deliberately short-circuited with a clear message rather than a Python
  traceback — read the message, it names the exact file/setting at fault.
  Common ones: `config/config.json is not valid JSON` (fix the syntax, or
  `git checkout -- config/config.json` to restore the checked-in version);
  `<path> doesn't look like a valid SQLite database` (the `.db` file is
  corrupted or isn't actually a SQLite file — delete/rename it and re-run,
  a fresh one is created automatically); `needs the 'pyodbc' package` (run
  `install.bat` again, or `pip install -r requirements-sqlserver.txt`).
- **The menu asks for something and then says "Refusing ... in a
  non-interactive context"**: this shows up if `run.bat`'s console isn't a
  real interactive terminal (e.g. its output is being redirected/piped by
  something else) — the confirmation genuinely needs to be typed at a real
  keyboard prompt, the same restriction `delete-survey`/`clear-surveys` have
  always had from the command line. Just double-clicking `run.bat` normally
  gives you a real console, so this shouldn't come up in everyday use.
- **`run.bat` says the virtual environment wasn't found**: run `install.bat`
  first (once per machine/clone).
- **HTTP 403 / Cloudflare error 1010**: already handled — `api_client.py`
  sends a browser-style `User-Agent` header, which this site's WAF requires.
- **"SHOPMETRICS_CLIENT_ID / SHOPMETRICS_CLIENT_SECRET are not set"**: you're
  in `api`/`live` mode without a filled-in `.env`. Follow §4.1 above, or just
  run from a console and enter them at the prompt.
- **"The API rejected these credentials" (HTTP 400 `invalid_client`)**: the
  values in `.env` are wrong — mistyped, swapped, deactivated, or regenerated
  in Shopmetrics. Run from a console to be prompted for fresh values (they're
  rewritten into `.env`), or fix the two lines by hand.
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
- **`clear-surveys` / `delete-surveys` refuses with a count mismatch**:
  either you typed the wrong number at the prompt, or (in a script)
  `--expect-count` doesn't match the database's *current* matching row
  count — re-run `run.bat view surveys` (or just re-run the same command)
  to see the current total, then use that exact number. This check exists
  specifically to stop a stale command from deleting more or less than you
  think.
- **`delete-surveys` says "No filters given — refuses to run with none"**:
  by design — an empty filter would match every survey, and that's what
  `clear-surveys` is for, deliberately spelled differently so you can't
  reach for the wrong command by habit. Add at least one `--title`/
  `--location`/`--id-min`/etc. flag, or use `clear-surveys` if you really do
  want everything gone.
- **Dashboard's Delete / Delete by filter / Clear-all buttons are grayed
  out with a note about `manage.py serve`**: expected — a dashboard opened
  as a plain file has no server behind it to write to the database. Run
  `run.bat serve` instead (§2.2) and use the copy of the dashboard it opens
  for you.
- **"Missing or invalid dashboard token" from `run.bat serve`**: the page
  you're clicking Delete/Delete by filter/Clear-all on is stale (from a
  previous `serve` session, or you reloaded a URL after restarting `serve`,
  which mints a new token each time). Reload the page at
  `http://127.0.0.1:8765/` and retry.
- **`run.bat serve` fails with "Only one usage of each socket address..."**:
  something (often a `serve` you forgot was already running) is already
  using that port. Pick a different one: `run.bat serve --port 8766`.
- **"Delete by filter" preview says 0 matches but you expected some**: text
  filters (title/location/status/campaign/fieldworker) are substring
  matches on the exact stored value, not fuzzy search — check spelling and
  try a shorter fragment (e.g. `"geneva"` instead of `"Geneva Office"`).
  Date filters use the survey's `submitted_at` date, not when it was loaded
  into your database.
