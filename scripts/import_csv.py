"""Import a Jira / GitHub Issues / Linear / generic CSV export into the analyst's
canonical schema (SQLite), so every skill and example query works on real data.

    python scripts/import_csv.py data/raw/jira.csv --tracker jira
    python scripts/import_csv.py data/raw/issues.csv --tracker github --out data/imported.db
    python scripts/import_csv.py data/raw/x.csv --map product=Project --map severity="Custom field (Severity)"

It prints the column mapping it used. Check it — especially product and severity —
then add a source to data_sources.yaml:

    imported:
      type: sqlite
      path: data/imported.db
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# canonical field -> candidate column names (case-insensitive), per tracker
CANDIDATES = {
    "key": ["issue key", "key", "number", "identifier", "id", "issue id"],
    "title": ["summary", "title", "name"],
    "product": ["project name", "project", "product", "custom field (product)", "repository", "repo", "team"],
    "component": ["component/s", "components", "component", "area", "labels"],
    "severity": ["custom field (severity)", "severity", "priority", "labels"],
    "priority": ["priority"],
    "status": ["status", "state"],
    "resolution": ["resolution", "state_reason", "state reason"],
    "type": ["issue type", "type", "kind"],
    "created": ["created", "created_at", "created at", "createdat", "opened"],
    "resolved": ["resolved", "resolutiondate", "closed_at", "closed at", "completed at", "completedat", "resolved at"],
    "affects_version": ["affects version/s", "affects versions", "milestone", "cycle"],
    "labels": ["labels", "label"],
}

SEV_MAP = [
    (r"\b(s0|s1|sev[-_ /]?[01]|p0|blocker|highest|critical|urgent)\b", "S1"),
    (r"\b(s2|sev[-_ /]?2|p1|high|major)\b", "S2"),
    (r"\b(s3|sev[-_ /]?3|p2|medium|normal|minor)\b", "S3"),
    (r"\b(s4|sev[-_ /]?4|p3|p4|low|lowest|trivial)\b", "S4"),
]
NOT_A_BUG = r"duplicate|won'?t (fix|do)|cannot reproduce|not planned|invalid|not a bug|declined|canceled|cancelled"
DONE = r"done|closed|resolved|fixed|completed|released|verified"


def find_col(cols: list[str], field: str, override: dict) -> str | None:
    if field in override:
        if override[field] not in cols:
            sys.exit(f"--map {field}={override[field]}: no such column")
        return override[field]
    lower = {c.lower().strip(): c for c in cols}
    for cand in CANDIDATES[field]:
        if cand in lower:
            return lower[cand]
    return None


def norm_sev(v) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).lower()
    for pat, out in SEV_MAP:
        if re.search(pat, s):
            return out
    return None


def norm_status(status, resolution) -> str:
    s = f"{status or ''} {resolution or ''}".lower()
    if re.search(NOT_A_BUG, s):
        return "duplicate" if "duplicate" in s else "wont_fix"
    if re.search(DONE, s):
        return "closed"
    if re.search(r"progress|review|doing|started", s):
        return "in_progress"
    return "open"


def to_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return ts.dt.tz_convert(None).dt.strftime("%Y-%m-%d %H:%M:%S")


def run(csv: Path, tracker: str, out: Path, override: dict, bugs_only: bool) -> None:
    raw = pd.read_csv(csv)
    cols = list(raw.columns)
    m = {f: find_col(cols, f, override) for f in CANDIDATES}
    print(f"Column mapping ({tracker}):")
    for f, c in m.items():
        print(f"  {f:16} <- {c!r}")
    for required in ("title", "created", "status"):
        if not m[required]:
            sys.exit(f"Could not find a column for '{required}'. Pass --map {required}=<column>.")

    df = raw.copy()
    if bugs_only and m["type"]:
        before = len(df)
        df = df[df[m["type"]].astype(str).str.lower().str.contains("bug")]
        print(f"Kept {len(df):,} of {before:,} rows where {m['type']!r} contains 'bug' (use --all-types to keep all)")

    product = df[m["product"]].fillna("(unknown)").astype(str) if m["product"] else pd.Series("(all)", index=df.index)
    component = df[m["component"]].astype(str).str.split(r"[,;]").str[0].str.strip() if m["component"] else None
    if component is not None:
        component = component.replace({"nan": None, "": None})

    sev_src = df[m["severity"]] if m["severity"] else pd.Series(None, index=df.index)
    if m["labels"] and m["severity"] != m["labels"]:   # fall back to sev/* labels
        sev = sev_src.map(norm_sev).fillna(df[m["labels"]].map(norm_sev))
    else:
        sev = sev_src.map(norm_sev)

    status = [norm_status(s, r) for s, r in zip(df[m["status"]],
                                                 df[m["resolution"]] if m["resolution"] else [None] * len(df))]
    labels = df[m["labels"]].astype(str).str.lower() if m["labels"] else pd.Series("", index=df.index)

    products = pd.DataFrame({"product_name": sorted(product.unique())})
    products["product_id"] = range(1, len(products) + 1)
    pid = product.map(dict(zip(products.product_name, products.product_id)))

    comp_df = pd.DataFrame({"product_id": pid, "component_name": component}) if component is not None else \
        pd.DataFrame(columns=["product_id", "component_name"])
    comp_df = comp_df.dropna().drop_duplicates().reset_index(drop=True)
    comp_df["component_id"] = range(1, len(comp_df) + 1)
    comp_key = {(r.product_id, r.component_name): r.component_id for r in comp_df.itertuples()}
    cid = [comp_key.get((p, c)) for p, c in zip(pid, component if component is not None else [None] * len(df))]

    created = to_ts(df[m["created"]])
    resolved = to_ts(df[m["resolved"]]) if m["resolved"] else pd.Series(None, index=df.index)
    bugs = pd.DataFrame({
        "bug_id": range(1, len(df) + 1),
        "bug_key": df[m["key"]].astype(str).values if m["key"] else [f"BUG-{i}" for i in range(1, len(df) + 1)],
        "product_id": pid.values,
        "component_id": cid,
        "title": df[m["title"]].astype(str).values,
        "severity": sev.values,
        "priority": df[m["priority"]].astype(str).values if m["priority"] else None,
        "status": status,
        "source": None, "environment": None,
        "is_regression": labels.str.contains("regression").astype(int).values,
        "found_in_release_id": None, "fixed_in_release_id": None, "assignee_team_id": None,
        "reopened_count": 0, "customer_tickets": 0,
        "created_at": created.values,
        "resolved_at": resolved.values,
    })
    open_mask = bugs.status.isin(["open", "in_progress"])
    bugs.loc[open_mask, "resolved_at"] = None

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    products.assign(platform=None, owner_team_id=None, launched_at=None)[
        ["product_id", "product_name", "platform", "owner_team_id", "launched_at"]].to_sql("products", con, index=False)
    comp_df.assign(kloc=None)[["component_id", "product_id", "component_name", "kloc"]].to_sql("components", con, index=False)
    bugs.to_sql("bugs", con, index=False)
    con.executescript("""
        CREATE TABLE teams (team_id INTEGER PRIMARY KEY, team_name TEXT, headcount INTEGER);
        CREATE TABLE releases (release_id INTEGER PRIMARY KEY, product_id INTEGER, version TEXT, released_at DATE);
        CREATE TABLE product_usage_monthly (product_id INTEGER, month DATE, monthly_active_users INTEGER, deploys INTEGER);
        CREATE VIEW v_defects AS
        SELECT b.*, COALESCE(b.severity, 'S3') AS severity_norm, p.product_name,
               COALESCE(c.component_name, '(untriaged)') AS component_name, c.kloc,
               DATE(b.created_at, 'start of month') AS created_month,
               CASE WHEN b.status IN ('resolved','closed') THEN 1 ELSE 0 END AS is_fixed,
               CASE WHEN b.status IN ('open','in_progress') THEN 1 ELSE 0 END AS is_open,
               CASE WHEN b.resolved_at IS NOT NULL AND b.status IN ('resolved','closed')
                    THEN JULIANDAY(b.resolved_at) - JULIANDAY(b.created_at) END AS days_to_resolve
        FROM bugs b JOIN products p ON p.product_id = b.product_id
        LEFT JOIN components c ON c.component_id = b.component_id
        WHERE b.status NOT IN ('duplicate','wont_fix');
    """)
    con.commit()
    n_sev_missing = int(bugs.severity.isna().sum())
    con.close()
    print(f"\nWrote {out} — {len(bugs):,} bugs, {len(products)} products, {len(comp_df)} components")
    print(f"Status mix: {pd.Series(status).value_counts().to_dict()}")
    if n_sev_missing:
        print(f"NOTE: {n_sev_missing:,} bugs have no recognisable severity; v_defects treats them as S3. "
              "Record this in .knowledge/quirks.md.")
    print("Not loaded (fill in for rate metrics): teams/headcount, releases, product_usage_monthly, components.kloc")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--tracker", default="generic", choices=["jira", "github", "linear", "generic"])
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "imported.db")
    ap.add_argument("--map", action="append", default=[], help="field=Column Name override")
    ap.add_argument("--all-types", action="store_true", help="keep stories/tasks, not just bugs")
    a = ap.parse_args()
    override = dict(x.split("=", 1) for x in a.map)
    run(a.csv, a.tracker, a.out, override, bugs_only=not a.all_types)
