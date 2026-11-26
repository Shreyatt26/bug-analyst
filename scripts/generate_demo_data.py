"""Generate a synthetic multi-product bug-tracking database (SQLite).

The data is fictional ("Acme Cloud") but shaped like a real Jira/GitHub-issues
export, with realistic quirks and a few planted patterns so you can check that
the analyst finds them:

  1. Payments API  - regression spike in the `refunds` component after v3.2 (Jun 2026)
  2. Mobile App    - `offline-sync` has by far the highest defect density (bugs / KLOC)
  3. Search        - high reopen rate: fixes don't stick
  4. Web Dashboard - most bugs in raw count, but mostly low severity and low per-user rate
  5. Admin Console - few bugs, but very slow time-to-resolve (understaffed team)

Data quirks (documented in .knowledge/quirks.md):
  * Bugs created before 2025-01-01 were migrated from a legacy tracker and use
    severity labels 'Critical'/'Major'/'Minor'/'Trivial' instead of S1-S4.
  * ~6% of bugs have no component (untriaged) -> component_id IS NULL.
  * status 'duplicate' and 'wont_fix' are not real defects.
  * resolved_at is NULL for open / in_progress bugs.

Usage:  python scripts/generate_demo_data.py [--out data/bugs.db] [--seed 7]
"""
from __future__ import annotations

import argparse
import math
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

# The demo is anchored so that it always ends "yesterday": every fixed date below
# is shifted by whole months relative to the original design date (2026-11-20).
DESIGN_END = date(2026, 11, 20)


def shift_months(d: date, k: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + k, 12)
    return date(y, m + 1, min(d.day, 28))


def anchor(as_of: date) -> dict:
    end = as_of - timedelta(days=1)
    k = (end.year * 12 + end.month) - (DESIGN_END.year * 12 + DESIGN_END.month)
    return {
        "START": shift_months(date(2024, 7, 1), k),
        "END": end,
        "V32": shift_months(date(2026, 6, 9), k),          # Payments API v3.2 ships
        "SPIKE_LAST_MONTH": shift_months(date(2026, 9, 1), k),
        "LEGACY_CUTOFF": shift_months(date(2025, 1, 1), k),  # legacy severity labels before this
    }


START = END = None  # set in build()

TEAMS = [
    # team_id, name, headcount
    (1, "Payments Eng", 9),
    (2, "Mobile Eng", 11),
    (3, "Search & Discovery", 7),
    (4, "Web Platform", 14),
    (5, "Internal Tools", 3),
    (6, "Data Platform", 8),
]

PRODUCTS = [
    # id, name, platform, owner_team, launched, base_mau
    (1, "Payments API", "backend", 1, "2022-03-01", 42000),
    (2, "Mobile App", "ios/android", 2, "2021-09-15", 310000),
    (3, "Search", "backend", 3, "2023-01-10", 260000),
    (4, "Web Dashboard", "web", 4, "2020-05-01", 520000),
    (5, "Admin Console", "web", 5, "2022-11-01", 1800),
    (6, "Data Pipeline", "backend", 6, "2023-06-01", 900),
]

# product_id -> [(component, kloc, relative bug weight)]
COMPONENTS = {
    1: [("checkout", 38, 1.0), ("refunds", 14, 0.7), ("ledger", 52, 0.6), ("webhooks", 11, 0.5), ("fraud-rules", 22, 0.4)],
    2: [("offline-sync", 9, 1.6), ("auth", 12, 0.6), ("feed-ui", 41, 1.0), ("push-notifications", 8, 0.5), ("payments-sdk", 15, 0.5)],
    3: [("indexer", 33, 1.0), ("ranking", 27, 0.9), ("query-parser", 12, 0.7), ("autocomplete", 9, 0.6)],
    4: [("reports", 64, 1.0), ("settings", 30, 0.7), ("navigation", 25, 0.8), ("charts", 48, 0.9), ("billing-pages", 20, 0.5), ("i18n", 18, 0.6)],
    5: [("user-mgmt", 16, 1.0), ("audit-log", 9, 0.6), ("permissions", 13, 0.9)],
    6: [("ingest", 45, 1.0), ("transforms", 60, 0.9), ("scheduler", 18, 0.6)],
}

# bugs per month baseline per product
BASE_MONTHLY = {1: 34, 2: 70, 3: 40, 4: 105, 5: 9, 6: 26}

# severity mix per product (S1..S4)
SEV_MIX = {
    1: [0.10, 0.30, 0.40, 0.20],
    2: [0.06, 0.28, 0.44, 0.22],
    3: [0.04, 0.22, 0.50, 0.24],
    4: [0.01, 0.09, 0.45, 0.45],   # lots of cosmetic bugs
    5: [0.05, 0.30, 0.45, 0.20],
    6: [0.08, 0.30, 0.42, 0.20],
}
LEGACY_SEV = {"S1": "Critical", "S2": "Major", "S3": "Minor", "S4": "Trivial"}

# median days to resolve by severity, multiplied per product (team capacity)
MTTR_BASE = {"S1": 2.0, "S2": 7.0, "S3": 18.0, "S4": 35.0}
MTTR_MULT = {1: 1.0, 2: 1.1, 3: 0.9, 4: 0.8, 5: 3.2, 6: 1.2}

REOPEN_P = {1: 0.07, 2: 0.09, 3: 0.27, 4: 0.06, 5: 0.08, 6: 0.10}

SOURCES = [("customer_report", 0.28), ("qa", 0.25), ("automated_test", 0.22), ("monitoring", 0.15), ("internal", 0.10)]

TITLE_BITS = {
    "checkout": ["Checkout times out on 3DS challenge", "Duplicate charge on retry", "Currency rounding error at checkout"],
    "refunds": ["Partial refund amount incorrect", "Refund webhook not fired", "Refund stuck in pending", "Refund applied twice after v3.2 migration"],
    "ledger": ["Ledger balance drift", "Reconciliation job fails on month-end"],
    "webhooks": ["Webhook signature mismatch", "Webhook retries exhaust too fast"],
    "fraud-rules": ["False positive on fraud rule FR-12", "Rule editor loses changes"],
    "offline-sync": ["Data loss when reconnecting offline", "Sync conflict overwrites newer edit", "Crash on sync after airplane mode", "Offline queue never drains"],
    "auth": ["Session expires early on Android", "Biometric login loop"],
    "feed-ui": ["Feed jumps on scroll", "Images flicker in feed", "Empty state shown with items"],
    "push-notifications": ["Duplicate push notifications", "Push opens wrong screen"],
    "payments-sdk": ["SDK crash on card scan", "Apple Pay sheet not dismissed"],
    "indexer": ["Stale results after update", "Indexer OOM on large tenants"],
    "ranking": ["Irrelevant top result", "Ranking regression for exact matches"],
    "query-parser": ["Quoted phrase ignored", "Special characters break query"],
    "autocomplete": ["Autocomplete lags", "Suggestions show deleted items"],
    "reports": ["Report export truncated", "Totals row misaligned", "Report filter resets"],
    "settings": ["Toggle doesn't persist", "Settings page typo"],
    "navigation": ["Back button loses state", "Breadcrumb wrong on deep link"],
    "charts": ["Tooltip clipped", "Legend overlaps chart", "Wrong axis label"],
    "billing-pages": ["Invoice PDF missing logo", "Plan price shows old value"],
    "i18n": ["Untranslated string in German", "RTL layout broken"],
    "user-mgmt": ["Invite email not sent", "Bulk deactivate times out"],
    "audit-log": ["Audit log missing actor", "Audit export slow"],
    "permissions": ["Role change requires relogin", "Custom role can't be deleted"],
    "ingest": ["Ingest drops late events", "Schema drift breaks ingest"],
    "transforms": ["Transform null handling wrong", "Job retries duplicate rows"],
    "scheduler": ["Cron skipped at DST change", "Scheduler double-runs job"],
}

RELEASE_CADENCE_DAYS = {1: 28, 2: 14, 3: 21, 4: 14, 5: 45, 6: 30}


def month_iter(start: date, end: date):
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def weighted(rng: random.Random, items):
    r, acc = rng.random(), 0.0
    for val, w in items:
        acc += w
        if r <= acc:
            return val
    return items[-1][0]


def build(out: Path, seed: int, as_of: date | None = None) -> dict:
    global START, END
    A = anchor(as_of or date.today())
    START, END = A["START"], A["END"]
    rng = random.Random(seed)
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_name TEXT NOT NULL,
            headcount INTEGER NOT NULL
        );
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            platform TEXT,
            owner_team_id INTEGER REFERENCES teams(team_id),
            launched_at DATE
        );
        CREATE TABLE components (
            component_id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            component_name TEXT NOT NULL,
            kloc REAL            -- thousands of lines of code, current snapshot
        );
        CREATE TABLE releases (
            release_id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            version TEXT NOT NULL,
            released_at DATE NOT NULL
        );
        CREATE TABLE bugs (
            bug_id INTEGER PRIMARY KEY,
            bug_key TEXT NOT NULL,            -- tracker key e.g. PAY-1234
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            component_id INTEGER REFERENCES components(component_id),  -- NULL = untriaged
            title TEXT,
            severity TEXT,                    -- S1..S4 (legacy: Critical/Major/Minor/Trivial)
            priority TEXT,                    -- P0..P3
            status TEXT NOT NULL,             -- open, in_progress, resolved, closed, wont_fix, duplicate
            source TEXT,                      -- customer_report, qa, automated_test, monitoring, internal
            environment TEXT,                 -- production, staging, dev
            is_regression INTEGER NOT NULL DEFAULT 0,
            found_in_release_id INTEGER REFERENCES releases(release_id),
            fixed_in_release_id INTEGER REFERENCES releases(release_id),
            assignee_team_id INTEGER REFERENCES teams(team_id),
            reopened_count INTEGER NOT NULL DEFAULT 0,
            customer_tickets INTEGER NOT NULL DEFAULT 0,   -- linked support tickets
            created_at TIMESTAMP NOT NULL,
            resolved_at TIMESTAMP                          -- NULL while open
        );
        CREATE TABLE product_usage_monthly (
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            month DATE NOT NULL,
            monthly_active_users INTEGER,
            deploys INTEGER,
            PRIMARY KEY (product_id, month)
        );
        """
    )
    cur.executemany("INSERT INTO teams VALUES (?,?,?)", TEAMS)
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", [p[:5] for p in PRODUCTS])

    comp_rows, comp_lookup = [], {}
    cid = 1
    for pid, comps in COMPONENTS.items():
        for name, kloc, w in comps:
            comp_rows.append((cid, pid, name, kloc))
            comp_lookup.setdefault(pid, []).append((cid, name, w))
            cid += 1
    cur.executemany("INSERT INTO components VALUES (?,?,?,?)", comp_rows)

    # releases
    rel_rows, rel_by_product = [], {}
    rid = 1
    pinned = A["V32"]  # Payments API v3.2 ships here
    for pid, *_ in PRODUCTS:
        dates = []
        d = START - timedelta(days=rng.randint(5, 20))
        while d <= END:
            dates.append(d)
            d += timedelta(days=RELEASE_CADENCE_DAYS[pid] + rng.randint(-3, 3))
        if pid == 1:
            idx = min(range(len(dates)), key=lambda i: abs((dates[i] - pinned).days))
            dates[idx] = pinned
            offset = 32 - idx          # so that dates[idx] is labelled v3.2
        else:
            idx, offset = 0, rng.randint(10, 40)
        for i, d in enumerate(dates):
            n = i + offset
            version = f"v{n // 10}.{n % 10}"
            rel_rows.append((rid, pid, version, d.isoformat()))
            rel_by_product.setdefault(pid, []).append((rid, d, version))
            rid += 1
    cur.executemany("INSERT INTO releases VALUES (?,?,?,?)", rel_rows)

    # usage
    usage_rows = []
    months = list(month_iter(START, END))
    for pid, _n, _p, _t, _l, mau in PRODUCTS:
        for i, m in enumerate(months):
            growth = (1 + 0.012) ** i
            usage_rows.append((pid, m.isoformat(), int(mau * growth * rng.uniform(0.96, 1.04)),
                               int(30 / RELEASE_CADENCE_DAYS[pid] * 6 * rng.uniform(0.7, 1.3))))
    cur.executemany("INSERT INTO product_usage_monthly VALUES (?,?,?,?)", usage_rows)

    prefix = {1: "PAY", 2: "MOB", 3: "SRCH", 4: "WEB", 5: "ADM", 6: "DATA"}
    key_counter = {pid: 100 for pid in prefix}
    bug_rows = []
    bid = 1
    spike_start = A["V32"]

    for m in months:
        for pid, *_ in PRODUCTS:
            lam = BASE_MONTHLY[pid] * (1 + 0.004 * months.index(m))
            # seasonal wobble
            lam *= 1 + 0.08 * math.sin(months.index(m) / 2.0)
            n = max(0, int(rng.gauss(lam, math.sqrt(lam))))
            extra_refunds = 0
            if pid == 1 and spike_start <= m.replace(day=28) and m <= A["SPIKE_LAST_MONTH"]:
                extra_refunds = int(rng.gauss(38, 6))  # v3.2 regression spike
            for k in range(n + extra_refunds):
                is_spike = k >= n
                day = rng.randint(1, 28)
                created = datetime(m.year, m.month, day, rng.randint(0, 23), rng.randint(0, 59))
                if created.date() > END:
                    continue
                if is_spike and created.date() < spike_start:
                    created = datetime(spike_start.year, spike_start.month, rng.randint(min(spike_start.day + 1, 28), 28), rng.randint(0, 23), rng.randint(0, 59))

                comps = comp_lookup[pid]
                if is_spike:
                    comp = next(c for c in comps if c[1] == "refunds")
                else:
                    comp = weighted(rng, [(c, c[2] / sum(x[2] for x in comps)) for c in comps])
                comp_id, comp_name = comp[0], comp[1]

                sev = weighted(rng, list(zip(["S1", "S2", "S3", "S4"], SEV_MIX[pid])))
                if is_spike:
                    sev = weighted(rng, [("S1", 0.25), ("S2", 0.5), ("S3", 0.25)])
                if pid == 2 and comp_name == "offline-sync":
                    sev = weighted(rng, [("S1", 0.15), ("S2", 0.45), ("S3", 0.3), ("S4", 0.1)])
                prio = {"S1": "P0", "S2": "P1", "S3": "P2", "S4": "P3"}[sev]
                if rng.random() < 0.15:
                    prio = rng.choice(["P0", "P1", "P2", "P3"])

                source = weighted(rng, SOURCES)
                if is_spike:
                    source = weighted(rng, [("customer_report", 0.6), ("monitoring", 0.3), ("qa", 0.1)])
                env = weighted(rng, [("production", 0.55), ("staging", 0.30), ("dev", 0.15)])
                if source in ("customer_report", "monitoring"):
                    env = "production"

                is_reg = 1 if (is_spike or rng.random() < 0.12) else 0

                rels = rel_by_product[pid]
                found = [r for r in rels if r[1] <= created.date()]
                found_rid = found[-1][0] if found else rels[0][0]
                if is_spike:
                    found_rid = next(r[0] for r in rels if r[2] == "v3.2")

                # status / resolution
                age_days = (END - created.date()).days
                mttr = MTTR_BASE[sev] * MTTR_MULT[pid] * rng.lognormvariate(0, 0.7)
                status_roll = rng.random()
                resolved_at = None
                if status_roll < 0.035:
                    status = "duplicate"
                    resolved_at = created + timedelta(days=rng.uniform(0.1, 3))
                elif status_roll < 0.065:
                    status = "wont_fix"
                    resolved_at = created + timedelta(days=rng.uniform(1, 30))
                elif mttr < age_days:
                    status = "closed" if rng.random() < 0.7 else "resolved"
                    resolved_at = created + timedelta(days=mttr)
                else:
                    status = "in_progress" if rng.random() < 0.4 else "open"

                reopened = 0
                if status in ("closed", "resolved"):
                    p = REOPEN_P[pid] * (1.8 if comp_name in ("ranking", "indexer") else 1.0)
                    while rng.random() < p and reopened < 4:
                        reopened += 1
                        resolved_at += timedelta(days=rng.uniform(2, 12))
                    if resolved_at.date() > END:
                        status, resolved_at = "in_progress", None

                if resolved_at and resolved_at.date() > END:   # can't be resolved in the future
                    status, resolved_at = "open", None

                fixed_rid = None
                if resolved_at and status in ("closed", "resolved"):
                    later = [r for r in rels if r[1] >= resolved_at.date()]
                    fixed_rid = later[0][0] if later else None

                tickets = 0
                if source == "customer_report":
                    tickets = max(1, int(rng.expovariate(1 / ({"S1": 14, "S2": 6, "S3": 2, "S4": 1}[sev]))))
                if is_spike:
                    tickets = int(tickets * 2.5) + rng.randint(1, 8)

                severity_out = sev
                if created.date() < A["LEGACY_CUTOFF"]:
                    severity_out = LEGACY_SEV[sev]

                if rng.random() < 0.06 and not is_spike:
                    comp_id_out = None  # untriaged
                else:
                    comp_id_out = comp_id

                title = rng.choice(TITLE_BITS[comp_name])
                if is_spike:
                    title = rng.choice(["Refund applied twice after v3.2 migration", "Partial refund amount incorrect",
                                        "Refund stuck in pending", "Refund webhook not fired"])

                key_counter[pid] += 1
                bug_rows.append((
                    bid, f"{prefix[pid]}-{key_counter[pid]}", pid, comp_id_out, title, severity_out, prio, status,
                    source, env, is_reg, found_rid, fixed_rid, PRODUCTS[pid - 1][3], reopened, tickets,
                    created.isoformat(sep=" "), resolved_at.isoformat(sep=" ", timespec="minutes") if resolved_at else None,
                ))
                bid += 1

    cur.executemany("INSERT INTO bugs VALUES (" + ",".join("?" * 18) + ")", bug_rows)

    # Analyst-friendly views: canonical definitions live here AND in .knowledge/metrics.md
    cur.executescript(
        """
        CREATE VIEW v_defects AS
        SELECT b.*,
               CASE b.severity
                    WHEN 'Critical' THEN 'S1' WHEN 'Major' THEN 'S2'
                    WHEN 'Minor' THEN 'S3' WHEN 'Trivial' THEN 'S4'
                    ELSE b.severity END                              AS severity_norm,
               p.product_name,
               COALESCE(c.component_name, '(untriaged)')            AS component_name,
               c.kloc,
               DATE(b.created_at, 'start of month')                 AS created_month,
               CASE WHEN b.status IN ('resolved','closed') THEN 1 ELSE 0 END AS is_fixed,
               CASE WHEN b.status IN ('open','in_progress') THEN 1 ELSE 0 END AS is_open,
               CASE WHEN b.resolved_at IS NOT NULL AND b.status IN ('resolved','closed')
                    THEN JULIANDAY(b.resolved_at) - JULIANDAY(b.created_at) END AS days_to_resolve
        FROM bugs b
        JOIN products p ON p.product_id = b.product_id
        LEFT JOIN components c ON c.component_id = b.component_id
        WHERE b.status NOT IN ('duplicate', 'wont_fix');
        """
    )
    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM bugs").fetchone()[0]
    con.close()
    print(f"Wrote {out} with {n:,} bugs, {len(rel_rows)} releases, {len(comp_rows)} components")
    print(f"  data range {START} .. {END}; Payments v3.2 shipped {A['V32']}; "
          f"legacy severity labels before {A['LEGACY_CUTOFF']}")
    return A


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/bugs.db")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None,
                    help="pretend today is this date (default: today)")
    a = ap.parse_args()
    build(Path(a.out), a.seed, a.as_of)
