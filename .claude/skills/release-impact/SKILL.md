---
name: release-impact
description: Assess whether a specific release or deploy made software quality worse - compare defects, regressions and severity before vs after a release. Use for "did v3.2 break things", "what happened after the last release", "which release was the worst".
---

# /release-impact — did this release hurt quality?

1. Identify the release: `SELECT * FROM releases r JOIN products p USING(product_id) WHERE ...`.
   Order by `released_at`, never by `version` text.
2. Windows: N days before vs N days after (default 28 days; shorten if the next
   release lands sooner, and say so).
3. Compare, for that product: defects/day, high-sev/day, regressions, customer tickets,
   and the component mix (which component moved).
4. Attribution evidence, strongest first:
   - `found_in_release_id = <release>` and `is_regression = 1`
   - concentration in one component that the release touched
   - same-period change in *other* products (control: if everyone spiked, it's not the release)
5. Chart: daily or weekly line with a dashed marker at the release (`events=` in `helpers.charts.line`).
6. Answer: "After <version> (<date>), <product> high-severity defects went from X/week to Y/week
   (+Z%), concentrated in <component> (N of M). Other products were flat → likely release-related."
   State the confidence level and what would confirm it (e.g. linked commits / incident reviews).
