---
name: sql-patterns
description: SQL dialect notes and reusable patterns (date windows, medians, period-over-period, safe joins to usage tables) for SQLite, DuckDB, Postgres, Snowflake and BigQuery. Apply automatically when writing SQL for bug analysis.
---

# SQL patterns

## Date windows (last 12 complete months)
| dialect | start | end (exclusive) |
|---|---|---|
| SQLite | `DATE('now','start of month','-12 months')` | `DATE('now','start of month')` |
| DuckDB / Postgres | `DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '12 months'` | `DATE_TRUNC('month', CURRENT_DATE)` |
| Snowflake | `DATEADD(month, -12, DATE_TRUNC('month', CURRENT_DATE))` | `DATE_TRUNC('month', CURRENT_DATE)` |
| BigQuery | `DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)` | `DATE_TRUNC(CURRENT_DATE(), MONTH)` |

Always use half-open windows: `>= start AND < end`.

## Days between
SQLite `JULIANDAY(b) - JULIANDAY(a)` · Postgres `EXTRACT(EPOCH FROM b - a)/86400` ·
DuckDB `DATE_DIFF('day', a, b)` · Snowflake `DATEDIFF(day, a, b)`.

## Median
DuckDB/Postgres/Snowflake: `MEDIAN(x)` or `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)`.
SQLite has none — use the ROW_NUMBER pattern in `.knowledge/example_queries.sql`,
or pull the grouped values into pandas and use `.median()`.

## Period over period (recent 3 months vs prior 3)
```sql
SELECT product_name,
  SUM(created_at >= DATE('now','start of month','-3 months')) AS recent,
  SUM(created_at <  DATE('now','start of month','-3 months')) AS prior,
  ROUND(100.0 * (SUM(created_at >= DATE('now','start of month','-3 months'))
               - SUM(created_at <  DATE('now','start of month','-3 months')))
        / NULLIF(SUM(created_at < DATE('now','start of month','-3 months')), 0), 1) AS pct_change
FROM v_defects
WHERE created_at >= DATE('now','start of month','-6 months')
  AND created_at <  DATE('now','start of month')
GROUP BY 1;
```
(Postgres/Snowflake: wrap booleans: `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.)

## Joining usage without fan-out
Aggregate bugs to (product, month) **first**, then join `product_usage_monthly`.
Joining raw bugs to usage and then summing MAU multiplies MAU by bug count.

## Booleans
SQLite/DuckDB allow `SUM(cond)`. Postgres needs `SUM(CASE WHEN cond THEN 1 ELSE 0 END)`
or `COUNT(*) FILTER (WHERE cond)`.

## Safety
One statement per query, SELECT/WITH only. Add `LIMIT` when exploring raw rows.
