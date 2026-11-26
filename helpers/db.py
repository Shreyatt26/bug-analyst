"""Read-only query runner with guardrails and provenance logging.

Every number the analyst reports must come from a query run through here, so
that it is logged in outputs/query_log.jsonl and can be traced back.

CLI:
    python -m helpers.db tables
    python -m helpers.db describe bugs
    python -m helpers.db query "SELECT product_name, COUNT(*) FROM v_defects GROUP BY 1"
    python -m helpers.db query --csv outputs/x.csv "SELECT ..."
    python -m helpers.db query --file outputs/q1.sql
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data_sources.yaml"
QUERY_LOG = ROOT / "outputs" / "query_log.jsonl"

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "merge", "upsert",
    "attach", "detach", "pragma", "vacuum", "reindex", "grant", "revoke", "copy", "call",
    "exec", "execute", "install", "begin", "commit", "rollback", "savepoint",
}
ALLOWED_START = {"select", "with", "explain", "values"}


class QueryRejected(ValueError):
    """Raised when a query fails the read-only guardrails."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    elapsed_ms: int
    sql: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self, max_rows: int = 50) -> str:
        if not self.columns:
            return "(no columns)"
        def fmt(v):
            if v is None:
                return "NULL"
            if isinstance(v, float):
                return f"{v:,.2f}"
            if isinstance(v, int):
                return f"{v:,}"
            return str(v).replace("|", "\\|")
        out = ["| " + " | ".join(self.columns) + " |", "|" + "---|" * len(self.columns)]
        for r in self.rows[:max_rows]:
            out.append("| " + " | ".join(fmt(v) for v in r) + " |")
        extra = len(self.rows) - max_rows
        if extra > 0:
            out.append(f"... {extra} more rows")
        if self.truncated:
            out.append("(result truncated at the max_rows guardrail - aggregate further)")
        return "\n".join(out)

    def to_dataframe(self):
        import pandas as pd
        return pd.DataFrame(self.rows, columns=self.columns)

    def to_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_dataframe().to_csv(path, index=False)
        return path


# --------------------------------------------------------------------------- guardrails

def _strip_literals_and_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)       # string literals
    sql = re.sub(r'"(?:[^"]|"")*"', '""', sql)       # quoted identifiers
    return sql


def check_read_only(sql: str) -> str:
    """Return the cleaned SQL or raise QueryRejected."""
    if not sql or not sql.strip():
        raise QueryRejected("Empty query.")
    bare = _strip_literals_and_comments(sql).strip().rstrip(";").strip()
    if ";" in bare:
        raise QueryRejected("Only one statement per query is allowed.")
    words = re.findall(r"[a-zA-Z_]+", bare.lower())
    if not words or words[0] not in ALLOWED_START:
        raise QueryRejected(f"Only SELECT / WITH queries are allowed (got '{words[0] if words else ''}').")
    bad = sorted(set(words) & FORBIDDEN)
    if bad:
        raise QueryRejected(f"Query contains forbidden keyword(s): {', '.join(bad)}.")
    return sql.strip().rstrip(";")


# --------------------------------------------------------------------------- connections

def _expand_env(value: str) -> str:
    def sub(m):
        var = m.group(1)
        if var not in os.environ:
            raise RuntimeError(f"Environment variable {var} is not set (referenced in data_sources.yaml).")
        return os.environ[var]
    return re.sub(r"\$\{([A-Z0-9_]+)\}", sub, value)


def load_config(path: Path = CONFIG) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_source(name: str | None = None) -> tuple[str, dict, dict]:
    cfg = load_config()
    name = name or os.environ.get("BUG_ANALYST_SOURCE") or cfg.get("default")
    if name not in cfg.get("sources", {}):
        raise RuntimeError(f"Unknown data source '{name}'. Defined: {list(cfg.get('sources', {}))}")
    return name, cfg["sources"][name], cfg.get("guardrails", {})


class Connection:
    """Thin adapter so the rest of the code doesn't care which engine is behind it."""

    def __init__(self, source: str | None = None):
        self.name, self.spec, self.guardrails = get_source(source)
        self.type = self.spec["type"]
        self.max_rows = int(self.guardrails.get("max_rows", 5000))
        self.timeout = float(self.guardrails.get("timeout_seconds", 60))
        self._con = self._open()

    @property
    def dialect(self) -> str:
        return {"sqlite": "SQLite", "duckdb": "DuckDB", "postgres": "PostgreSQL"}.get(
            self.type, self.spec.get("dialect", "ANSI SQL"))

    def _open(self):
        t = self.type
        if t == "sqlite":
            p = (ROOT / self.spec["path"]).resolve()
            if not p.exists():
                raise RuntimeError(f"{p} not found. Run: python scripts/generate_demo_data.py")
            return sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
        if t == "duckdb":
            import duckdb  # type: ignore
            return duckdb.connect(str(ROOT / self.spec["path"]), read_only=True)
        if t == "postgres":
            import psycopg2  # type: ignore
            con = psycopg2.connect(_expand_env(self.spec["dsn"]))
            con.set_session(readonly=True, autocommit=True)
            with con.cursor() as c:
                c.execute(f"SET statement_timeout = {int(self.timeout * 1000)}")
                if self.spec.get("schema"):
                    c.execute("SET search_path TO %s", (self.spec["schema"],))
            return con
        if t == "sqlalchemy":
            import sqlalchemy  # type: ignore
            eng = sqlalchemy.create_engine(_expand_env(self.spec["url"]))
            return eng.connect()
        raise RuntimeError(f"Unsupported source type: {t}")

    # -- querying -------------------------------------------------------------
    def query(self, sql: str, max_rows: int | None = None, purpose: str = "") -> QueryResult:
        sql = check_read_only(sql)
        cap = min(max_rows or self.max_rows, self.max_rows)
        t0 = time.time()
        if self.type == "sqlite":
            deadline = t0 + self.timeout
            self._con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10_000)
        try:
            if self.type == "sqlalchemy":
                import sqlalchemy  # type: ignore
                res = self._con.execute(sqlalchemy.text(sql))
                cols = list(res.keys())
                rows = [tuple(r) for r in res.fetchmany(cap + 1)]
            else:
                cur = self._con.cursor()
                cur.execute(sql)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = [tuple(r) for r in cur.fetchmany(cap + 1)]
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e):
                raise TimeoutError(f"Query exceeded {self.timeout}s timeout") from e
            raise
        finally:
            if self.type == "sqlite":
                self._con.set_progress_handler(None, 0)
        truncated = len(rows) > cap
        rows = rows[:cap]
        res = QueryResult(cols, rows, truncated, int((time.time() - t0) * 1000), sql)
        _log(self.name, res, purpose)
        return res

    # -- introspection ----------------------------------------------------------
    def tables(self) -> list[tuple[str, str]]:
        """[(name, 'table'|'view')]"""
        if self.type == "sqlite":
            r = self._con.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
            return [(a, b) for a, b in r]
        schema = self.spec.get("schema", "main" if self.type == "duckdb" else "public")
        res = self.query(
            "SELECT table_name, CASE WHEN table_type LIKE '%VIEW%' THEN 'view' ELSE 'table' END "
            f"FROM information_schema.tables WHERE table_schema = '{schema}' ORDER BY 2, 1")
        return [tuple(r) for r in res.rows]

    def columns(self, table: str) -> list[tuple[str, str]]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", table):
            raise QueryRejected(f"Bad table name: {table}")
        if self.type == "sqlite":
            return [(r[1], r[2] or "") for r in self._con.execute(f"PRAGMA table_info('{table}')")]
        res = self.query(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{table}' ORDER BY ordinal_position")
        return [tuple(r) for r in res.rows]

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass


def _log(source: str, res: QueryResult, purpose: str) -> None:
    try:
        QUERY_LOG.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(repr(res.rows).encode()).hexdigest()[:12]
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source, "purpose": purpose, "sql": res.sql,
            "rows": len(res.rows), "truncated": res.truncated, "ms": res.elapsed_ms,
            "result_sha": digest,
        }
        res.meta["result_sha"] = digest
        with open(QUERY_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


_default: Connection | None = None


def connect(source: str | None = None) -> Connection:
    global _default
    if source is None:
        if _default is None:
            _default = Connection()
        return _default
    return Connection(source)


def query(sql: str, **kw) -> QueryResult:
    return connect().query(sql, **kw)


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m helpers.db")
    ap.add_argument("--source", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tables")
    d = sub.add_parser("describe"); d.add_argument("table")
    q = sub.add_parser("query")
    q.add_argument("sql", nargs="?")
    q.add_argument("--file")
    q.add_argument("--csv")
    q.add_argument("--purpose", default="")
    q.add_argument("--show", type=int, default=50)
    a = ap.parse_args(argv)

    con = connect(a.source)
    if a.cmd == "tables":
        for n, t in con.tables():
            print(f"{t:5}  {n}")
    elif a.cmd == "describe":
        for n, t in con.columns(a.table):
            print(f"{n:24} {t}")
    elif a.cmd == "query":
        sql = Path(a.file).read_text() if a.file else (a.sql or sys.stdin.read())
        try:
            res = con.query(sql, purpose=a.purpose)
        except QueryRejected as e:
            print(f"REJECTED: {e}", file=sys.stderr)
            sys.exit(2)
        print(res.to_markdown(a.show))
        print(f"\n{len(res.rows)} rows · {res.elapsed_ms} ms · sha {res.meta.get('result_sha')}")
        if a.csv:
            print(f"saved {res.to_csv(a.csv)}")


if __name__ == "__main__":
    main()
