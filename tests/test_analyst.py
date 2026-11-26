"""Run with: pytest -q"""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from helpers.db import QueryRejected, check_read_only, connect  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def demo_db():
    if not (ROOT / "data" / "bugs.db").exists():
        subprocess.run([sys.executable, "scripts/generate_demo_data.py"], cwd=ROOT, check=True)


# ---------------------------------------------------------------- guardrails
@pytest.mark.parametrize("sql", [
    "DELETE FROM bugs",
    "DROP TABLE bugs",
    "SELECT 1; DROP TABLE bugs",
    "WITH x AS (SELECT 1) INSERT INTO teams VALUES (9,'x',1)",
    "UPDATE bugs SET status='closed'",
    "PRAGMA writable_schema=1",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "",
])
def test_rejects_writes(sql):
    with pytest.raises(QueryRejected):
        check_read_only(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM bugs WHERE title LIKE '%delete%' OR title LIKE '%update%'",
    "-- comment with DROP\nSELECT 1",
    "WITH a AS (SELECT 1 AS x) SELECT x FROM a;",
    "SELECT REPLACE(title, 'a', 'b') FROM bugs LIMIT 1",
])
def test_allows_reads(sql):
    assert check_read_only(sql)


def test_connection_is_read_only_even_without_guardrail():
    import sqlite3
    con = connect()
    with pytest.raises(sqlite3.OperationalError):
        con._con.execute("DELETE FROM bugs")


def test_max_rows_truncates():
    res = connect().query("SELECT * FROM bugs", max_rows=10)
    assert len(res.rows) == 10 and res.truncated


# ---------------------------------------------------------------- knowledge
def example_blocks():
    txt = (ROOT / ".knowledge" / "example_queries.sql").read_text()
    for block in re.split(r"\n(?=-- Q:)", txt):
        if block.startswith("-- Q:"):
            q, sql = block.split("\n", 1)
            yield q[6:], sql


@pytest.mark.parametrize("question,sql", list(example_blocks()))
def test_example_queries_run_and_return_rows(question, sql):
    res = connect().query(sql, purpose="test")
    assert res.rows, f"no rows for: {question}"


def test_v_defects_excludes_non_defects_and_normalizes_severity():
    con = connect()
    assert con.query("SELECT COUNT(*) FROM v_defects WHERE status IN ('duplicate','wont_fix')").rows[0][0] == 0
    sev = {r[0] for r in con.query("SELECT DISTINCT severity_norm FROM v_defects").rows}
    assert sev == {"S1", "S2", "S3", "S4"}


# ---------------------------------------------------------------- planted patterns are findable
def test_planted_patterns():
    con = connect()
    top = con.query("""SELECT component_name FROM v_defects WHERE kloc IS NOT NULL
                       GROUP BY product_name, component_name, kloc
                       ORDER BY COUNT(*)/kloc DESC LIMIT 1""").rows[0][0]
    assert top == "offline-sync"
    reopen = con.query("""SELECT product_name FROM v_defects WHERE is_fixed=1 GROUP BY 1
                          ORDER BY AVG(reopened_count>0) DESC LIMIT 1""").rows[0][0]
    assert reopen == "Search"
    v32 = con.query("""SELECT COUNT(*) FROM v_defects d JOIN releases r ON r.release_id=d.found_in_release_id
                       JOIN products p ON p.product_id=r.product_id
                       WHERE p.product_name='Payments API' AND r.version='v3.2' AND d.is_regression=1""").rows[0][0]
    assert v32 > 50


# ---------------------------------------------------------------- CSV import
def test_import_jira_csv(tmp_path):
    csv = tmp_path / "jira.csv"
    csv.write_text(
        "Issue key,Summary,Project name,Component/s,Priority,Status,Resolution,Issue Type,Created,Resolved,Labels\n"
        "ABC-1,Crash on login,Mobile,auth,Highest,Done,Done,Bug,2026-01-02 10:00,2026-01-03 12:00,regression\n"
        "ABC-2,Typo,Web,settings,Low,Open,,Bug,2026-02-01 09:00,,\n"
        "ABC-3,Same as ABC-1,Mobile,auth,High,Closed,Duplicate,Bug,2026-01-02 11:00,2026-01-02 12:00,\n"
        "ABC-4,New feature,Web,,Medium,Open,,Story,2026-02-03 09:00,,\n")
    out = tmp_path / "imported.db"
    subprocess.run([sys.executable, "scripts/import_csv.py", str(csv), "--tracker", "jira", "--out", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    import sqlite3
    con = sqlite3.connect(out)
    rows = con.execute("SELECT bug_key, product_name, severity_norm, status, is_regression, days_to_resolve "
                       "FROM v_defects ORDER BY bug_key").fetchall()
    assert [r[0] for r in rows] == ["ABC-1", "ABC-2"]          # dup + story dropped
    assert rows[0][2] == "S1" and rows[0][4] == 1 and rows[0][5] > 1
    assert rows[1][3] == "open"


# ---------------------------------------------------------------- agent loop with a fake model
class FakeClient:
    """Scripted stand-in for anthropic.Anthropic: one tool call, then a final answer."""

    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls += 1
        if self.calls == 1:
            system = kw["system"][0]["text"]
            assert "Bug Analyst" in system and "v_defects" in system
            assert '<skill name="release-impact">' in system and "name: release-impact" not in system
            return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
                type="tool_use", id="t1", name="run_sql",
                input={"sql": "SELECT product_name, COUNT(*) n FROM v_defects GROUP BY 1 ORDER BY 2 DESC",
                       "purpose": "volume by product", "save_as": "vol"})])
        tool_result = kw["messages"][-1]["content"][0]["content"]
        assert "Web Dashboard" in tool_result
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="Web Dashboard has the most bugs.")])


def test_agent_loop_with_fake_client():
    from agent import Analyst
    a = Analyst(client=FakeClient(), verbose=False)
    assert a.ask("Which product has the most bugs?") == "Web Dashboard has the most bugs."
    assert "vol" in a.tools.saved
    msg = a.tools("make_chart", {"result": "vol", "kind": "bar", "x": "product_name", "y": "n",
                                  "title": "Web Dashboard leads in raw count"})
    assert msg.startswith("saved chart")
    assert a.tools("run_sql", {"sql": "DROP TABLE bugs", "purpose": "x"}).startswith("REJECTED")


def test_focus_report_runs(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import focus_report
    out = focus_report.run(12, out=tmp_path / "fr")
    brief = (out / "brief.md").read_text()
    assert "Bottom line" in brief and "(OK)" in brief
    assert len(list(out.glob("*.png"))) == 3


def test_write_file_is_confined_to_outputs(tmp_path):
    from agent import Tools
    t = Tools(ROOT / "outputs" / "test-agent-tmp")
    t.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        assert t("write_file", {"name": "../x.md", "content": "x"}).startswith("ERROR")
        assert t("write_file", {"name": "run.sh", "content": "x"}).startswith("ERROR")
        assert t("write_file", {"name": "brief.md", "content": "hi"}).startswith("saved")
    finally:
        shutil.rmtree(t.out_dir, ignore_errors=True)


def test_agent_focus_report_tool():
    from agent import Tools
    t = Tools(ROOT / "outputs" / "test-agent-tmp")
    t.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        res = t("focus_report", {"months": 12})
        assert "Bottom line" in res and "saved to" in res
    finally:
        shutil.rmtree(t.out_dir, ignore_errors=True)


def test_missing_api_key_gives_clear_error(monkeypatch):
    import agent
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(agent, "_load_dotenv", lambda: None)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        agent.Analyst()
