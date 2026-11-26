# Corrections log

Things a human told the analyst it got wrong, or business rules learned in
conversation. Newest first. Added via `/remember`. These override defaults.

| date | rule / correction | applies to |
|---|---|---|
| 2026-11-25 | `found_in_release_id` is the latest release at creation for non-regressions; for regressions it can point to the introducing (older) release. Check `release_id < latest-at-creation` before assuming it is a timing marker. | release attribution, `/release-impact` |
| _example_ | "Bugs from `source = 'internal'` filed by the QA bot are noise; exclude title LIKE '[bot]%'" | all defect counts |
