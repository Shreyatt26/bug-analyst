---
name: connect-data
description: Connect the analyst to a real bug data source - Postgres, DuckDB, Snowflake/BigQuery via SQLAlchemy, or a Jira / GitHub Issues / Linear CSV export - and map its columns to the analyst's canonical bug schema.
---

# /connect-data

Ask the user (one question) where their bug data lives, unless they said.

## A. A warehouse / database (Postgres, Snowflake, BigQuery, DuckDB)
1. Add a source to `data_sources.yaml` (templates are in the file). Credentials go
   in environment variables (`${BUG_DB_DSN}`), never in the YAML. Use a **read-only** DB user.
2. Install the driver it needs (`psycopg2-binary`, `duckdb`, `snowflake-sqlalchemy`, …).
3. Set `default:` to the new source, run `python -m helpers.db tables`.
4. Continue with **C. Mapping**.

## B. A CSV export (Jira, GitHub Issues, Linear, Azure DevOps)
1. Put the file in `data/raw/`.
2. Run `python scripts/import_csv.py data/raw/<file>.csv --tracker jira` (or `github`, `linear`, `generic`).
   It loads into `data/imported.db`, prints the column mapping it guessed, and
   builds `products`, `components`, `bugs` and the `v_defects` view.
3. Show the user the guessed mapping and ask them to confirm the two that matter
   most: which field is the **product** and which is **severity**.
4. Add a `imported` sqlite source pointing at `data/imported.db` and make it default.

## C. Mapping to the canonical schema
The skills assume these concepts. Find the equivalent of each and record the
mapping at the top of `.knowledge/quirks.md`:

| concept | typical Jira field | typical GitHub field |
|---|---|---|
| product | Project / Product (custom) | repository |
| component | Component/s | label `area/*` |
| severity | Severity (custom) / Priority | label `sev/*` / `priority/*` |
| status | Status + Resolution | state + `state_reason` |
| created / resolved | Created / Resolved | created_at / closed_at |
| found in release | Affects Version/s | milestone |
| regression | label `regression` | label `regression` |
| not-a-bug | Resolution in (Duplicate, Won't Do, Cannot Reproduce) | `state_reason = not_planned` |

Denominators (KLOC, MAU, headcount) usually live elsewhere. If missing, tell the
user which rates won't be available and offer a small CSV template they can fill in.

Then run `/setup`.
