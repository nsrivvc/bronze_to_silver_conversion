# Bronze → Silver (Pipeline Accelerator)

A modular batch system that reads **Bronze** tables from Postgres, applies
transformation logic, and writes curated **Silver** tables. This repo handles
**only** Bronze → Silver. Ingestion (JSON → Bronze) and export (Silver →
downstream) live elsewhere.

Each Silver table is its own self-registering module, so new transformations are
added by dropping in a file — no central list to edit.

## Architecture

```
run.py                        CLI: --list / --table NAME / --all / --show-sql NAME
src/
  config.py                   env-driven settings (DB URL, schema names, log level)
  logging_config.py           logging setup (stdout)
  db/connection.py            SQLAlchemy engine factory (the only driver-aware file)
  core/
    base.py                   SilverTransformation base class (the shared pattern)
    registry.py               @register decorator + REGISTRY
    runner.py                 run one / run all: per-table transaction, checks, logging
  transformations/
    __init__.py               auto-discovers every module in this folder
    silver_firm_transport_rate.py   implemented example
```

- **One file per Silver table.** Each subclasses `SilverTransformation` and
  provides `create_table_sql()` and `transform_sql()`.
- **Per-table transactions.** The runner runs each transformation in its own
  `engine.begin()` block, so a failure rolls back cleanly and doesn't stop the
  others. It also checks the required Bronze tables exist first (skips with a
  clear message if not).
- **Idempotent.** `CREATE TABLE IF NOT EXISTS` + a `UNIQUE` natural key +
  `ON CONFLICT DO UPDATE`. Re-running refreshes rows in place — no duplicates.
- **Driver-isolated.** Only `db/connection.py` imports the driver, so
  `--list` / `--show-sql` work with no database, and swapping databases later is
  contained to one file.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then edit DATABASE_URL to point at your Postgres
```

For a local/dummy Postgres, the quickest option is Docker:

```bash
docker run --name pa-postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=pipeline -p 5432:5432 -d postgres:16
```

(That matches the default `DATABASE_URL` in `.env.example`.) This codebase
assumes the **Bronze tables already exist**; it reads them and writes Silver.

## Run

```bash
python run.py --list                                 # what's registered
python run.py --inspect                              # snapshot existing Bronze/Silver tables + row counts (no transforms)
python run.py --show-sql silver_firm_transport_rate  # inspect SQL (no DB needed)
python run.py --table silver_firm_transport_rate     # run one transformation
python run.py --all                                  # run all of them
```

Run `--inspect` before transforming to confirm which Bronze tables exist and how
many rows they hold, and which transformations are READY vs BLOCKED (missing a
source). It's read-only — it never writes or alters data — so it's safe to run
anytime to check the state as data flows through. Run it again afterward to see
the new Silver row counts.

The run commands exit non-zero if any transformation fails, so a scheduler can
flag the job.

## Add a new Silver table

1. Copy `src/transformations/silver_firm_transport_rate.py` to a new file, e.g.
   `silver_pipeline_locations.py`.
2. Change four things (each is commented in the example):
   - the class name and `name`
   - `bronze_sources` (the Bronze tables you read)
   - `create_table_sql()` (your columns/types)
   - `transform_sql()` (your column mapping + business rules)
3. Keep the idempotency pieces: `CREATE TABLE IF NOT EXISTS` with a `UNIQUE`
   natural key, and `INSERT … SELECT … ON CONFLICT (key) DO UPDATE`.

That's it — `python run.py --list` will show it immediately.

> Most transformations are pure SQL. If one needs real Python logic, override
> `run(self, conn)` in your subclass instead of using the two SQL methods.

## Running it on a schedule later

`run.py` is a plain batch command that reads all config from environment
variables, which makes it portable to any scheduler without code changes.

A ready-to-use workflow is included at `.github/workflows/bronze_to_silver.yml`
("Workflow 2: Bronze → Silver" in the architecture diagram). It:

- runs on a `cron` schedule (`:30` past each hour, offset after the `:00` Bronze
  ingestion) and on manual dispatch;
- lets you pick `all` or a single transformation at dispatch time;
- reads the Neon connection string from the `DATABASE_URL` repo secret (the same
  secret used by the ingestion repo — Settings → Secrets and variables →
  Actions);
- runs `python run.py --inspect` before and after, so the run log shows Bronze
  inputs and the resulting Silver row counts.

To run it: push the repo, add the `DATABASE_URL` secret, then Actions →
**bronze-to-silver** → **Run workflow**.

For other schedulers:

- **Azure Container Apps job** — build a small image (`python:3.11-slim`,
  `pip install -r requirements.txt`, `CMD ["python","run.py","--all"]`) and set
  `DATABASE_URL` as a secret/env var on the job.

Because nothing is hardcoded and logs go to stdout, the same command works
locally, in CI, and in a cloud job.
```
