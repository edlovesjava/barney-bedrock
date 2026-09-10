import json
import subprocess

import pytest

from barney.config import RoleConfig
from barney.harness import Outcome
from barney.roles.coder import PreflightError, build_prompt, run_coder, slugify
from barney.run_record import RunRecord


class FakeHarness:
    name = "fake"

    def __init__(self, do, status="success", finish=None):
        self.do, self.status, self.finish = do, status, finish or {}

    def run(self, task, cfg, record):
        self.do(task)
        return Outcome(self.status, final_text="text", finish_args=self.finish)


def test_slugify():
    assert slugify("Add OLED status screen!") == "add-oled-status-screen"
    assert slugify("!!!") == "work"


def test_dry_run_creates_branch_and_commits_leftovers(repo):
    def do(task):
        (task.ctx.workdir / "src/b.py").write_text("y = 2\n")
        task.tools[0]  # tools exist
        assert {t.name for t in task.tools} >= {"read_file", "run_command", "git_commit", "post_plan", "finish"}
        assert "Issue #7: Do thing" in task.prompt and "no CLAUDE.md" in task.prompt

    rec = RunRecord("coder", "m", "fake", "o/r", "issue:7")
    fin = {"summary": "made b", "pr_title": "t", "pr_body": "b", "verification": "ran tests"}
    res = run_coder(
        harness=FakeHarness(do, finish=fin),
        cfg=RoleConfig(model="m"),
        workdir=repo,
        issue={"number": 7, "title": "Do thing", "body": "desc"},
        gh=None,
        repo="o/r",
        record=rec,
        dry_run=True,
    )
    assert res.branch == "agent/issue-7-do-thing"
    assert (
        subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        == res.branch
    )
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=repo, capture_output=True, text=True).stdout
    assert "made b" in log
    assert rec.outcome == "success" and rec.head_sha and rec.prompt_hash
    d = json.loads(json.dumps(rec.to_dict(), default=str))
    assert d["branch"] == res.branch


def test_protected_change_blocks_push(repo):
    def do(task):
        # bypass the fs tool guard by writing directly, as run_command could
        (task.ctx.workdir / ".github/workflows/ci.yml").write_text("evil\n")

    rec = RunRecord("coder", "m", "fake", "o/r", "issue:1")
    res = run_coder(
        harness=FakeHarness(do),
        cfg=RoleConfig(model="m"),
        workdir=repo,
        issue={"number": 1, "title": "x", "body": ""},
        gh=None,
        repo="o/r",
        record=rec,
        dry_run=False,
        base_branch="main",
    )
    assert res.outcome.status == "error" and "protected" in res.outcome.final_text
    assert res.pr_url == ""


def test_preflight_refuses_dirty_worktree(repo):
    (repo / "README.md").write_text("dirty\n")
    rec = RunRecord("coder", "m", "fake", "o/r", "issue:1")
    with pytest.raises(PreflightError, match="uncommitted"):
        run_coder(
            harness=FakeHarness(lambda t: None),
            cfg=RoleConfig(model="m"),
            workdir=repo,
            issue={"number": 1, "title": "x", "body": ""},
            gh=None,
            repo="o/r",
            record=rec,
            dry_run=True,
        )
    # allow_dirty folds the change in
    res = run_coder(
        harness=FakeHarness(lambda t: None),
        cfg=RoleConfig(model="m"),
        workdir=repo,
        issue={"number": 1, "title": "x", "body": ""},
        gh=None,
        repo="o/r",
        record=rec,
        dry_run=True,
        allow_dirty=True,
    )
    assert res.outcome.status == "success"


def test_branch_starts_from_base_not_current_head(repo):
    # Simulate a stale agent branch with an extra commit, then a new pass on the same issue.
    subprocess.run(["git", "checkout", "-q", "-b", "agent/issue-1-x"], cwd=repo, check=True)
    (repo / "stale.txt").write_text("stale\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "stale"], cwd=repo, check=True
    )
    rec = RunRecord("coder", "m", "fake", "o/r", "issue:1")
    run_coder(
        harness=FakeHarness(lambda t: None),
        cfg=RoleConfig(model="m"),
        workdir=repo,
        issue={"number": 1, "title": "x", "body": ""},
        gh=None,
        repo="o/r",
        record=rec,
        dry_run=True,
    )
    assert not (repo / "stale.txt").exists()  # branch was recreated from main, not from the stale head


def test_build_prompt_includes_conventions():
    p = build_prompt({"number": 1, "title": "T", "body": None}, "# CLAUDE.md\n\nrules")
    assert "(no description)" in p and "rules" in p
