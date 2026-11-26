# Bug Analyst

Ask questions about software defects in plain English — *"which component has the
worst defect density?"*, *"did Payments v3.2 break things?"*, *"where should we put
engineering effort next quarter?"* — and get answers backed by SQL that was
actually run, checked, and logged.

Modeled on [ai-analyst-lab/ai-analyst](https://github.com/ai-analyst-lab/ai-analyst):
the same three layers, scoped down to one domain (bug data across products).

| layer | ai-analyst | here |
|---|---|---|
| Persona + workflow | `CLAUDE.md` | `CLAUDE.md` — analyst loop, rules, defaults |
| Skills | `.claude/skills/*/SKILL.md` | `/ask`, `/focus-report`, `/release-impact`, `/setup`, `/connect-data`, `/remember` + auto-applied `validate-results`, `chart-style`, `sql-patterns` |
| Deterministic helpers | `helpers/` | `helpers/db.py` (read-only runner + query log), `schema.py` (profiler), `checks.py` (reconcile, freshness), `charts.py` |
| Memory | `.knowledge/` | schema, metric definitions, data quirks, corrections, verified question→SQL examples |
| Data connections | `data_sources.yaml` | SQLite (demo), DuckDB, Postgres, anything SQLAlchemy (Snowflake, BigQuery…), CSV import for Jira / GitHub / Linear |

## Quick start (Claude Code)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_demo_data.py      # synthetic 6-product bug tracker, ~8.7k bugs
python -m helpers.schema                  # profile -> .knowledge/schema.md
pytest -q                                 # 29 tests: guardrails, examples, planted patterns
claude                                    # then:
```
```
/ask which products have the most critical bugs, normalized for size?
/ask is Search getting worse?
/release-impact Payments API v3.2
/focus-report
```

## Quick start (standalone, no Claude Code)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_demo_data.py
cp .env.example .env                      # then put your ANTHROPIC_API_KEY in .env (gitignored)
python agent.py "Did Payments v3.2 make quality worse?"
python agent.py "Run the focus report"
python agent.py                           # interactive; --quiet hides tool progress, --model picks a model
```
`agent.py` loads `CLAUDE.md`, `.knowledge/` and the workflow skills in `.claude/skills/` as its
system prompt and gives the model seven tools: `list_tables`, `describe_table`, `run_sql`,
`make_chart`, `focus_report`, `write_file` (confined to `outputs/<date>-agent/`) and `remember`.
Set `BUG_ANALYST_MODEL` to change the default model.

## Using your own data

**Jira / GitHub / Linear export:**
```bash
python scripts/import_csv.py data/raw/jira.csv --tracker jira
```
then add to `data_sources.yaml` and run `/setup`:
```yaml
default: imported
sources:
  imported: {type: sqlite, path: data/imported.db}
```

**Warehouse:** add a `postgres` / `duckdb` / `sqlalchemy` source (templates in
`data_sources.yaml`), using a read-only DB user and `${ENV_VAR}` credentials, then
run `/connect-data` in Claude Code — it maps your columns onto the canonical schema
(product, component, severity, status, created/resolved, release) and runs `/setup`.

To get the normalized rates (the important ones for deciding where effort goes)
you also need denominators: `components.kloc`, `product_usage_monthly` (MAU) and
`teams.headcount`. Without them you still get counts, trends, MTTR and reopen rates.

## How a question becomes an answer

1. **Interpret** — map vague words to definitions in `.knowledge/metrics.md`
   ("critical" → S1+S2, "recently" → last 3 complete months).
2. **SQL** — written against `v_defects` (duplicates / won't-fix excluded, severity normalized),
   reusing verified patterns from `.knowledge/example_queries.sql`.
3. **Run** — `helpers/db.py` rejects anything but a single SELECT/WITH, opens the DB
   read-only, caps rows, times out, and logs every query with a result hash to
   `outputs/query_log.jsonl`.
4. **Validate** — totals reconcile, no join fan-out, partial month excluded, n ≥ 30, plausibility.
5. **Normalize & compare** — rank on rates (per KLOC / per 1k MAU), always with a baseline.
6. **Answer** — finding, table, what it means for engineering, caveats, SQL.

Corrections you give it (`/remember`) are written to `.knowledge/corrections.md`
and apply from then on.

## Demo data

`scripts/generate_demo_data.py` builds a fictional company with 6 products,
26 components and ~29 months of bugs, anchored to end yesterday. It has realistic
quirks (legacy severity labels, untriaged bugs, duplicates) and five planted
findings for testing the analyst: a regression spike in Payments `refunds` after
v3.2, very high defect density in Mobile `offline-sync`, a 35% reopen rate in
Search, a Web Dashboard that looks worst on raw counts but isn't, and a slow,
understaffed Admin Console team. `examples/sample-focus-report/` shows the output.

## Layout
```
CLAUDE.md                 persona, loop, rules
agent.py                  standalone API agent (tool use)
data_sources.yaml         connections + guardrails
.claude/skills/           9 skills
.claude/settings.json     tool permissions
.knowledge/               schema · metrics · quirks · corrections · example_queries.sql
helpers/                  db · schema · checks · charts
scripts/                  generate_demo_data · import_csv · focus_report
tests/                    pytest suite
outputs/                  generated work (gitignored)
```
