# Metric definitions

Canonical definitions. If a user's definition differs, use theirs, say so, and
log it with `/remember` if it should become the default.

All SQL below is SQLite against the demo DB. For other dialects swap the date
functions (see `sql-patterns` skill).

## Population
**Valid defect** = a bug that is not `duplicate` or `wont_fix`. Use `v_defects`.

## Volume
| metric | definition | SQL |
|---|---|---|
| defects | count of valid defects created in period | `COUNT(*) FROM v_defects WHERE created_at >= :start AND created_at < :end` |
| high-severity defects | S1 + S2 | `SUM(severity_norm IN ('S1','S2'))` |
| production escapes | valid defects found in production | `SUM(environment = 'production')` |
| customer-reported | `source = 'customer_report'` | `SUM(source = 'customer_report')` |
| customer impact | linked support tickets | `SUM(customer_tickets)` |

## Normalized rates (use these to rank)
| metric | definition | notes |
|---|---|---|
| **defect density** | defects / KLOC of the component | `kloc` is a current snapshot, so density over long windows is approximate |
| **defects per 1k MAU** | monthly defects / (MAU/1000), joined on product + month | best for comparing user-facing products of different size |
| **defects per release** | defects with `found_in_release_id` = release / releases in period | for release quality |
| **escape rate** | production defects / all defects | high = testing isn't catching things |
| **regression rate** | `is_regression = 1` / all defects | high = changes break existing behaviour |

## Flow / responsiveness
| metric | definition | notes |
|---|---|---|
| **MTTR** (days) | median of `days_to_resolve` for fixed bugs (`is_fixed = 1`) | use the median, not the mean — heavy right tail. Compute median in Python or with the window pattern in `sql-patterns`. Report by severity: S1 MTTR matters most |
| **reopen rate** | share of fixed bugs with `reopened_count > 0` | high = fixes don't stick / weak verification |
| **open backlog** | `is_open = 1` right now | |
| **backlog age** | `JULIANDAY('now') - JULIANDAY(created_at)` for open bugs | |
| **SLA breach** | S1 not fixed within 3 days, S2 within 14 | company SLA (demo assumption) |

## Engineering-effort score (for `/focus-report`)
A transparent, explainable ranking — not a black box. For each product (or component):

```
focus_score = 0.35 * z(high-sev defects per 1k MAU or per KLOC)
            + 0.20 * z(trend: last 3 months vs prior 3 months, % change)
            + 0.15 * z(customer tickets)
            + 0.15 * z(S1/S2 median MTTR)
            + 0.15 * z(reopen rate)
```
z = z-score across the units being compared. Always show the components of the
score next to it so a reader can disagree with the weights.

## Engineering capacity
`teams.headcount` gives engineers per owning team. "Defects per engineer" =
open + new defects in period / headcount — useful to flag understaffed teams.
