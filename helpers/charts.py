"""Chart helpers with an opinionated 'gray first, one highlight' style.

Rules baked in (see .claude/skills/chart-style/SKILL.md):
  * Title states the finding (an action title), subtitle states metric + period + filter.
  * Everything is gray except what the reader should look at.
  * No chart junk: no top/right spines, light grid on the value axis only.
  * Always cite the source query sha in the footer so numbers are traceable.

    from helpers.charts import bar, line, heatmap
    bar(df, x="component", y="bugs_per_kloc", highlight=["offline-sync"],
        title="Offline-sync has 3x the defect density of any other component",
        subtitle="Valid defects per KLOC, last 12 months", path="outputs/density.png")
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

GRAY = "#B8B8B8"
DARK = "#333333"
MUTED = "#6B6B6B"
HIGHLIGHT = "#D1495B"     # one accent color
HIGHLIGHT_2 = "#2E86AB"   # second accent only when comparing two things

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": "#CCCCCC",
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})


def _frame(ax, title: str, subtitle: str | None, source: str | None, fig):
    fig.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=DARK, ha="left", va="top")
    if subtitle:
        fig.text(0.01, 0.915, subtitle, fontsize=9.5, color=MUTED, ha="left", va="top")
    if source:
        fig.text(0.01, 0.01, source, fontsize=7.5, color="#999999", ha="left", va="bottom")
    fig.subplots_adjust(top=0.84, bottom=0.12)


def _save(fig, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def bar(df, x: str, y: str, title: str, path: str | Path, subtitle: str | None = None,
        highlight: Iterable | None = None, horizontal: bool = True, value_fmt: str = "{:,.1f}",
        source: str | None = None, sort: bool = True):
    d = df.sort_values(y, ascending=horizontal) if sort else df
    hl = set(highlight or [])
    colors = [HIGHLIGHT if v in hl else GRAY for v in d[x]]
    fig, ax = plt.subplots(figsize=(8, max(3.0, 0.38 * len(d) + 1.4)) if horizontal else (9, 4.5))
    labels = d[x].astype(str)
    if horizontal:
        bars = ax.barh(labels, d[y], color=colors)
        ax.xaxis.grid(True, color="#EEEEEE"); ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
        ax.margins(x=0.12)  # room for value labels at either end
        for b, v, c in zip(bars, d[y], colors):
            neg = v < 0
            ax.text(b.get_width(), b.get_y() + b.get_height() / 2,
                    (value_fmt.format(v) + " ") if neg else (" " + value_fmt.format(v)),
                    va="center", ha="right" if neg else "left", fontsize=8.5, color=DARK if c == HIGHLIGHT else MUTED,
                    fontweight="bold" if c == HIGHLIGHT else "normal")
    else:
        bars = ax.bar(labels, d[y], color=colors)
        ax.yaxis.grid(True, color="#EEEEEE"); ax.set_axisbelow(True)
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    for lbl in (ax.get_yticklabels() if horizontal else ax.get_xticklabels()):
        if lbl.get_text() in {str(h) for h in hl}:
            lbl.set_color(DARK); lbl.set_fontweight("bold")
    _frame(ax, title, subtitle, source, fig)
    return _save(fig, path)


def line(df, x: str, y: str, title: str, path: str | Path, series: str | None = None,
         subtitle: str | None = None, highlight: Iterable | None = None,
         events: dict | None = None, source: str | None = None, ylabel: str | None = None):
    """events: {x_value: "label"} drawn as dashed vertical markers (e.g. releases)."""
    import pandas as pd
    fig, ax = plt.subplots(figsize=(9, 4.6))
    d = df.copy()
    d[x] = pd.to_datetime(d[x])
    hl = set(highlight or [])
    groups = d.groupby(series) if series else [(None, d)]
    ends = []
    for name, g in groups:
        g = g.sort_values(x)
        is_hl = (name in hl) or (series is None)
        ax.plot(g[x], g[y], color=HIGHLIGHT if is_hl else GRAY, lw=2.4 if is_hl else 1.3,
                zorder=3 if is_hl else 2)
        if name is not None:
            ends.append([float(g[y].iloc[-1]), g[x].iloc[-1], name, is_hl])
    # end-of-line labels, nudged apart so they don't overlap
    if ends:
        lo, hi = ax.get_ylim()
        gap = (hi - lo) * 0.055
        ends.sort(key=lambda e: e[0])
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
        for yv, xv, name, is_hl in ends:
            ax.text(xv, yv, f"  {name}", va="center", fontsize=8.5,
                    color=DARK if is_hl else MUTED, fontweight="bold" if is_hl else "normal")
    for xv, label in (events or {}).items():
        xv = pd.to_datetime(xv)
        ax.axvline(xv, color=MUTED, ls="--", lw=0.9)
        ax.text(xv, ax.get_ylim()[1], f" {label}", fontsize=8, color=MUTED, va="top")
    ax.yaxis.grid(True, color="#EEEEEE"); ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel)
    _frame(ax, title, subtitle, source, fig)
    return _save(fig, path)


def heatmap(pivot, title: str, path: str | Path, subtitle: str | None = None,
            source: str | None = None, fmt: str = "{:.0f}"):
    """pivot: DataFrame (rows x cols) of numbers, e.g. product x month."""
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("hl", ["#F7F7F7", "#F2B8BF", HIGHLIGHT])
    fig, ax = plt.subplots(figsize=(min(14, 1.2 + 0.55 * pivot.shape[1]), 1.2 + 0.45 * pivot.shape[0]))
    vals = pivot.values.astype(float)
    ax.imshow(vals, aspect="auto", cmap=cmap)
    ax.set_xticks(range(pivot.shape[1]), [str(c)[:7] for c in pivot.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(pivot.shape[0]), [str(i) for i in pivot.index], fontsize=9)
    hi = np.nanpercentile(vals, 85) if np.isfinite(vals).any() else 0
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            if np.isfinite(vals[i, j]):
                ax.text(j, i, fmt.format(vals[i, j]), ha="center", va="center", fontsize=7,
                        color="white" if vals[i, j] >= hi else MUTED)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    _frame(ax, title, subtitle, source, fig)
    return _save(fig, path)
