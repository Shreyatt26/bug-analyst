-- Verified question -> SQL pairs (few-shot examples for the analyst).
-- Each block: a `-- Q:` line, then one query. Tested by tests/test_examples.py.
-- Add new ones when a user confirms an answer was right.

-- Q: Which products had the most valid defects in the last 12 complete months?
SELECT product_name,
       COUNT(*)                                   AS defects,
       SUM(severity_norm IN ('S1','S2'))          AS high_sev,
       ROUND(100.0 * SUM(severity_norm IN ('S1','S2')) / COUNT(*), 1) AS high_sev_pct
FROM v_defects
WHERE created_at >= DATE('now', 'start of month', '-12 months')
  AND created_at <  DATE('now', 'start of month')
GROUP BY product_name
ORDER BY defects DESC;

-- Q: Normalize by users: high-severity defects per 1,000 monthly active users, by product
WITH monthly AS (
    SELECT product_id, created_month, SUM(severity_norm IN ('S1','S2')) AS high_sev
    FROM v_defects
    WHERE created_at >= DATE('now', 'start of month', '-12 months')
      AND created_at <  DATE('now', 'start of month')
    GROUP BY 1, 2
)
SELECT p.product_name,
       SUM(m.high_sev)                                         AS high_sev,
       ROUND(AVG(u.monthly_active_users))                      AS avg_mau,
       ROUND(1000.0 * SUM(m.high_sev) / SUM(u.monthly_active_users), 3) AS high_sev_per_1k_mau_month
FROM monthly m
JOIN product_usage_monthly u ON u.product_id = m.product_id AND u.month = m.created_month
JOIN products p ON p.product_id = m.product_id
GROUP BY p.product_name
ORDER BY high_sev_per_1k_mau_month DESC;

-- Q: Which components have the highest defect density (bugs per KLOC) in the last 6 months?
SELECT product_name, component_name, kloc,
       COUNT(*)                         AS defects,
       ROUND(COUNT(*) / kloc, 2)        AS defects_per_kloc
FROM v_defects
WHERE kloc IS NOT NULL
  AND created_at >= DATE('now', 'start of month', '-6 months')
  AND created_at <  DATE('now', 'start of month')
GROUP BY product_name, component_name, kloc
ORDER BY defects_per_kloc DESC
LIMIT 10;

-- Q: Monthly defect trend per product (complete months only)
SELECT created_month, product_name, COUNT(*) AS defects
FROM v_defects
WHERE created_at < DATE('now', 'start of month')
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q: Reopen rate by product - where do fixes not stick?
SELECT product_name,
       COUNT(*)                                             AS fixed,
       SUM(reopened_count > 0)                              AS reopened,
       ROUND(100.0 * SUM(reopened_count > 0) / COUNT(*), 1) AS reopen_rate_pct
FROM v_defects
WHERE is_fixed = 1
  AND created_at >= DATE('now', 'start of month', '-12 months')
GROUP BY product_name
ORDER BY reopen_rate_pct DESC;

-- Q: Median days to resolve S1/S2 bugs by product (median via window functions)
WITH ranked AS (
    SELECT product_name, days_to_resolve,
           ROW_NUMBER() OVER (PARTITION BY product_name ORDER BY days_to_resolve) AS rn,
           COUNT(*)     OVER (PARTITION BY product_name)                          AS n
    FROM v_defects
    WHERE is_fixed = 1 AND severity_norm IN ('S1','S2')
      AND created_at >= DATE('now', 'start of month', '-12 months')
)
SELECT product_name, n AS fixed_high_sev,
       ROUND(AVG(days_to_resolve), 1) AS median_days_to_resolve
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY product_name, n
ORDER BY median_days_to_resolve DESC;

-- Q: Defects found after each Payments API release (release quality)
SELECT r.version, r.released_at,
       COUNT(d.bug_id)                         AS defects,
       SUM(d.is_regression)                    AS regressions,
       SUM(d.severity_norm IN ('S1','S2'))     AS high_sev
FROM releases r
JOIN products p ON p.product_id = r.product_id
LEFT JOIN v_defects d ON d.found_in_release_id = r.release_id
WHERE p.product_name = 'Payments API'
  AND r.released_at >= DATE('now', '-12 months')
GROUP BY r.release_id, r.version, r.released_at
ORDER BY r.released_at;

-- Q: Open backlog and its age by product and severity
SELECT product_name, severity_norm,
       COUNT(*)                                                     AS open_bugs,
       ROUND(AVG(JULIANDAY('now') - JULIANDAY(created_at)), 0)      AS avg_age_days
FROM v_defects
WHERE is_open = 1
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q: Defects per engineer by owning team (capacity check)
SELECT t.team_name, t.headcount,
       COUNT(d.bug_id)                                AS defects_12m,
       ROUND(1.0 * COUNT(d.bug_id) / t.headcount, 1)  AS defects_per_engineer
FROM teams t
LEFT JOIN v_defects d ON d.assignee_team_id = t.team_id
     AND d.created_at >= DATE('now', 'start of month', '-12 months')
GROUP BY t.team_id, t.team_name, t.headcount
ORDER BY defects_per_engineer DESC;

-- Q: Share of untriaged bugs per product
SELECT product_name,
       COUNT(*)                                                            AS defects,
       SUM(component_name = '(untriaged)')                                 AS untriaged,
       ROUND(100.0 * SUM(component_name = '(untriaged)') / COUNT(*), 1)    AS untriaged_pct
FROM v_defects
WHERE created_at >= DATE('now', 'start of month', '-3 months')
GROUP BY product_name
ORDER BY untriaged_pct DESC;
