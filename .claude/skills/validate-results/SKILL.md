---
name: validate-results
description: Checks to run on every query result before presenting numbers - reconciliation, join fan-out, NULL buckets, partial periods, sample size, plausibility. Apply automatically whenever reporting bug metrics.
---

# Validate before you present

Run through this list. Fix what fails; disclose what can't be fixed.

1. **Reconcile.** Do breakdown rows sum to the total? Use
   `python -m helpers.checks reconcile "<total sql>" "<breakdown sql>"`.
   A mismatch usually means a join fan-out (one bug → many rows) or dropped NULLs.
2. **Fan-out.** After any JOIN, check `COUNT(*)` vs `COUNT(DISTINCT bug_id)`.
3. **NULL buckets.** Untriaged components, missing severity, unmatched usage month — report them.
4. **Partial period.** `python -m helpers.checks freshness`. Never compare a partial month to full ones.
5. **Sample size.** Flag any rate computed on n < 30. Don't rank on it.
6. **Denominator sanity.** Per-MAU rates for internal tools (tiny MAU) are meaningless;
   per-KLOC for long windows uses a current KLOC snapshot.
7. **Plausibility.** Compare with the obvious baseline (overall average, prior period).
   A >3x jump is either the headline or a bug in your SQL — find out which by
   pulling 5 example rows (`bug_key`, `title`, `created_at`).
8. **Definition check.** Did you use `v_defects` and `severity_norm`? Any correction in
   `corrections.md` that applies?
9. **Re-derive the headline number** with an independent query (different SQL shape)
   when it drives a recommendation.
