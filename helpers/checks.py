"""Deterministic sanity checks the analyst runs before presenting numbers.

    python -m helpers.checks reconcile "SELECT COUNT(*) FROM v_defects" \
        "SELECT product_name, COUNT(*) FROM v_defects GROUP BY 1"
    python -m helpers.checks freshness
"""
from __future__ import annotations

import argparse
from datetime import date, datetime

from helpers.db import connect

MIN_N = 30   # below this, rates are flagged as unreliable


def reconcile(total_sql: str, parts_sql: str, value_col: int = -1, tol: float = 0.001) -> dict:
    """Check that a breakdown adds back up to the total (catches join fan-out / dropped NULLs)."""
    con = connect()
    total = con.query(total_sql, purpose="check: reconcile total").rows[0][0]
    parts = sum((r[value_col] or 0) for r in con.query(parts_sql, purpose="check: reconcile parts").rows)
    ok = abs(total - parts) <= max(tol * abs(total), 1e-9)
    return {"ok": ok, "total": total, "sum_of_parts": parts, "diff": parts - total}


def small_samples(rows, n_col: int, label_col: int = 0, min_n: int = MIN_N) -> list:
    """Return labels whose sample size is below min_n."""
    return [r[label_col] for r in rows if (r[n_col] or 0) < min_n]


def freshness(table: str = "bugs", ts_col: str = "created_at") -> dict:
    """Latest data point and whether the current month is partial."""
    con = connect()
    mx = con.query(f"SELECT MAX({ts_col}) FROM {table}", purpose="check: freshness").rows[0][0]
    latest = datetime.fromisoformat(str(mx)[:19]).date() if mx else None
    today = date.today()
    # the month holding the latest record is incomplete unless data runs to its last days
    partial = bool(latest and latest.day < 28)
    return {"latest": str(latest), "today": str(today), "latest_month_partial": partial,
            "advice": "Exclude or label the latest month — it is incomplete." if partial else "OK"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconcile"); r.add_argument("total_sql"); r.add_argument("parts_sql")
    f = sub.add_parser("freshness"); f.add_argument("--table", default="bugs"); f.add_argument("--col", default="created_at")
    a = ap.parse_args(argv)
    if a.cmd == "reconcile":
        res = reconcile(a.total_sql, a.parts_sql)
    else:
        res = freshness(a.table, a.col)
    for k, v in res.items():
        print(f"{k}: {v}")
    if res.get("ok") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
