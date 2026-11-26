---
name: setup
description: First-run setup - verify the data connection, profile every table, and build the .knowledge folder (schema, quirks, metrics) so natural-language questions can be answered accurately. Use when starting fresh, after /connect-data, or when schema.md is missing or stale.
---

# /setup

1. `python -c "import yaml, pandas, matplotlib"` — if missing: `pip install -r requirements.txt`.
2. If `default: demo` and `data/bugs.db` is missing: `python scripts/generate_demo_data.py`.
3. Test the connection: `python -m helpers.db tables`.
4. Profile: `python -m helpers.schema` → writes `.knowledge/schema.md`. Read it.
5. Look for quirks and write them into `.knowledge/quirks.md` (keep existing notes):
   - columns with mixed vocabularies (e.g. two severity schemes) → run a GROUP BY by year
   - high NULL % on columns you'd join or group on
   - statuses that mean "not a real bug" (duplicate, invalid, won't fix, cannot reproduce)
   - future timestamps, or resolved_at < created_at
   - text-typed versions/dates
6. Make sure there is a clean analysis view equivalent to `v_defects`
   (exclusions + normalized severity + joined names). On a read-only warehouse
   you can't create it — instead, save its SELECT as a CTE snippet at the top of
   `.knowledge/metrics.md` and tell the user they may want a DBA to create the view.
7. Check `metrics.md` definitions still match the column names; adjust if not.
8. Run `pytest -q` (examples must still execute) and report: tables found,
   row counts, date range, quirks found, and 3 example questions the user can ask.
