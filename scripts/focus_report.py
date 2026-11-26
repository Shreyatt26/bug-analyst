"""Reference implementation of /focus-report: where should engineering effort go?

    python scripts/focus_report.py                  # writes outputs/<today>-focus-report/
    python scripts/focus_report.py --months 6

Everything goes through helpers.db (guarded + logged), charts through helpers.charts.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers import charts  # noqa: E402
from helpers.checks import freshness, reconcile  # noqa: E402
from helpers.db import QUERY_LOG, ROOT, query  # noqa: E402

USER_FACING = {"Mobile App", "Web Dashboard", "Search", "Payments API"}
WEIGHTS = {"high_sev_rate": 0.35, "trend_pct": 0.20, "tickets": 0.15, "mttr_high_sev": 0.15, "reopen_pct": 0.15}


def df(sql: str, purpose: str) -> pd.DataFrame:
    return query(sql, purpose=purpose).to_dataframe()


def z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd else s * 0


def run(months: int = 12, out: Path | None = None) -> Path:
    out = out or ROOT / "outputs" / f"{date.today().isoformat()}-focus-report"
    out.mkdir(parents=True, exist_ok=True)
    log_start = sum(1 for _ in open(QUERY_LOG)) if QUERY_LOG.exists() else 0

    fresh = freshness()
    W_START = f"DATE('now','start of month','-{months} months')"
    W_END = "DATE('now','start of month')"          # excludes the partial month
    R_START = "DATE('now','start of month','-3 months')"
    P_START = "DATE('now','start of month','-6 months')"
    window = f"created_at >= {W_START} AND created_at < {W_END}"

    # 1. volume & severity
    vol = df(f"""
        SELECT product_name, COUNT(*) AS defects,
               SUM(severity_norm IN ('S1','S2')) AS high_sev,
               SUM(environment='production') AS prod_escapes,
               SUM(customer_tickets) AS tickets,
               SUM(component_name='(untriaged)') AS untriaged
        FROM v_defects WHERE {window} GROUP BY 1""", "focus: volume by product")
    rec = reconcile(f"SELECT COUNT(*) FROM v_defects WHERE {window}",
                    f"SELECT product_name, COUNT(*) FROM v_defects WHERE {window} GROUP BY 1")

    # 2. normalize: per 1k MAU (aggregate to product-month first to avoid fan-out)
    mau = df(f"""
        WITH m AS (SELECT product_id, created_month, SUM(severity_norm IN ('S1','S2')) hs
                   FROM v_defects WHERE {window} GROUP BY 1,2)
        SELECT p.product_name, 1000.0*SUM(m.hs)/SUM(u.monthly_active_users) AS high_sev_per_1k_mau
        FROM m JOIN product_usage_monthly u ON u.product_id=m.product_id AND u.month=m.created_month
        JOIN products p ON p.product_id=m.product_id GROUP BY 1""", "focus: per-MAU rate")
    kloc = df(f"""
        SELECT p.product_name, SUM(c.kloc) AS kloc FROM components c
        JOIN products p USING(product_id) GROUP BY 1""", "focus: product KLOC")

    # 3. trend recent 3 vs prior 3 (product and component)
    trend_sql = lambda grp: f"""
        SELECT {grp}, SUM(created_at >= {R_START}) AS recent_3m,
               SUM(created_at < {R_START}) AS prior_3m
        FROM v_defects WHERE created_at >= {P_START} AND created_at < {W_END}
          AND severity_norm IN ('S1','S2') GROUP BY {grp}"""
    trend = df(trend_sql("product_name"), "focus: high-sev trend by product")
    ctrend = df(trend_sql("product_name, component_name"), "focus: high-sev trend by component")
    for t in (trend, ctrend):
        t["trend_pct"] = 100 * (t.recent_3m - t.prior_3m) / t.prior_3m.where(t.prior_3m > 0)

    # 4. hotspots: density
    dens = df(f"""
        SELECT product_name, component_name, kloc, COUNT(*) AS defects,
               SUM(severity_norm IN ('S1','S2')) AS high_sev,
               COUNT(*)/kloc AS defects_per_kloc
        FROM v_defects WHERE kloc IS NOT NULL AND {window}
        GROUP BY 1,2,3 ORDER BY defects_per_kloc DESC""", "focus: component density")

    # 5. flow
    flow = df(f"""
        SELECT product_name, days_to_resolve, reopened_count, severity_norm
        FROM v_defects WHERE is_fixed=1 AND {window}""", "focus: flow raw (aggregated in pandas)")
    mttr = (flow[flow.severity_norm.isin(["S1", "S2"])].groupby("product_name")
            .days_to_resolve.agg(mttr_high_sev="median", n_fixed_high_sev="size").reset_index())
    reopen = flow.groupby("product_name").reopened_count.apply(lambda s: 100 * (s > 0).mean()) \
        .rename("reopen_pct").reset_index()
    backlog = df("""SELECT product_name, COUNT(*) AS open_now,
                    AVG(JULIANDAY('now')-JULIANDAY(created_at)) AS open_age_days
                    FROM v_defects WHERE is_open=1 GROUP BY 1""", "focus: open backlog")

    # 6. capacity
    cap = df(f"""SELECT p.product_name, t.team_name, t.headcount FROM products p
                 JOIN teams t ON t.team_id=p.owner_team_id""", "focus: team capacity")

    # ---- assemble
    T = (vol.merge(mau, on="product_name", how="left").merge(kloc, on="product_name")
         .merge(trend[["product_name", "recent_3m", "prior_3m", "trend_pct"]], on="product_name")
         .merge(mttr, on="product_name", how="left").merge(reopen, on="product_name", how="left")
         .merge(backlog, on="product_name", how="left").merge(cap, on="product_name"))
    T["high_sev_per_kloc"] = T.high_sev / T.kloc
    T["defects_per_engineer"] = T.defects / T.headcount
    # internal tools have tiny MAU: use per-KLOC for the severity-rate term (see quirks.md)
    T["high_sev_rate"] = z(T.high_sev_per_kloc)
    for k in ["trend_pct", "tickets", "mttr_high_sev", "reopen_pct"]:
        T[f"z_{k}"] = z(T[k].fillna(0))
    T["focus_score"] = (WEIGHTS["high_sev_rate"] * T.high_sev_rate
                        + sum(WEIGHTS[k] * T[f"z_{k}"] for k in ["trend_pct", "tickets", "mttr_high_sev", "reopen_pct"]))
    T = T.sort_values("focus_score", ascending=False)
    T.round(3).to_csv(out / "product_scorecard.csv", index=False)
    dens.round(3).to_csv(out / "component_density.csv", index=False)

    risers = ctrend[(ctrend.recent_3m >= 20) & (ctrend.trend_pct >= 30)].sort_values("trend_pct", ascending=False)

    # monthly high-sev trend for chart
    monthly = df(f"""SELECT created_month, product_name, SUM(severity_norm IN ('S1','S2')) AS high_sev
                     FROM v_defects WHERE {window} GROUP BY 1,2""", "focus: monthly high-sev")
    v32 = df("""SELECT released_at FROM releases r JOIN products p USING(product_id)
                WHERE p.product_name='Payments API' AND version='v3.2'""", "focus: v3.2 date")

    # ---- charts
    top2 = dens.head(2).component_name.tolist()
    top_dens = dens.head(10).assign(label=lambda d: d.product_name + " · " + d.component_name)
    ch1 = charts.bar(top_dens, "label", "defects_per_kloc", path=out / "1_hotspots.png",
                     highlight=[f"{r.product_name} · {r.component_name}" for r in dens.head(2).itertuples()],
                     title=f"{top2[0][:1].upper() + top2[0][1:]} and {top2[1]} are the defect hotspots",
                     subtitle=f"Valid defects per KLOC, top 10 components, last {months} complete months",
                     source="Source: bug DB (v_defects) · excludes duplicates & won't-fix")
    riser_products = trend.sort_values("trend_pct", ascending=False).head(1).product_name.tolist()
    ch2 = charts.line(monthly, "created_month", "high_sev", series="product_name", path=out / "2_trend.png",
                      highlight=riser_products,
                      events={v32.released_at[0]: "Payments v3.2"} if len(v32) else None,
                      title=f"{riser_products[0]} high-severity bugs are up "
                            f"{trend.set_index('product_name').trend_pct[riser_products[0]]:.0f}% in the last 3 months",
                      subtitle="S1+S2 valid defects per month, by product",
                      source="Source: bug DB (v_defects)")
    ch3 = charts.bar(T, "product_name", "focus_score", path=out / "3_focus_score.png",
                     highlight=T.head(2).product_name.tolist(), value_fmt="{:+.2f}",
                     title=f"Prioritise {T.iloc[0].product_name}, then {T.iloc[1].product_name}",
                     subtitle="Focus score = weighted z-scores of severity density, trend, tickets, S1/S2 MTTR, reopens",
                     source="Weights in .knowledge/metrics.md")

    # ---- brief
    def row(r):
        return (f"| {r.product_name} | {r.defects:,} | {r.high_sev:,} | {r.high_sev_per_kloc:.2f} | "
                f"{r.trend_pct:+.0f}% | {r.tickets:,} | {r.mttr_high_sev:.1f} | {r.reopen_pct:.0f}% | "
                f"{r.defects_per_engineer:.0f} | **{r.focus_score:+.2f}** |")
    lines = [
        f"# Engineering focus report — {date.today():%B %d, %Y}",
        "",
        f"Window: last {months} complete months (latest data {fresh['latest']}; partial month excluded). "
        f"Population: valid defects (duplicates / won't-fix excluded). "
        f"Reconciliation: product totals sum to {rec['total']:,} ({'OK' if rec['ok'] else 'MISMATCH'}).",
        "",
        "## Bottom line",
        "",
    ]
    first, second = T.iloc[0], T.iloc[1]
    lines.append(f"1. **{first.product_name}** has the highest focus score ({first.focus_score:+.2f}): "
                 f"high-severity bugs {first.trend_pct:+.0f}% in the last 3 months vs the prior 3, "
                 f"{first.tickets:,} linked customer tickets.")
    lines.append(f"2. **{second.product_name}** is next ({second.focus_score:+.2f}): "
                 f"{second.high_sev_per_kloc:.2f} high-sev bugs per KLOC, reopen rate {second.reopen_pct:.0f}%.")
    worst_reopen = T.sort_values("reopen_pct", ascending=False).iloc[0]
    slowest = T.sort_values("mttr_high_sev", ascending=False).iloc[0]
    lines.append(f"3. Process fixes: **{worst_reopen.product_name}** reopens {worst_reopen.reopen_pct:.0f}% of fixes "
                 f"(fix verification); **{slowest.product_name}** takes a median {slowest.mttr_high_sev:.0f} days "
                 f"to fix S1/S2 bugs with a team of {slowest.headcount} ({slowest.team_name}).")
    lines += ["", "![focus score](3_focus_score.png)", "",
              "## Scorecard", "",
              "| product | defects | high-sev | high-sev / KLOC | high-sev trend (3m) | tickets | S1/S2 median days | reopen | defects / eng | focus |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    lines += [row(r) for r in T.itertuples()]
    lines += ["", "## Hotspot components", "", "![hotspots](1_hotspots.png)", "",
              "| product | component | KLOC | defects | high-sev | defects / KLOC |", "|---|---|---|---|---|---|"]
    lines += [f"| {r.product_name} | {r.component_name} | {r.kloc:.0f} | {r.defects:,} | {r.high_sev:,} | {r.defects_per_kloc:.1f} |"
              for r in dens.head(8).itertuples()]
    lines += ["", "## What's rising", "", "![trend](2_trend.png)", ""]
    if len(risers):
        lines += ["Components with ≥20 high-sev bugs in the last 3 months and ≥30% growth:", "",
                  "| product | component | prior 3m | recent 3m | change |", "|---|---|---|---|---|"]
        lines += [f"| {r.product_name} | {r.component_name} | {r.prior_3m} | {r.recent_3m} | {r.trend_pct:+.0f}% |"
                  for r in risers.itertuples()]
    else:
        lines.append("No component meets the rising threshold.")
    big_raw = T.sort_values("defects", ascending=False).iloc[0]
    lines += ["", "## What looks bad but isn't", "",
              f"**{big_raw.product_name}** has the most bugs in raw count ({big_raw.defects:,}), but only "
              f"{100 * big_raw.high_sev / big_raw.defects:.0f}% are high severity and its high-sev density is "
              f"{big_raw.high_sev_per_kloc:.2f}/KLOC. Its volume reflects size, not a quality problem.",
              "", "## Caveats", "",
              "- KLOC is a current snapshot; densities over long windows are approximate.",
              "- Per-MAU rates are not used for ranking because internal tools have tiny MAU.",
              f"- `found_in_release_id` is a timing marker (latest release at creation) for non-regressions and may name the introducing release for regressions; neither is a verified root cause.",
              f"- Untriaged bugs (no component) in window: {int(vol.untriaged.sum()):,} "
              f"({100 * vol.untriaged.sum() / vol.defects.sum():.1f}%), excluded from component rankings only.",
              "", "## Appendix — queries run", ""]
    with open(QUERY_LOG) as f:
        entries = [json.loads(x) for x in list(f)[log_start:]]
    lines += [f"- `{e['result_sha']}` {e['purpose']} ({e['rows']} rows)" for e in entries if e["purpose"].startswith("focus")]
    (out / "brief.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out}/brief.md + {len([ch1, ch2, ch3])} charts")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    run(a.months)
