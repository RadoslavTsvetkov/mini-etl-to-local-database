# TASK_001: Mini ETL to Local Database

## Task

Use Claude, the AI coding assistant, to help you complete this task.

**Goal:** Build a small but complete ETL pipeline that pulls new Client Analytics surveys, stores them in a local database, marks them as opened through the Command API, and logs every run.

**What to build:**
- An extraction step that fetches or reads new Client Analytics survey records (for example, from a file, endpoint, or mock dataset).
- A local database using SQL Server with a clear schema for surveys and run metadata.
- A load step that inserts the extracted surveys into the database, avoiding duplicates.
- A step that calls the Command API to mark each loaded survey as opened.
- A logging mechanism that records the date, number of surveys processed, and any errors for each run.
- A main entry point (for example, `etl.py`) that runs the full pipeline end to end.

**Getting started with Claude:** Open a fresh project folder and ask Claude to scaffold a Python ETL pipeline with separate `extract.py`, `load.py`, `api_client.py`, and `logger.py` modules, plus a SQLite database setup script. Start with a small set of sample survey data so you can test the flow before connecting to a real source.

## Definition of Done
- [ ] Running `etl.py` completes all steps without errors on sample data.
- [ ] The database schema is documented in a `schema.md` or `schema.sql` file.
- [ ] Sample survey records appear in the database after a run.
- [ ] Each survey loaded is marked as opened through a simulated or real Command API call.
- [ ] A log file shows at least one completed run with the count of processed surveys and any warnings or errors.
