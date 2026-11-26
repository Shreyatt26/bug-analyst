# Data quirks and gotchas

Hand-maintained. Add to this whenever profiling or a user reveals something.

## Bug tracker
- **Legacy severity labels.** Bugs created before 2025-01-01 were migrated from the
  old tracker and use `Critical / Major / Minor / Trivial`. Map to S1/S2/S3/S4.
  `v_defects.severity_norm` already does this. Never `GROUP BY severity` raw.
  (Demo DB: all dates are anchored to the day it was generated, so this cutoff,
  the v3.2 release date etc. move with it — the generator prints the actual dates.)
- **Not real defects.** `status IN ('duplicate','wont_fix')` (~6%). Excluded by `v_defects`.
- **Untriaged.** ~6% of bugs have `component_id IS NULL`. `v_defects.component_name`
  shows them as `(untriaged)`. A large untriaged share for one product is itself a finding.
- **resolved_at** is NULL while a bug is open. `resolved` and `closed` both count as fixed.
- **Reopens** push `resolved_at` later, so MTTR already includes reopen cycles.
- **priority vs severity.** Priority is set by PMs and drifts; prefer severity for quality questions.
- **assignee_team_id** in the demo always equals the product's owner team.

## Usage / size denominators
- `product_usage_monthly.month` is the first of the month; join on `v_defects.created_month`.
- `components.kloc` is today's snapshot, not historical.
- Internal products (Admin Console, Data Pipeline) have tiny MAU — per-MAU rates
  explode for them. Use per-KLOC for internal tools, per-MAU for user-facing.

## Time
- Data ends a day or two before "today"; the latest month is partial.
- Timestamps are stored as text `YYYY-MM-DD HH:MM[:SS]` (UTC). Use `DATE()`, `JULIANDAY()`.

## Releases
- `releases.version` is text: don't `MAX(version)` (string sort). Order by `released_at`.
- `found_in_release_id` is the latest release of the bug's product at creation time for every
  non-regression (7,071 of 7,071). For `is_regression = 1` it is the same for 1,001 of 1,085, but
  the other 84 point to an *older* release: all are Payments API refunds regressions tagged v3.2
  and filed after v3.3 shipped (verified 2026-11-25). So on regressions the field can carry the
  introducing release. On non-regressions it is only a timing marker, never a cause. Treat
  `found_in_release_id` + `is_regression = 1` as attribution evidence, not proof (confirm with commits).
  Never use it alone to say a release caused a bug. Order releases by `released_at`.
