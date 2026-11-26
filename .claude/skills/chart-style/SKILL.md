---
name: chart-style
description: House style for every chart the analyst makes - gray first, one highlight color, action titles, traceable footers. Apply automatically when creating any chart.
---

# Chart style

Use `helpers/charts.py` (`bar`, `line`, `heatmap`). Don't hand-roll matplotlib styles.

- **Action title** that states the finding: "Refund bugs tripled after v3.2", not "Bugs by month".
- **Subtitle**: metric, population, window. "High-severity valid defects per month, Jun 2025–Oct 2026".
- **Gray first**: everything gray except the 1–2 things the title talks about (`highlight=[...]`).
- **Horizontal bars** for ranked categories, sorted. Lines for time. Heatmap for product × month.
- **Rates beat counts** for ranking; if you chart a count, say so in the subtitle.
- **Footer** (`source=`): `"Source: bug DB · query sha <sha> · excludes duplicates/won't-fix"`.
- One idea per chart; ≤ 4 charts per report.
- Mark releases / incidents with `events={"2026-06-09": "v3.2"}` on time series.
- After saving, open the PNG (Read tool) and check labels aren't clipped or overlapping.
