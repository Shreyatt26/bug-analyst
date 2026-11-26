"""Profile the connected database and write .knowledge/schema.md.

Run once after connecting a new source (the /setup skill does this), and again
whenever the schema changes. The analyst reads schema.md before writing SQL,
which is the single biggest driver of correct NL->SQL.

    python -m helpers.schema            # writes .knowledge/schema.md
    python -m helpers.schema --print    # print instead of writing
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from helpers.db import ROOT, connect

LOW_CARD = 25        # list all values for columns with <= this many distinct values


def q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def profile_table(con, table: str) -> dict:
    cols = con.columns(table)
    n = con.query(f"SELECT COUNT(*) FROM {q(table)}", purpose="schema profile").rows[0][0]
    out = {"table": table, "rows": n, "columns": []}
    for name, typ in cols:
        c = q(name)
        r = con.query(
            f"SELECT COUNT(*) - COUNT({c}), COUNT(DISTINCT {c}), MIN({c}), MAX({c}) FROM {q(table)}",
            purpose="schema profile").rows[0]
        nulls, distinct, mn, mx = r
        info = {"name": name, "type": typ, "null_pct": (nulls / n * 100) if n else 0,
                "distinct": distinct, "min": mn, "max": mx, "values": None}
        if distinct and distinct <= LOW_CARD:
            vals = con.query(
                f"SELECT {c}, COUNT(*) FROM {q(table)} GROUP BY 1 ORDER BY 2 DESC",
                purpose="schema profile").rows
            info["values"] = vals
        out["columns"].append(info)
    return out


def render(profiles: list[dict], source: str, dialect: str) -> str:
    lines = [
        "# Schema (auto-generated)",
        "",
        f"Source: `{source}` · dialect: **{dialect}** · profiled {date.today().isoformat()}",
        "",
        "Regenerate with `python -m helpers.schema`. Hand-written meaning, joins and",
        "gotchas live in `quirks.md` and `metrics.md` — read those too.",
        "",
    ]
    for p in profiles:
        lines += [f"## `{p['table']}` — {p['rows']:,} rows", "",
                  "| column | type | null % | distinct | range / values |", "|---|---|---|---|---|"]
        for c in p["columns"]:
            if c["values"] is not None:
                rng = ", ".join(f"`{v}` ({k:,})" for v, k in c["values"][:LOW_CARD])
            elif c["min"] is not None:
                mn, mx = str(c["min"])[:24], str(c["max"])[:24]
                rng = f"{mn} … {mx}"
            else:
                rng = ""
            lines.append(f"| {c['name']} | {c['type']} | {c['null_pct']:.1f} | {c['distinct']:,} | {rng} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--source")
    a = ap.parse_args(argv)
    con = connect(a.source)
    profiles = [profile_table(con, t) for t, _ in con.tables()]
    md = render(profiles, con.name, con.dialect)
    if a.print:
        print(md)
    else:
        out = ROOT / ".knowledge" / "schema.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md)
        print(f"wrote {out.relative_to(ROOT)} ({len(profiles)} tables)")


if __name__ == "__main__":
    main()
