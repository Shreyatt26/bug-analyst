---
name: remember
description: Save a correction, definition or business rule the user gave (e.g. "don't count internal bugs", "Search and Autocomplete are the same team") to the analyst's persistent memory so future answers use it. Use whenever the user corrects an answer.
---

# /remember

1. Restate the rule in one unambiguous sentence, plus the SQL it implies
   (e.g. `AND source <> 'internal'`).
2. Append a row at the top of the table in `.knowledge/corrections.md`
   (date · rule · applies to).
3. If it changes a canonical metric, also update `.knowledge/metrics.md`.
   If it's a data oddity, update `.knowledge/quirks.md`.
4. If a verified question→SQL pair came out of it, append it to
   `.knowledge/example_queries.sql` and run `pytest -q tests/test_examples.py`.
5. Re-run the query that was wrong and show the corrected answer.
