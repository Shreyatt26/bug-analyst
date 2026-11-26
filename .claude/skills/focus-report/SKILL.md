---
name: focus-report
description: Produce a full engineering-focus report - where bugs are concentrating across products and components, what is trending up, and where engineering effort should go next. Use when asked "where should we invest engineering effort", "quality review", "bug hotspots", "quarterly quality report".
---

# /focus-report — where should engineering effort go?

Output folder: `outputs/<yyyy-mm-dd>-focus-report/` with `analysis.py`, charts, `brief.md`.
Default window: last 12 complete months, with "recent" = last 3 complete months.

## Steps
Write `analysis.py` that imports `helpers.db.query` and `helpers.charts`, and run it.
Use `scripts/focus_report.py` as the reference implementation (run it directly for
the standard report; adapt it when the user wants a different cut).

1. **Freshness** — `helpers.checks.freshness()`; drop the partial month.
2. **Volume and severity by product** — defects, high-sev, % high-sev, customer tickets.
3. **Normalize** — high-sev per 1k MAU (user-facing products) and per KLOC (all).
4. **Trend** — last 3 months vs prior 3 months, per product and per component.
   Flag anything with ≥ +30% and ≥ 20 bugs in the recent window.
5. **Hotspots** — top 10 components by defects/KLOC; untriaged share per product.
6. **Flow** — median days-to-resolve for S1/S2, reopen rate, open backlog age.
7. **Capacity** — defects per engineer by owning team.
8. **Focus score** — formula in `.knowledge/metrics.md`. Show the component z-scores.
9. **Validate** — reconcile product totals against the overall total; flag n < 30.

## Charts (≤ 4, all via helpers/charts.py, action titles)
- Hotspot bar: components by defects/KLOC, highlight the top 2.
- Trend line: monthly high-sev defects by product, highlight the riser(s).
- Focus-score bar by product, highlight the top.
- Optional: heatmap product × month.

## brief.md structure
1. **Bottom line** (3 bullets max): where to put effort, in priority order, each with the number that justifies it.
2. **Evidence** — one short section per recommendation: chart + 2–3 sentences + table.
3. **What's fine** — products that look bad on raw counts but not on rates (call out explicitly).
4. **Caveats & definitions** — window, exclusions, denominators, small samples.
5. **Appendix** — queries run (from `outputs/query_log.jsonl`, with result sha).

Recommendations must be specific and actionable: name the component, the kind of
work (e.g. "add integration tests around refund idempotency", "fix verification
step — 35% of Search fixes reopen", "add headcount or triage rotation to Internal Tools").
