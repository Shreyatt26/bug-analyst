"""Standalone Bug Analyst: ask questions in plain English, get SQL-backed answers.

Same brain as the Claude Code version (CLAUDE.md + .knowledge/), wired to the
Anthropic Messages API with tool use, so you can run it without Claude Code —
in a terminal, a cron job, or behind a Slack bot.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...        # or put it in .env (gitignored)
    python agent.py                                   # interactive
    python agent.py "Which component has the worst defect density?"

Tools the model can call (all read-only):
    list_tables, describe_table, run_sql, make_chart, remember, focus_report, write_file
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from helpers import charts
from helpers.db import QueryRejected, connect

ROOT = Path(__file__).resolve().parent
MODEL = os.environ.get("BUG_ANALYST_MODEL", "claude-opus-5-5")
MAX_TURNS = 25
MAX_TOKENS = 8192
SKILLS = ["ask", "release-impact", "focus-report", "validate-results", "chart-style", "sql-patterns", "remember"]
RESULT_ROWS_TO_MODEL = 200

TOOLS = [
    {
        "name": "list_tables",
        "description": "List tables and views in the bug database.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_table",
        "description": "Column names and types for one table or view.",
        "input_schema": {"type": "object", "properties": {"table": {"type": "string"}}, "required": ["table"]},
    },
    {
        "name": "run_sql",
        "description": (
            "Run ONE read-only SELECT/WITH query and get the result as a markdown table. "
            "Aggregate in SQL. Results over 200 rows are truncated for you. "
            "Always give a short purpose. Optionally save the full result as CSV for charting."),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "purpose": {"type": "string", "description": "why you are running this query"},
                "save_as": {"type": "string", "description": "optional name to keep the result for make_chart"},
            },
            "required": ["sql", "purpose"],
        },
    },
    {
        "name": "make_chart",
        "description": (
            "Chart a saved query result in the house style (gray first, one highlight). "
            "kind=bar for ranked categories, line for time series (x is a date column)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "save_as name from run_sql"},
                "kind": {"type": "string", "enum": ["bar", "line"]},
                "x": {"type": "string"}, "y": {"type": "string"},
                "series": {"type": "string", "description": "line only: column to split lines by"},
                "title": {"type": "string", "description": "action title stating the finding"},
                "subtitle": {"type": "string"},
                "highlight": {"type": "array", "items": {"type": "string"}},
                "events": {"type": "object", "description": "line only: {date: label} markers"},
            },
            "required": ["result", "kind", "x", "y", "title"],
        },
    },
    {
        "name": "focus_report",
        "description": (
            "Run the standard company-wide focus report (products, hotspots, trends, flow, capacity, "
            "focus score). Writes brief.md, charts and CSVs to outputs/ and returns the brief text."),
        "input_schema": {"type": "object", "properties": {"months": {"type": "integer", "description": "window in complete months, default 12"}}},
    },
    {
        "name": "write_file",
        "description": "Save a text file (e.g. brief.md, analysis.py) into today's outputs/<date>-agent/ folder. Name only, no paths.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}},
                         "required": ["name", "content"]},
    },
    {
        "name": "remember",
        "description": "Save a correction / business rule the user stated to .knowledge/corrections.md.",
        "input_schema": {
            "type": "object",
            "properties": {"rule": {"type": "string"}, "applies_to": {"type": "string"}},
            "required": ["rule", "applies_to"],
        },
    },
]


def build_system_prompt() -> str:
    parts = [(ROOT / "CLAUDE.md").read_text()]
    for name in ["schema.md", "metrics.md", "quirks.md", "corrections.md", "example_queries.sql"]:
        p = ROOT / ".knowledge" / name
        if p.exists():
            parts.append(f"\n\n<knowledge file=\"{name}\">\n{p.read_text()}\n</knowledge>")
    for name in SKILLS:
        p = ROOT / ".claude" / "skills" / name / "SKILL.md"
        if p.exists():
            body = re.sub(r"\A---\n.*?\n---\n", "", p.read_text(), flags=re.S)
            parts.append(f"\n\n<skill name=\"{name}\">\n{body}\n</skill>")
    con = connect()
    parts.append(
        f"\n\nYou are running as a standalone agent (not Claude Code). Use your tools instead of shell "
        f"commands; where a skill mentions scripts or files, use the matching tool (run_sql, make_chart, "
        f"focus_report, write_file). Active source: {con.name} ({con.dialect}). Today is {date.today().isoformat()}. "
        f"Save charts with make_chart; they are written to outputs/. Keep answers tight: finding, "
        f"table, what it means for engineering effort, caveats, then the SQL.")
    return "".join(parts)


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines); existing environment variables win."""
    p = ROOT / ".env"
    if p.exists():
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class Tools:
    def __init__(self, out_dir: Path):
        self.con = connect()
        self.saved = {}
        self.out_dir = out_dir

    def __call__(self, name: str, args: dict) -> str:
        try:
            return getattr(self, name)(**args)
        except QueryRejected as e:
            return f"REJECTED by guardrail: {e}"
        except Exception as e:  # surface errors to the model so it can fix its SQL
            return f"ERROR: {type(e).__name__}: {e}"

    def list_tables(self):
        return "\n".join(f"{t}\t{n}" for n, t in self.con.tables())

    def describe_table(self, table):
        return "\n".join(f"{n}\t{t}" for n, t in self.con.columns(table))

    def run_sql(self, sql, purpose, save_as=None):
        res = self.con.query(sql, purpose=purpose)
        if save_as:
            self.saved[save_as] = res.to_dataframe()
        md = res.to_markdown(RESULT_ROWS_TO_MODEL)
        return f"{md}\n\n({len(res.rows)} rows, sha {res.meta.get('result_sha')})"

    def make_chart(self, result, kind, x, y, title, subtitle=None, highlight=None, series=None, events=None):
        if result not in self.saved:
            return f"ERROR: no saved result named {result!r}. Use run_sql with save_as first."
        df = self.saved[result]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        path = self.out_dir / f"{slug}.png"
        if kind == "bar":
            charts.bar(df, x, y, title=title, subtitle=subtitle, highlight=highlight, path=path)
        else:
            charts.line(df, x, y, title=title, subtitle=subtitle, highlight=highlight,
                        series=series, events=events, path=path)
        return f"saved chart: {path.relative_to(ROOT)}"

    def focus_report(self, months=12):
        sys.path.insert(0, str(ROOT / "scripts"))
        import focus_report as fr
        out = fr.run(int(months), out=self.out_dir / "focus-report")
        return f"saved to {out.relative_to(ROOT)}\n\n{(out / 'brief.md').read_text()}"

    def write_file(self, name, content):
        if Path(name).name != name or name.startswith("."):
            return "ERROR: name must be a plain filename (no paths, not hidden)."
        if Path(name).suffix not in {".md", ".py", ".sql", ".csv", ".txt"}:
            return "ERROR: allowed extensions: .md .py .sql .csv .txt"
        path = self.out_dir / name
        path.write_text(content)
        return f"saved {path.relative_to(ROOT)}"

    def remember(self, rule, applies_to):
        p = ROOT / ".knowledge" / "corrections.md"
        lines = p.read_text().splitlines()
        idx = next(i for i, ln in enumerate(lines) if ln.startswith("|---")) + 1
        lines.insert(idx, f"| {date.today().isoformat()} | {rule} | {applies_to} |")
        p.write_text("\n".join(lines) + "\n")
        return "saved to .knowledge/corrections.md"


class Analyst:
    def __init__(self, client=None, model: str = MODEL, verbose: bool = True):
        if client is None:
            _load_dotenv()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit("ANTHROPIC_API_KEY is not set. Export it or put it in .env (see README).")
            import anthropic  # imported lazily so the tool layer works without it
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.verbose = verbose
        self.system = build_system_prompt()
        self.messages: list[dict] = []
        self.tools = Tools(ROOT / "outputs" / f"{date.today().isoformat()}-agent")
        self.tools.out_dir.mkdir(parents=True, exist_ok=True)

    def ask(self, question: str) -> str:
        self.messages.append({"role": "user", "content": question})
        for _ in range(MAX_TURNS):
            resp = self.client.messages.create(
                model=self.model, max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS, messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                if self.verbose:
                    shown = block.input.get("purpose") or block.input.get("title") or json.dumps(block.input)[:80]
                    print(f"  · {block.name}: {shown}", file=sys.stderr)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": self.tools(block.name, dict(block.input))})
            self.messages.append({"role": "user", "content": results})
        return "Stopped: too many steps. Try a narrower question."


def main():
    ap = argparse.ArgumentParser(description="Ask the Bug Analyst a question (omit it for interactive mode).")
    ap.add_argument("question", nargs="*")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--quiet", action="store_true", help="hide the tool-call progress lines")
    a = ap.parse_args()
    analyst = Analyst(model=a.model, verbose=not a.quiet)
    if a.question:
        print(analyst.ask(" ".join(a.question)))
        return
    print("Bug Analyst — ask about bugs across products. Ctrl-D to quit.\n")
    while True:
        try:
            q = input("you> ").strip()
        except EOFError:
            break
        if q:
            print("\n" + analyst.ask(q) + "\n")


if __name__ == "__main__":
    main()
