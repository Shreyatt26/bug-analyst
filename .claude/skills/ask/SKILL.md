---
name: ask
description: Answer any natural-language question about bugs, defects, incidents, quality, regressions, backlog, MTTR or engineering effort by turning it into SQL against the bug database. Use for questions like "which product has the most critical bugs", "is Search getting worse", "where are bugs coming from".
---

# /ask — natural language → SQL → checked answer

Input: the user's question (`$ARGUMENTS`).

## 1. Ground yourself (once per session)
- Read `.knowledge/schema.md`, `metrics.md`, `quirks.md`, `corrections.md`.
- Skim `.knowledge/example_queries.sql` — reuse a verified pattern if one fits.

## 2. Interpret
Write one line: *"Reading this as: <metric> by <dimension>, <population>, <time window>."*
Map vague words to definitions:
| user says | means |
|---|---|
| "bugs", "issues" | valid defects (`v_defects`) |
| "critical", "serious", "bad" | `severity_norm IN ('S1','S2')` |
| "recently", "lately" | last 3 complete months, compared with the 3 before |
| "this year" | calendar YTD, latest partial month labelled |
| "where", "which area" | component level within product |
| "slow to fix" | median `days_to_resolve` for fixed bugs, by severity |
| "getting worse" | trend of a rate over complete months vs a baseline period |
| "effort should go" | run `/focus-report` instead |

Ask a clarifying question only if two readings would change the conclusion.

## 3. Query
- Start with the smallest query that answers the question; aggregate in SQL.
- Run: `python -m helpers.db query --purpose "<question>" "<SQL>"`.
- If a query errors, read the error, fix the SQL (check column names in schema.md),
  retry. After 3 failures, show the user the error and your SQL.

## 4. Validate (see `validate-results` skill) before writing anything to the user.

## 5. Answer format
```
**<One-sentence finding with the key number and its comparison.>**

| table (≤ 10 rows, rate + raw count) |

What this means for engineering: <1–2 sentences: where effort should go and why>.
Caveats: <partial month, small n, untriaged share, definition used>.

<details><summary>SQL</summary> ...query... </details>
```
Offer exactly one natural follow-up (e.g. drill into the top component).

If the answer needs a chart, use `helpers/charts.py` and save under
`outputs/<yyyy-mm-dd>-<slug>/`, then show the image path.
